# 工程架构审查报告：容器安全加固与终端优化（第8期）

**审查日期**：2026-03-31  
**审查模式**：完整工程审查 + 外部视角（Claude subagent）  
**文档版本**：v1.0  
**原始计划**：[SDD-第8期：容器安全加固与终端优化](./SDD-第8期：容器安全加固与终端优化.md)  
**CEO 审查**：[CEO-Review-第8期：容器安全加固与终端优化](./CEO-Review-第8期：容器安全加固与终端优化.md)

---

## 执行摘要

本次工程架构审查在 CEO Review (HOLD SCOPE) 的基础上，对第8期实施方案进行了全面技术验证。

**关键成果**：
- ✅ 发现并修正 CEO Review 中的 2 处逻辑错误（`user=` 层级错误、`chmod` 循环逻辑）
- ✅ 外部视角（独立 Claude 实例）新增发现 3 个问题，全部纳入实施范围
- ✅ 确认最终变更集：3 个文件，5 处修改，0 个新类
- ✅ 测试计划：5 个 mock Docker unit tests

**最重要的修正**：CEO Review 建议将 `user="1000:1000"` 加到容器创建层（`create_container()`），工程审查发现这与现有 `patch_cmd` 根本不兼容——最终决策改为只在 `docker exec` 终端层应用，容器启动链路不受影响。

---

## 一、范围确认（Step 0）

### 1.1 已有基础设施（直接复用）

| 已有代码 | 文件 | 本期做法 |
|---------|------|---------|
| workspace 创建 | `core/container_manager.py:37` | 在函数末尾追加 chown 逻辑 |
| 容器创建 | `core/container_manager.py:76` | 追加安全参数 |
| executor 封装模式 | `core/container_manager.py:29` | `ensure_network` 复用此模式 |
| lifespan 钩子 | `app/main.py:143` | 在 `yield` 前插入 network 初始化 |
| docker exec 命令构造 | `api/v1/endpoints/student/terminal.py:121` | 追加 `-u 1000 -w /workspace` |

### 1.2 复杂度检查

- 触及文件数：3 个 ✓（远低于 8 文件阈值）
- 新增核心组件：0 个新类，1 个新函数（`ensure_edubot_network`）✓
- 复杂度检查通过

### 1.3 已明确不做（本期）

| 功能 | 原因 |
|------|------|
| `cap_drop ALL` | Gazebo GPU 渲染兼容性风险，答辩后验证 |
| `read_only=True` rootfs | 需调试 ROS 临时目录可写挂载，与 cap_drop 同批 |
| iptables 精细过滤 | 运营复杂度过高，Docker 网络隔离已满足需求 |
| 极端命令兜底拦截 | 容器层已足够，终端透传是核心体验 |

---

## 二、架构审查

### 2.1 架构问题汇总

| # | 问题 | 严重级别 | 决策 |
|---|------|---------|------|
| 1 | `user="1000:1000"` 在容器创建层与 `patch_cmd` 不兼容 | P0 | 移至 `docker exec` 层，容器层不设置 |
| 2 | `ensure_edubot_network()` 在 async lifespan 中同步阻塞事件循环 | P0 | 用 `_run_in_executor` 包装 |
| 3 | `enable_icc=False` Docker SDK 参数格式错误 | P1 | 使用 `options={"com.docker.network.bridge.enable_icc": "false"}` |
| 4 | CEO Review 提出的 `chmod 666` 修复是循环逻辑（外部视角确认） | P0 | 随决策 #1 一并消解 |

### 2.2 关键架构决策详解

#### 决策 1：`user="1000:1000"` 仅在终端层（最重要修正）

**问题根因**：

```
CEO Review 方案：
  client.containers.run(..., user="1000:1000", command=["-c", "chmod 666 ... && sed ..."])
                              ↑
                    容器所有进程以 uid 1000 运行
                    包括 patch_cmd 里的 chmod 和 sed

问题链：
  uid 1000 运行 chmod 666 root-owned-file → Permission denied
  || true 静默掩盖
  sed -i 仍然因权限不足失败
  容器 exit code ≠ 0
  仿真完全不可用
```

外部视角独立识别了这个循环逻辑——`chmod` 本身就需要文件所有权，uid 1000 无法 chmod root-owned 文件。

**最终方案**：`user="1000:1000"` 只加在 `terminal.py` 的 `docker exec` 命令上：

