# 当前任务状态

## 当前阶段：第三期已完成 ✅

## 已完成事项

### 后端（edubot-twin-server）
- `app/core/docker_client.py` — Docker 客户端单例（新建）
- `app/core/container_manager.py` — 容器生命周期异步管理器（新建）
- `app/core/security.py` — 新增 `get_current_student_id()` JWT 依赖注入
- `app/crud/container.py` — 4 处 Mock 替换为真实 Docker 调用
- `app/models/container.py` — 新增 `error_message` 字段
- `app/schemas/container.py` — `image_name` 默认值 → `gzweb_sim:v1`；`error_message` 字段
- `app/api/v1/endpoints/student/container.py` — JWT 鉴权 + 新增 `/start`、`/destroy-and-recreate` 端点
- `requirements.txt` — 新增 `docker>=7.0`

### 前端（edubot-twin-web）
- `src/views/Student/Home.vue` — 「开始仿真」完整容器预检 + 弹窗流程（4 种情况）
- `src/views/Simulation/Simulation.vue` — provide `containerRosUrl`；去掉 `TEMP_STUDENT_ID`
- `src/views/Simulation/panels/ROS3DViewer/index.vue` — inject `containerRosUrl`，watch 自动更新 rosUrl
- `src/api/container/index.ts` — 去掉 `studentId` 参数；新增 `destroyAndRecreateApi`、`startMyContainerApi`
- `src/api/container/types.ts` — `ContainerResponse` 增加 `error_message`

## 关键注意事项
- Python 版本：3.9.5（使用 `Optional[X]` 不用 `X | None`）
- 虚拟环境路径：`edubot-twin-server/../.venv/`
- `gzweb_sim:v1` 镜像需要在宿主机提前存在

## 下一步（第四期候选）
- 学生端 Terminal 集成（xterm.js + WebSocket 反向代理）
- 教师端容器监控看板（实时 CPU/内存）
- 考试/测试模块

### BUG修复
- 修复了因为 `src/api/container/index.ts` 中请求路径缺少 `/api/v1` 前缀而导致的 Vite 代理拦截失败（404 NotFound）的错误。
- 修复了因为 `src/axios/index.ts` 传递 JWT Token 时没有 `Bearer ` 前缀而导致的鉴权失败（401 Unauthorized）的错误。
- 修复了因开发迭代中 `sim_containers` 模型添加 `error_message` 字段但未更新 SQLite 表结构导致的 `sqlalchemy.exc.OperationalError`。

### 新增修复内容 (2026-03-24)
- **前端 404 控制台报错修复**：修改了学生端 `/mine` 与 `/start` 接口逻辑，当找不到容器时，不再抛出 `HTTPException(404)`，而是返回 `ApiResponse(code=0, data=None, message="尚未分配容器")`，以避免浏览器控制台出现红色的 AxiosError 报错。同时同步更新了 `SDD-第三期` 文档的对应描述。
- **仿真一直加载中修复**：发现学生端的后端容器相关接口（例如 `/mine`, `/request` 等）原先都未包裹在统一的 `ApiResponse[T]` 中返回，导致响应体内没有 `code: 0` 字段，进而触发前端 Axios 拦截器抛出 undefined 错误，最终导致 `waitForContainerRunning()` 轮询无限失败（一直在尝试）。修复：将所有返回接口包裹在了 `ApiResponse` 中。
- **浏览器拦截新标签页处理**：由于 `requestContainerApi` 及其后续轮询是异步操作，`window.open` 可能会被浏览器的弹窗拦截器阻挡，现在在弹窗被拦截时会自动显示警告并在当前标签页中跳转 (`router.push`)。
