# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Edubot Twin 是一个面向移动机器人实训的数字孪生评测平台，采用 Monorepo 架构：
- **前端** (`edubot-twin-web`): Vue 3.5 + Vite 6 + TypeScript + Element Plus + UnoCSS
- **后端** (`edubot-twin-server`): Python 3.9+ FastAPI + SQLAlchemy + SQLite
- **核心功能**: 基于 WebGL 的 ROS 3D 可视化、容器化仿真环境管理、在线考试评测

## 开发环境

### scripts/ 规范

> ⚠️ 所有 Run & Debug 操作必须通过 `scripts/` 目录下的 `.sh` 脚本进行，严禁直接使用 `pnpm`、`uvicorn` 等命令。
> 如所需脚本尚未存在，先创建脚本，再通过脚本执行。

### 现有 scripts/

| 脚本 | 用途 |
|---|---|
| `start_server.sh` | 启动后端 API 服务（自动加载 .env，端口 8000） |
| `start_nginx_dev.sh` | 启动开发环境 Nginx 反向代理 |
| `stop_nginx_dev.sh` | 停止 Nginx |
| `ts_check_web.sh` | 前端类型检查（提交前必跑） |
| `migrate_db.sh` | SQLite 增量迁移（新增 ORM 字段后运行，幂等） |
| `bench_sim_containers.sh` | 仿真容器并发性能压测 |
| `fix_exam_dir_ownership.sh` | 修复考试目录被 root 创建的所有权问题 |
| `test_sidecar.sh` | Sidecar 文件服务 & 代理层联调测试 |
| `test_server_container_crud.sh` | 容器 CRUD 接口测试 |
| `test_server_status_toggle.sh` | 容器状态切换测试 |
| `test_server_terminal_permissions.sh` | 终端权限测试 |
| `test_server_exam_attempts.sh` | 考试尝试接口测试 |
| `test_server_student_crud.sh` | 学生 CRUD 接口测试 |
| `test_server_phase10.sh` | 第 10 期验收脚本 |

### 前端常用命令（需要时请封装到 scripts/）

```bash
cd edubot-twin-web
pnpm install          # 安装依赖
pnpm run dev          # 开发服务器 → http://localhost:4000
pnpm ts:check         # 类型检查（已封装：scripts/ts_check_web.sh）
pnpm lint:eslint      # ESLint
pnpm lint:format      # Prettier
pnpm build:pro        # 生产构建
```

**要求**: Node.js >= 18.0.0, pnpm >= 8.1.0

### 后端常用命令（需要时请封装到 scripts/）

```bash
cd edubot-twin-server
../.venv/bin/pip install -r requirements.txt  # 安装依赖
../.venv/bin/python init_db.py                # 初始化数据库（首次）
../.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# 或使用已封装的脚本：bash scripts/start_server.sh
# API 文档: http://localhost:8000/docs
```

**虚拟环境**: `.venv` 位于项目根目录（所有 Python 命令通过 `../.venv/bin/...` 调用）。

### 后端测试

```bash
cd edubot-twin-server
../.venv/bin/python -m pytest tests/ -v        # 运行全部测试
../.venv/bin/python -m pytest tests/test_exam_domain.py -v  # 运行单个测试文件
```

**pytest 配置**: `pytest.ini` 中已设置 `asyncio_mode = auto`，异步测试函数直接写 `async def test_xxx` 即可。

## 核心架构

### 前端架构

```
edubot-twin-web/src/
├── views/
│   ├── Simulation/          # ★ 核心仿真工作台 (Golden Layout v2.6)
│   │   ├── Simulation.vue   # 主容器
│   │   ├── panels/          # 8 个功能面板（见下文）
│   │   ├── composables/     # useRenderer, useRosConnection
│   │   ├── stores/          # panelState（面板状态管理）
│   │   └── types/           # settings.ts（设置树类型）
│   ├── Student/             # 学生端页面
│   └── Authorization/       # 教师管理端
├── api/                     # HTTP 请求封装 (Axios)
├── components/Ros/          # ROS 通用组件
└── hooks/web/               # useRos, useTerminal
```

**关键技术点**:
- **ROS 通信**: `roslibjs` 通过 WebSocket 连接 ROS
- **3D 渲染**: 移植自 Lichtblick 的 Renderer-Extension 架构（见下文）
- **布局系统**: Golden Layout 2.6.0，支持面板拖拽、拆分、堆叠
- **状态管理**: Pinia (全局) + `panelState` store (Simulation 局部)
- **HTTP 请求**: 必须使用封装的 `service` from `@/axios`，严禁直接使用 `axios`

### 已实现的面板（panels/）