```
容器创建层（patch_cmd + Gazebo/ROS 启动）：
  user 不设置 → 以镜像默认用户运行 → patch_cmd 正常 → Gazebo 正常

终端层（学生交互）：
  docker exec -u 1000 -w /home/student/workspace {container_id} /bin/bash
                ↑
        只有学生终端会话降权，启动链路不受影响
```

**安全目标验证**：学生只能通过终端操作容器，终端以 uid 1000 进入，写入系统目录报 `Permission denied`，`no-new-privileges` 防止提权。目标达成。

---

#### 决策 2：`ensure_edubot_network()` 必须用 executor 封装

`lifespan()` 是 async 函数，Docker SDK 是同步 I/O。直接调用会阻塞事件循环：

```python
# ❌ 错误（阻塞）
async def lifespan(app):
    ensure_edubot_network()  # 同步调用，卡住事件循环

# ✅ 正确（复用已有 executor 模式）
async def ensure_edubot_network():
    await _run_in_executor(_sync_ensure_network)

# 或在 lifespan 中
async def lifespan(app):
    await asyncio.get_event_loop().run_in_executor(None, _sync_ensure_network)
```

项目已有 `_run_in_executor()` 标准封装，直接复用，零额外代码。

---

#### 决策 3：`enable_icc` Docker SDK 参数路径

CEO Review 写 "设置 `enable_icc=false`"，但 docker-py 的 `networks.create()` 没有顶层 `enable_icc` 参数。正确写法：

```python
# ❌ 错误（被忽略，容器间隔离不生效）
client.networks.create(name="edubot_network", enable_icc=False)

# ✅ 正确
client.networks.create(
    name="edubot_network",
    driver="bridge",
    options={"com.docker.network.bridge.enable_icc": "false"},
)
```

同时，`ensure_edubot_network` 需要用 `try/except` 处理网络已存在的情况（`docker.errors.APIError: network with name edubot_network already exists`），否则服务重启会直接抛异常。

---

### 2.3 架构流程图（最终方案）

```
容器生命周期安全架构
=====================

服务启动 (lifespan)
  │
  └─▶ ensure_edubot_network() [executor]
        ├─ 网络不存在 → 创建 edubot_network (bridge, icc=off)
        └─ 网络已存在 → 幂等返回

学生启动仿真 → create_container()
  │
  ├─▶ create_student_workspace()
  │     ├─ 创建目录结构
  │     └─ chown -R 1000:1000  [subprocess, check=True]
  │
  └─▶ client.containers.run(
          privileged=False,
          security_opt=["no-new-privileges:true"],
          network="edubot_network",
          shm_size="512m",
          devices=["/dev/dri:/dev/dri:rwm"]
          # ← 无 user= 参数，patch_cmd 以镜像默认用户运行
      )

学生打开终端 → terminal_ws()
  │
  ├─▶ 认证 + 频控（已实现）
  │
  └─▶ docker exec -it
            -u 1000              ← 只在此处降权
            -w /home/student/workspace
            -e TERM=xterm
            {container_id} /bin/bash
```

---

## 三、代码质量审查

### 3.1 代码质量问题汇总

| # | 问题 | 文件位置 | 决策 |
|---|------|---------|------|
| 1 | `chown` 只改目录本身，不递归 | `container_manager.py:53` | `subprocess.run(["chown", "-R", ...], check=True)` |
| 2 | `chown` PermissionError 静默 WARNING，导致假成功 | CEO Review §5.3 | 改为 `raise CalledProcessError` 暴露失败 |
| 3 | `docker exec` 用 `-u student` 依赖容器内用户名（外部视角发现） | `terminal.py:121` | 改为 `-u 1000`（UID 更健壮，不依赖 `/etc/passwd`） |

### 3.2 关键代码质量改进

#### 改进 1：`chown` 递归实现

**问题**：`create_student_workspace()` 创建 4 个子目录 + 复制模板文件，但 `os.chown(workspace, 1000, 1000)` 只修改顶级目录 owner。子目录和模板文件（`shutil.copy2` 保留 source owner，可能是 root）对 uid 1000 不可写。

**方案**（两种，用户选择 A）：

```python
# ✅ 方案 A（已采纳）：subprocess chown -R
import subprocess

result = subprocess.run(
    ["chown", "-R", "1000:1000", str(workspace)],
    check=True,        # 失败时抛 CalledProcessError，不静默
    capture_output=True,
)
logger.info(f"工作区权限设置完成: {workspace}")
```

