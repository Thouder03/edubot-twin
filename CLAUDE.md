# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Edubot Twin 是一个面向移动机器人实训的数字孪生评测平台，采用 Monorepo 架构：
- **前端** (`edubot-twin-web`): Vue 3.5 + Vite 6 + TypeScript + Element Plus
- **后端** (`edubot-twin-server`): Python FastAPI + SQLAlchemy + SQLite
- **核心功能**: 基于 WebGL 的 ROS 3D 可视化、容器化仿真环境管理、在线教学评测

## 开发环境

### scripts/ 规范

> ⚠️ 所有 Run & Debug 操作必须通过 `scripts/` 目录下的 `.sh` 脚本进行，严禁直接使用 `pnpm`、`uvicorn` 等命令。
> 该目录尚未创建——首次执行启停操作时，先在 `scripts/` 下创建对应脚本，再通过脚本执行。

### 前端常用命令（通过 scripts/ 封装后使用）

```bash
# 原始命令，仅作参考，请封装到 scripts/start_web.sh
cd edubot-twin-web
pnpm install          # 安装依赖
pnpm run dev          # 开发服务器 http://localhost:4000
pnpm ts:check         # 类型检查（提交前必须通过）
pnpm lint:eslint      # ESLint
pnpm lint:format      # Prettier
pnpm build:pro        # 生产构建
```

**要求**: Node.js >= 18.0.0, pnpm >= 8.1.0

### 后端常用命令（通过 scripts/ 封装后使用）

```bash
# 原始命令，仅作参考，请封装到 scripts/start_server.sh
cd edubot-twin-server
../.venv/bin/pip install -r requirements.txt  # 安装依赖
../.venv/bin/python init_db.py                # 初始化数据库（首次）
../.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# API 文档: http://localhost:8000/docs
```

## 核心架构

### 前端架构

```
edubot-twin-web/src/
├── views/
│   ├── Simulation/          # ★ 核心仿真工作台 (Golden Layout v2.6)
│   │   ├── Simulation.vue   # 主容器
│   │   ├── panels/          # 7 个功能面板（见下文）
│   │   ├── composables/     # useRenderer, useRosConnection
│   │   ├── stores/          # panelState（面板状态管理）
│   │   └── types/           # settings.ts（设置树类型）
│   ├── Student/             # 学生端页面
│   └── Authorization/       # 教师管理端
├── api/                     # HTTP 请求封装
├── components/Ros/          # ROS 通用组件
└── hooks/web/               # useRos, useTerminal
```

**关键技术点**:
- **ROS 通信**: `roslibjs` 通过 WebSocket 连接 ROS
- **3D 渲染**: 移植自 Lichtblick 的 Renderer-Extension 架构（见下文）
- **布局系统**: Golden Layout 2.6.0，支持面板拖拽、拆分、堆叠
- **状态管理**: Pinia (全局) + `panelState` store (Simulation 局部)

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
├── api/v1/endpoints/
│   ├── student/             # files, container, terminal, basic
│   ├── teacher/             # containers, students, monitor
│   └── common/              # auth（登录、Token、路由权限）
├── core/                    # security, docker_client, container_manager, port_allocator, logger
├── models/                  # SQLAlchemy ORM 模型
├── schemas/                 # Pydantic 数据验证
├── crud/                    # 数据库操作层
└── db/                      # 数据库配置
```

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
  receiveTime: BigInt(Date.now()) * 1000000n
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

本项目使用**后端驱动的动态路由**，路由权限由后端接口返回，新增路由必须同时修改两处：

1. **前端路由定义**: `src/router/index.ts` 的 `asyncRouterMap`
2. **后端路由权限**: `app/api/v1/endpoints/common/auth.py` 的 `get_user_routes()` 中对应角色的路径列表

**常见错误**: 只在前端定义了路由，但后端 `get_user_routes` 未返回该路径，导致用户无法访问。

```bash
# 调试：验证后端是否返回了新路径
curl "http://localhost:8000/api/v1/auth/routes?role=student"
```

详细说明见 `.claude/rules/router-map-guidance.md`。

## 开发规范

### TypeScript

- 为 ROS Message 定义 Interface，严禁 `any`
- 使用 Composition API + `<script setup>`
- `pnpm ts:check` 必须通过

### 样式系统

- **BEM (Less)**: 复杂组件（如 RosViewer）
- **Atomic CSS (UnoCSS)**: 布局和间距
- **样式隔离**: 使用 `useDesign` Hook 生成前缀（默认 `v-`）

### Git 提交规范

遵循 Conventional Commits（中文提交信息）：`feat`、`fix`、`refactor`、`docs`、`style`

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
4. `app/api/v1/endpoints/` 对应模块 → 路由
5. 模块 `__init__.py` → 注册路由

## 技术债务与已知问题

1. **scripts/ 未创建**: 违反全局规范，首次启动前需补建
2. **GzWeb 集成**: iframe 嵌入，通信能力有限
3. **数据库迁移**: 当前 SQLite，生产需切换 PostgreSQL
4. **Token 认证**: 前后端联调中，Token 存储机制待完善
5. **容器管理**: Docker SDK 集成尚未完成（`app/core/docker_client.py` 骨架已有）

## 相关文档

- ROS3DViewer 扩展开发: `panels/ROS3DViewer/CLAUDE.md`（内含详细开发指南和内存管理规范）
- 扩展开发规范: `.claude/rules/ros3dviewer-extension-guidance.md`
- 面板添加指南: `.claude/rules/simulation-panel-guidance.md`
- 路由添加指南: `.claude/rules/router-map-guidance.md`
- API 架构设计: `edubot-twin-server/API_ARCHITECTURE.md`