| 面板 | 目录 | 说明 |
|------|------|------|
| ROS3DViewer | `ROS3DViewer/` | Three.js 3D 可视化，核心面板 |
| ContainerTerminal | `ContainerTerminal/` | 容器终端（xterm.js） |
| GzWebViewer | `GzWebViewer/` | Gazebo Web iframe 嵌入 |
| WorkspacePanel | `WorkspacePanel/` | 文件树 + 代码编辑器 |
| KeyboardControl | `KeyboardControl/` | 键盘控制机器人运动 |
| RosoutPanel | `RosoutPanel/` | ROS 日志输出面板 |
| CameraPanel | `CameraPanel/` | 摄像头视频流面板 |

### 后端架构

```
edubot-twin-server/app/
├── main.py                   # FastAPI 入口，含 lifespan 后台任务
├── api/v1/endpoints/
│   ├── student/              # container, terminal, files, simulation, exams, tasks, experiments
│   ├── teacher/              # containers, students, monitor, exams, experiments, env_bundles, file_bundles
│   └── common/               # auth（登录、Token、路由权限）, bundle_files_router
├── core/                     # security, docker_client, container_manager, port_allocator, logger,
│                             #   container_lifecycle, sidecar_manager, snapshot_copier, workspace_snapshot,
│                             #   readiness_checker, result_parser, final_score_calculator, system_entrypoint, path_policy
├── services/                 # 业务逻辑层 (bundle_file_service)
├── models/                   # SQLAlchemy ORM: container, student, exam, exam_attempt, experiment,
│                             #   simulation_task, container_config, container_metrics
├── schemas/                  # Pydantic 数据验证
├── crud/                     # 数据库操作层
└── db/                       # 数据库配置
```

**后端 lifespan 后台任务**（`main.py` 中通过 `@asynccontextmanager` 管理）:
1. **心跳超时容器清理** — 每 60s 扫描，停止心跳超时（120s）的容器
2. **性能指标采集** — 每 10s 并发采集所有运行中容器的 CPU/内存指标
3. **历史数据清理** — 每 24h 清理 7 天前的指标数据
4. **孤儿容器 reconcile** — 每 5min 三阶段清洗（僵死状态回收 → DB-Docker 校准 → Docker→DB 反向清洗）
5. **Sidecar 超时扫描** — 检测并清理超时的 sidecar 容器

启动时还会执行：孤儿仿真任务回收、孤儿容器 reconcile。

## ROS3D Renderer 架构（重要）

本项目的 `ROS3DViewer` 采用移植自 Lichtblick 的 Renderer-Extension 架构，详细文档见 `panels/ROS3DViewer/CLAUDE.md`。

### 核心原则

1. **解耦设计**: `Renderer` 不依赖 `roslib`，通过 `addMessageEvent()` 接收标准化数据
2. **桥接模式**: `index.vue` 作为桥接层，负责 ROS 连接和消息注入
3. **扩展注册**: 所有 3D 功能都是 `SceneExtension`，必须在 `useRenderer.ts` 的 `createExtensionConfig()` 中显式注册
4. **按需渲染**: 状态变化后必须调用 `queueAnimationFrame()` 触发渲染
5. **双向同步**: 3D 交互 ↔ 设置面板，浮点数必须 `round` 处理防止抖动

### 消息注入格式

```typescript
renderer.addMessageEvent({
  topic: '/scan',
  schemaName: 'sensor_msgs/LaserScan',
  message: rosMessage,
  receiveTime: BigInt(Date.now()) * 1000000n  // 纳秒精度
})
```

### 已实现的 SceneExtensions

- **Grids**: 网格地面
- **FrameAxes**: TF 坐标系
- **LaserScans**: 激光雷达点云（**标准参考实现**）
- **PointClouds**: PointCloud2，支持多种颜色模式、decayTime
- **OccupancyGrids**: 占据栅格地图（DataTexture 渲染，需 polygonOffset）
- **Markers / TopicMarkers**: visualization_msgs/Marker(Array)，12 种类型
- **Poses / PoseArrays**: 姿态可视化
- **Polygons**: 多边形
- **PublishClickTool**: 3D 场景点击发布 (goal/point/pose_estimate)
- **SceneSettings**: 全局场景设置

## 角色与路由系统

### 测试账号

| 用户名  | 密码    | 角色    | 说明 |
|---------|---------|---------|------|
| admin   | admin   | admin   | 超级管理员 |
| test    | test    | test    | 测试账号 |
| student | student | student | 学生账号，仅学生工作台 |

### 路由配置原则（重要）

本项目使用**前端动态路由 + 后端权限控制**，新增路由必须同时修改以下位置：

1. **前端路由定义**: `src/router/index.ts` 的 `asyncRouterMap`
2. **前端 Mock 数据**: `mock/role/index.mock.ts` 中对应角色的路由列表（**开发环境使用**）
3. **后端路由权限**: `app/api/v1/endpoints/common/auth.py` 的 `get_user_routes()` 中对应角色的路径列表（**生产环境使用**）