```python
# 方案 B（备选）：os.walk 纯 Python
import os
for dirpath, dirnames, filenames in os.walk(workspace):
    os.chown(dirpath, 1000, 1000)
    for filename in filenames:
        os.chown(os.path.join(dirpath, filename), 1000, 1000)
```

**PermissionError 处理**：调用进程（uvicorn）需要 root 或 `CAP_CHOWN`。开发环境以 root 运行 uvicorn 是惯例。若 `chown` 失败，改为抛出异常（`CalledProcessError`）而非静默 WARNING，让容器创建 API 返回 500，给教师明确的失败信号。

---

#### 改进 2：`docker exec` 用 UID 而非用户名

**问题**：`-u student` 依赖容器镜像的 `/etc/passwd` 中存在名为 `student` 的条目。gzweb 镜像以 root 构建，不一定有 `student` 用户名。

```python
# ❌ 脆弱（依赖镜像内用户名）
f"docker exec -it -u student -w /home/student/workspace ..."

# ✅ 健壮（直接指定 UID，不依赖 /etc/passwd）
f"docker exec -it -u 1000 -w /home/student/workspace ..."
```

---

## 四、测试审查

### 4.1 代码路径覆盖图

```
CODE PATH COVERAGE（第8期新增/修改路径）
==========================================

[+] container_manager.py — ensure_edubot_network()
    │
    ├── [GAP → TEST] 网络不存在 → 创建成功（验证 options 含 icc=false）
    ├── [GAP → TEST] 网络已存在 → 幂等返回，不重复创建
    └── [GAP] Docker 不可达 → 异常传播（手动测试覆盖）

[+] container_manager.py — create_student_workspace() + chown
    │
    ├── [GAP → TEST] chown 成功 → workspace + 所有子目录/文件 owner=1000:1000
    └── [GAP → TEST] chown 失败（check=True）→ 抛出 CalledProcessError

[+] container_manager.py — create_container() 安全参数
    │
    └── [GAP] 安全参数传入验证（privileged=False, security_opt, network）
            → 手动测试（docker inspect 验证）

[+] terminal.py — docker exec 命令构造
    │
    └── [GAP → TEST] 命令字符串包含 -u 1000 和 -w /home/student/workspace

[+] main.py — lifespan ensure_network 调用
    │
    └── [GAP] lifespan 中调用 ensure_network（手动测试覆盖）

─────────────────────────────────────────
自动化测试覆盖：0/5 关键路径（0%）
规划 unit tests：5 个（mock Docker）
手动测试：其余场景由 CEO Review 验证清单覆盖
─────────────────────────────────────────
```

### 4.2 单元测试计划（5 个）

所有测试使用 `unittest.mock.patch("docker.from_env")` mock Docker 客户端，不需要真实 Docker daemon，CI 可运行。

| # | 测试名称 | 验证内容 |
|---|---------|---------|
| 1 | `test_ensure_edubot_network_creates_when_missing` | mock `networks.list()` 返回空 → 验证 `networks.create()` 被调用，`options` 含 `com.docker.network.bridge.enable_icc: "false"` |
| 2 | `test_ensure_edubot_network_idempotent` | mock `networks.list()` 返回已有网络 → 验证 `networks.create()` 不被调用 |
| 3 | `test_create_student_workspace_chown_recursive` | 使用 `tempdir`，mock `subprocess.run` → 验证调用 `chown -R 1000:1000 {workspace}` |
| 4 | `test_create_student_workspace_chown_failure_raises` | mock `subprocess.run` 返回 `returncode=1` → 验证抛出 `CalledProcessError` |
| 5 | `test_terminal_exec_uses_uid_1000` | 捕获 `asyncio.create_subprocess_exec` 调用 → 验证命令字符串包含 `-u 1000` 和 `-w /home/student/workspace` |

### 4.3 手动测试清单（来自 CEO Review §6）

| 测试项 | 操作 | 预期结果 |
|--------|------|---------|
| 容器用户确认 | `docker exec <id> whoami` | 容器内进程以镜像默认用户运行 |
| 工作区可写 | `echo test > ~/workspace/t.txt` | 成功（终端内 uid 1000） |
| 系统目录不可写 | `echo x > /usr/bin/test_sec` | `Permission denied`（如镜像非 root 用户） |
| 特权禁止 | `sudo su 2>&1` | `command not found`（no-new-privileges） |
| 容器间隔离 | 从容器 A `ping` 容器 B | 不通（icc=false） |
| 终端落点 | 打开前端终端 | 提示符在 `~/workspace`，身份为 uid 1000 |
| Gazebo 可用 | 浏览器打开 GzWeb 面板 | 场景正常渲染（privileged=False 兼容验证） |
| ROS 正常 | `roslaunch` 命令 | 正常执行，无权限报错 |
| 网络建立幂等 | 重启后端服务两次 | 无报错，`edubot_network` 存在一个 |
| 工作区 chown | `ls -la /home/student/workspace` | owner 显示 `1000:1000` |

