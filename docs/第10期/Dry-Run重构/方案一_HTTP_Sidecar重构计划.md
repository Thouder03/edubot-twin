# Dry Run容器内文件管理服务（HTTP Sidecar代理方案）实施计划

## 一、 背景与目标

目前 Dry Run 环境下的「ROOT 模式」文件面板使用 `docker exec` (`container_files.py`) 来实现容器内的文件管理，这导致了以下困境：
1. **指令硬编码困难**：后端的 `docker exec` API 只能支持极为有限的命令（`ls`, `cat`, `mkdir`, `rm`）。
2. **大文件传输黑洞**：无法优雅地处理上传 (Upload)、下载打包 (Download)、解压 (Extract) 等基于流的操作。
3. **前后端代码强耦合拆分**：前端的 `useWorkspaceCommands` 等必须为了 ROOT 模式使用另一套阉割版 API，维护两套 API 分发链路异常痛苦。

**目标（方案一）**：
在容器初次启动时，挂载并启动一个功能与 `student/files.py` 极其相似的轻量级无状态 HTTP 文件服务（**Sidecar**）。所有 ROOT 模式的操作由后端 FastAPI 接收后，直接作为 Reverse Proxy **透明反向代理**转发进容器内的该服务处理，从而以零代码差异支持高级操作。

---

## 二、 核心架构

### 1. 容器内服务 (`mini_file_server.py`)
提取现有的 `student/files.py` 核心功能形成独立的单文件 FastAPI 服务，剥离 JWT 和 DB 强依赖约束，取消禁止绝对路径的安全校验（这本就是为了访问任意绝对路径）。
- 运行时：容器内置的 Python 和 `uvicorn` (依赖 FastAPI, Pydantic, Uvicorn 等)。
- 监听地址：`0.0.0.0:8010` (安全上仅允许 Docker Bridge 网络被宿主机访问)。

### 2. 后端宿主代理 (`teacher/container_files.py` 改写)
宿主机原有用来拼装 `docker exec` 的路由拦截器被替换。
无论前端发送什么文件操作请求，后端只需要抓取 URL 的 `path`、`body` 或 `stream`，直接全透传给 `http://[容器IP]:8010/files/[action]`。

### 3. 前端复用 (`useWorkspace`)
前端文件完全不需要拆解，统一维护 `rootFileMode: boolean`，开启时只需将 `API Base URL` 指向宿主代理层，参数和格式与普通文件操作完全一致。

### 4. 权限分层与目录策略（新增）
在统一 Sidecar 链路下，文件访问能力按身份分层：
- **真实学生（student）**：仅允许浏览 `/home` 与 `/root` 两个入口目录；
  - `/home/student` 允许读写；
  - `/home` 下其他目录与 `/root` 仅允许只读（用于查看 ROS/Gazebo 日志等）。
- **Shadow 学生（Dry Run）**：可切换 ROOT 模式，允许访问容器全文件系统（沿用教师 Dry Run 能力）。

---

## 三、 执行步骤（Plan）

### Phase 1： 编写与准备注入容器的 `mini_file_server.py`
1. 复制后端的 `app/api/v1/endpoints/student/files.py`。
2. **瘦身与改造**：
   - 移除所有的 `Depends(get_current_student_id)`（授权因为外层宿主机已经代理拦截鉴权了）。
   - 移除所有的 `check_disk_quota` 磁盘配额检查逻辑。
   - 修改 `validate_path` 使其支持绝对路径，或直接废弃 `validate_path` 转为基于 `pathlib.Path.resolve()`。
3. 把文件放置在后端的某个公共文件分发池里，例如 `data/system/agent/mini_file_server.py`，等待容器启动时动态挂载或发送进去。
4. 提供一个附带的 `requirements-agent.txt` 确保容器环境安装了 FastAPI 等。

### Phase 2： 容器生命周期改造 (`simulation.py`)
1. 修改 `simulation.py` 中的 `_run_rebuild_task` 启动容器环节。
2. 启动容器时增加逻辑：利用 `docker cp` 或挂载（Volume Mount），将宿主机上的 `mini_file_server.py` 投喂进目标容器内 `/opt/edubot/agent/`。
3. 改写 `system_entrypoint.sh` 生成逻辑，使得每次进入仿真时都会在后台执行：
   ```bash
   nohup python3 -m uvicorn mini_file_server:app --host 0.0.0.0 --port 8010 &
   ```
4. 容器需要向 Docker 暴露 `8010` 端口，以便我们能在宿主机反向请求。

### Phase 3： 宿主机透明代理核心 (`container_proxy.py`)
1. 删除 `container_files.py` 中老的基于 `docker exec` 的代码。
2. 使用 `httpx` (推荐配合 `httpx.AsyncClient`) 改写一套包含所有动作前缀匹配的反向代理函数：
    ```python
    import httpx
    # 示例代理路由
    @router.api_route("/{path:path}", methods=["GET", "POST", "DELETE", "PUT"])
    async def proxy_to_container(request: Request, path: str, user_id: int = Depends(...)):
        container_ip = await get_container_ip_by_user(user_id)
        target_url = f"http://{container_ip}:8010/files/{path}"
        
        async with httpx.AsyncClient() as client:
            req = client.build_request(...)
            response = await client.send(req, stream=True)
            return StreamingResponse(...)
    ```