**常见错误**: 只在前端定义了路由，但 mock 或后端未返回该路径，导致用户无法访问。父路由和子路由都必须添加。

```bash
# 调试：验证后端是否返回了新路径
curl "http://localhost:8000/api/v1/auth/routes?role=student"
```

详细说明见 `.claude/rules/router-map-guidance.md`。

## 考试系统架构

考试评测是核心业务，涉及以下关键模块：

- **考试管理** (`exams.py`, `exam.py` model): 考试 CRUD、状态机（draft → active → finished）
- **考试尝试** (`exam_attempts.py`, `exam_attempt.py` model): 学生参加考试、交卷、评分
- **环境快照** (`exam_env_snapshots.py`, `exam_file_snapshots.py`): 考试环境的文件/配置快照
- **评分** (`exam_eval_scripts.py`, `final_score_calculator.py`, `result_parser.py`): 自动化评分脚本与结果解析
- **面板策略** (`path_policy.py`): 考试期间面板锁定与白名单控制
- **考试目录**: `data/exam_artifacts/`, `data/exam_submissions/`，注意文件所有权问题（见 `fix_exam_dir_ownership.sh`）

## 开发规范

### TypeScript / Vue

- 为 ROS Message 定义 Interface，严禁 `any`
- 使用 Composition API + `<script setup lang="ts">`
- Props 定义使用 `propTypes` from `@/utils/propTypes`，而非裸 `defineProps<T>()`
- `pnpm ts:check` 必须通过
- 文件命名：`.vue` 文件使用 PascalCase

### 样式系统

- **BEM (Less)**: 复杂组件（如 RosViewer）
- **Atomic CSS (UnoCSS)**: 布局和间距
- **样式隔离**: 使用 `useDesign` Hook 生成前缀（默认 `v-`）
- **颜色**: 严禁硬编码 hex 值，使用 Element Plus CSS 变量（`var(--el-color-primary)`, `var(--el-bg-color)` 等）

### Python

- 数据结构定义为 Pydantic Schema 强类型
- 遵循 RESTful 风格，端点文件不超过 200 行
- CRUD 层与 API 层分离

### Git 提交规范

遵循 Conventional Commits（中文提交信息）：`feat`、`fix`、`refactor`、`docs`、`style`、`perf`

## 常见任务

### 添加新的 SceneExtension

1. 在 `extensions/` 创建扩展类，继承 `SceneExtension`
2. 实现 `getSubscriptions()`、`settingsNodes()`、`handleSettingsAction()`、`startFrame()`
3. 在 `composables/useRenderer.ts` 的 `createExtensionConfig()` 中注册
4. 在 `index.vue` 订阅 ROS Topic 并调用 `renderer.addMessageEvent()`

> ⚠️ `handleSettingsAction` 必须同时处理 `path.length === 2`（眼睛图标 visible 切换）和 `path.length === 3`（字段更新），详见 `.claude/rules/ros3dviewer-extension-guidance.md`。

### 添加仿真工作台面板

详见 `.claude/rules/simulation-panel-guidance.md`。关键步骤：创建 `panels/<Name>/index.vue` 和 `settings.ts`，然后在 `panels/registry.ts` 注册。

### 添加后端 API 端点

1. `app/models/` → ORM 模型
2. `app/schemas/` → Pydantic Schema
3. `app/crud/` → CRUD 操作
4. `app/api/v1/endpoints/` 对应模块 → 路由文件
5. 模块 `__init__.py` → `include_router` 注册

## 技术债务与已知问题

1. **API_ARCHITECTURE.md 过时**: 文档中标记为"待实现"的端点大部分已实现，但文档未更新
2. **GzWeb 集成**: iframe 嵌入，通信能力有限
3. **数据库迁移**: 当前 SQLite（根目录 `edubot.db`），生产需切换 PostgreSQL；迁移依赖手动 `migrate_db.sh`
4. **前端启停脚本缺失**: `start_web.sh` 尚未创建
5. **考试文件所有权**: sidecar 容器可能以 root 创建文件，需定期运行 `fix_exam_dir_ownership.sh`

## 相关文档

- ROS3DViewer 扩展开发: `panels/ROS3DViewer/CLAUDE.md`（内含详细开发指南和内存管理规范）
- 扩展开发规范: `.claude/rules/ros3dviewer-extension-guidance.md`
- 面板添加指南: `.claude/rules/simulation-panel-guidance.md`
- 路由添加指南: `.claude/rules/router-map-guidance.md`
- 前端编码规范: `.agent/rules/overall-guidance.md`
- API 架构设计: `edubot-twin-server/API_ARCHITECTURE.md`（⚠️ 部分内容过时）