---

## 五、性能审查

无显著问题。

- `ensure_edubot_network()` 一次性在启动时调用，不影响请求路径
- `create_container()` 已在 executor 线程池，追加参数不改变调用模式
- `chown -R` 在 workspace 初始化时运行，目录通常很小（<100 文件），毫秒级

---

## 六、故障模式分析

| 代码路径 | 潜在失败 | 有测试? | 有错误处理? | 用户体验 |
|---------|---------|--------|-----------|---------|
| `ensure_network` 首次调用 | Docker 不可达 | ❌ | ❌（异常传播，服务启动失败） | 后端不启动，部署层报警 |
| `ensure_network` 重复调用 | `APIError: network already exists` | ✅（unit test 2） | 需加 try/except | 服务重启崩溃 → **critical gap，需修复** |
| `chown` PermissionError | uvicorn 非 root 运行时失败 | ✅（unit test 4） | 抛 `CalledProcessError`，500 响应 | 教师看到明确 500 错误 |
| `patch_cmd` 权限（已解决） | 以镜像默认用户运行，无问题 | — | — | — |
| `docker exec -u 1000` 失败 | UID 1000 在容器内不存在（极小概率） | ❌ | 终端显示错误信息 | 学生看到错误提示 |
| `devices=["/dev/dri"]` + `privileged=False` | GPU 渲染失败 | ❌ | 无（Gazebo 可能黑屏） | 必须手动验证 |

**critical gap**：`ensure_network` 重复调用时必须用 `try/except docker.errors.APIError` 处理 "already exists" 错误，否则后端重启会崩溃。

---

## 七、外部视角（独立 Claude 实例审查）

**结论**：运行 Claude subagent 作为独立外部视角（Codex 不可用）。

外部视角共发现 6 个问题：

| # | 发现 | 评估 | 处置 |
|---|------|------|------|
| 1 | `chmod 666` 是循环逻辑（uid 1000 无法 chmod root 文件） | ✅ 正确，与架构问题 #1 同根 | 随 `user=` 移至 exec 层决策一并消解 |
| 2 | `-u student` 依赖容器内用户名，不如 `-u 1000` 健壮 | ✅ 正确 | 纳入实施：改为 `-u 1000` |
| 3 | `chown check=False` 与 PermissionError 处理路径不对齐 | ✅ 正确 | 纳入实施：改为 `check=True` |
| 4 | `enable_icc=false` 可能影响多容器 ROS 通信 | 本项目每学生一个容器，ICC 只隔离学生间 | 可接受 |
| 5 | `/dev/dri` + `privileged=False` + uid 1000 可能不在 video group | 随 `user=` 移至 exec 层解决（容器启动以镜像用户运行） | 消解 |
| 6 | metrics 采集使用随机数（`main.py:50`） | 已存在的技术债，非本期范围 | 已记录，第9期处理 |

**跨模型共识**：外部视角与工程评审在核心问题（`user=` 层级、`chmod` 循环逻辑、`-u` 参数健壮性）上一致。无跨模型分歧。

---

## 八、最终实施范围（锁定）

在 CEO Review 基础上，经工程评审和外部视角修正后的精确实施清单：

| 文件 | 具体变更 | 优先级 | 变更来源 |
|------|---------|--------|---------|
| `container_manager.py` | 新增 `EDUBOT_NETWORK = "edubot_network"` 常量 | P0 | CEO Review |
| `container_manager.py` | 新增 `ensure_edubot_network()`，内部用 `_run_in_executor`，捕获 "already exists" | P0 | CEO Review + 工程评审 |
| `container_manager.py` | `create_student_workspace()` 末尾追加 `subprocess.run(["chown", "-R", "1000:1000", str(workspace)], check=True)` | P0 | CEO Review + 工程评审 |
| `container_manager.py` | `create_container()` 新增 `privileged=False, security_opt=["no-new-privileges:true"], network=EDUBOT_NETWORK, shm_size="512m", devices=["/dev/dri:/dev/dri:rwm"]`；**不加 `user=`** | P0 | CEO Review，工程评审修正 |
| `terminal.py` | `docker exec` 命令追加 **`-u 1000`**（非 `-u student`）和 `-w /home/student/workspace` | P0 | CEO Review，外部视角修正 |
| `main.py` | `lifespan()` 的 `yield` 前调用 `await ensure_edubot_network()` | P0 | CEO Review |