*(注：如果处理大文件流，此方案对内存友好，因为全双工数据流)*

### Phase 4： 宿主机透明代理扩展为双路由（新增）
1. 将 `teacher/container_files.py` 的 `docker exec` 逻辑替换为 Sidecar 反向代理。
2. 新增学生侧代理入口（建议 `student/container_files_proxy.py` 或在 `student/files.py` 增加 `/container/*` 子路由），统一转发到 `http://[容器IP]:8010/files/[action]`。
3. 在代理层注入**能力上下文**（`access_scope`）：
   - `shadow_root`：全路径 + 可写（Dry Run）
   - `student_limited`：仅 `/home` `/root` 可见，其中仅 `/home/student` 可写
4. 代理层处理流式上传下载，避免大文件内存峰值。

### Phase 5： 容器内 `mini_file_server.py` 增加策略校验（新增）
1. 每个请求接收 `access_scope` 与 `requested_path`，统一走 `resolve_path_with_policy()`。
2. 对真实学生执行路径与写权限校验：
   - 允许读取：`/home`, `/root`
   - 允许写入：`/home/student`
3. 对 Shadow 学生放开全路径（保留危险删除保护，可复用 blocklist）。
4. 对 `upload/save/mkdir/delete/rename/move/copy/extract/compress` 全动作统一套用同一策略，避免遗漏。

### Phase 6： 前端 WorkspacePanel 能力开关重构（新增）
1. 将 `WorkspacePanel/index.vue` 当前 `isDryRunMode`/`rootFileMode` 的硬编码，改为上下文能力模型：
   - `canSwitchRoot`
   - `pathPresets`（`/home/student`、`/home`、`/root`）
   - `readOnlyRules`
2. 学生仿真页显示目录切换按钮（`/home/student`、`/home`、`/root`），不显示 ROOT 全局切换。
3. Dry Run 仿真页保留 `USR/ROOT` 切换按钮。
4. 在 `useWorkspaceTreeState.ts` 与 `useWorkspaceCommands.ts` 中移除对 Dry Run endpoint 的硬编码，统一走文件 API 适配层，根据能力模型决定目标 endpoint 和动作可用性。

### Phase 7： 验证与回归（新增）
1. **学生身份**
   - `/home/student` 可上传、编辑、删除、压缩、解压
   - `/home` 与 `/root` 可浏览、读取、下载；写操作返回 403
2. **Shadow 身份（Dry Run）**
   - `USR/ROOT` 切换后所有文件动作可用
3. **一致性**
   - 文件树、编辑器、快捷键、批量操作在两类身份下行为一致
4. **安全性**
   - 路径穿越、越权写入、危险目录删除均被拦截

---

## 四、 风险防范
- **依赖缺失**：学生端的实验镜像里**通常**一定会装有 Python，但有可能没有安装 `fastapi` 和 `uvicorn`。需要在实验包的环境准备阶段保证注入基础代理工具包的 pip install 或改用标准库单纯写个 HTTP 服务。
- **防止端口拥挤**：固定 `8010` 端口必须确认不与其他 ROS 服务冲突，最好做可配置。
- **权限绕过风险**：若仅在前端做只读限制会被绕过，必须在宿主代理 + Sidecar 双层强校验。
- **策略碎片化风险**：目录白名单/读写白名单必须收敛到单一策略函数，避免某个 action 漏校验。
- **兼容性风险**：现有 `WorkspacePanel` 已硬编码 Dry Run endpoint，迁移时需保留适配层，避免一次性改动过大导致回归。

## 五、 学生仿真页文件管理面板纳入后的目标行为

### 学生身份（student）
- 面板提供三个目录入口：`/home/student`、`/home`、`/root`。
- 仅 `/home/student` 可写，其他目录只读。
- 允许读取日志相关文件，不允许修改系统文件。

### Shadow 身份（Dry Run）
- 保留 `USR/ROOT` 切换。
- ROOT 下可访问全文件系统，能力与教师 Dry Run 对齐。

### 统一原则
- 两类身份都走同一套 Sidecar 协议与请求格式。
- 差异仅体现在后端注入的 `access_scope` 与策略校验结果。

## 六、 注意项（新增）
- 学生端**独立文件管理页面** [`FileManager.vue`](edubot-twin-web/src/views/Student/FileManager.vue) 保持当前逻辑不变，继续使用服务器侧学生工作区方案（`/api/v1/students/files`）。
- 本次 Sidecar 扩展仅作用于仿真页内的 [`WorkspacePanel/index.vue`](edubot-twin-web/src/views/Simulation/panels/WorkspacePanel/index.vue) 场景，不改变独立页面现有行为与接口契约。