### 与 CEO Review 的关键差异

| CEO Review 原方案 | 工程评审修正 | 原因 |
|-----------------|------------|------|
| `create_container()` 加 `user="1000:1000"` | **不加** | 与 `patch_cmd` 循环依赖，无法 chmod root 文件 |
| `docker exec -u student` | `docker exec -u 1000` | 用户名依赖镜像 `/etc/passwd`，UID 更健壮 |
| `chmod 666 || true` 修复 patch_cmd | **不需要** | 随 user= 移至 exec 层后，patch_cmd 以镜像默认用户运行，无权限问题 |
| `ensure_network` 直接调用 | 用 `_run_in_executor` 包装 | 防止阻塞 async 事件循环 |
| `chown` 方式未指定 | `subprocess.run check=True` | 递归 + 失败时抛异常而非静默 |

---

## 九、工作量估算

| 子任务 | AI 辅助 |
|--------|---------|
| `ensure_edubot_network()` + 常量 + executor 封装 | 5 分钟 |
| `create_student_workspace()` chown -R | 3 分钟 |
| `create_container()` 安全参数（无 user=） | 5 分钟 |
| `main.py` lifespan 集成 | 3 分钟 |
| `terminal.py` exec 参数（-u 1000） | 2 分钟 |
| 5 个 mock unit tests | 15 分钟 |
| 验证测试（手动） | 30 分钟 |
| **总计** | **~63 分钟** |

---

## 十、完成总结

### 10.1 审查统计

- **Step 0 范围挑战**：范围合理，3 文件 0 新类，通过
- **架构审查**：4 个问题，全部解决
- **代码质量审查**：3 个问题，全部解决
- **测试审查**：5 个 unit tests 纳入实施范围
- **性能审查**：无问题
- **外部视角**：6 个发现，3 个纳入实施，3 个评估后可接受

### 10.2 关键决策

| 决策 | 选项 | 结论 |
|------|------|------|
| `user="1000:1000"` 作用层级 | A) 仅 docker exec 层 / B) 容器创建层 | **A**（避免 patch_cmd 不兼容） |
| `chown` 实现方式 | A) subprocess -R / B) os.walk | **A**（简洁，check=True 暴露错误） |
| 测试策略 | A) mock Docker unit tests / B) 仅手动测试 | **A**（5 个自动化测试） |

### 10.3 最终评分

| 维度 | SDD 原文 | CEO Review 后 | 工程审查后 |
|------|---------|--------------|-----------|
| 安全设计正确性 | 5/10 | 8/10 | 9/10 |
| 实现完整性 | 6/10 | 9/10 | 9/10 |
| 风险控制 | 6/10 | 9/10 | 9/10 |
| 可交付性（毕设） | 6/10 | 9/10 | 9/10 |

**总评**：CEO Review 修正了 SDD 的设计错误，工程审查发现了 CEO Review 自身的实现逻辑错误（`user=` 层级、`chmod` 循环），修正后方案可直接落地实施。

---

## 附录

### A. 相关文档

- [SDD-第8期：容器安全加固与终端优化](./SDD-第8期：容器安全加固与终端优化.md) - 原始设计文档
- [CEO-Review-第8期：容器安全加固与终端优化](./CEO-Review-第8期：容器安全加固与终端优化.md) - CEO 战略审查
- [gzweb docker-compose.yml](../../../gzweb/docker-compose.yml) - 容器参数对齐参考

### B. 审查方法论

1. **Step 0 范围挑战**：检查现有代码、复杂度、完整性
2. **架构审查**：追踪 CPU/内存/网络参数传递路径，验证 async 安全性
3. **代码质量审查**：DRY、错误处理显式化、参数健壮性
4. **测试审查**：追踪所有新增代码路径，生成覆盖率图表
5. **外部视角**：独立 Claude 实例对计划进行盲审，无先验偏见

---

**文档状态**：已完成  
**下一步行动**：按锁定实施范围进行代码修改  
**审查人**：Claude Code (Eng Review + 外部视角)  
**审查日期**：2026-03-31
