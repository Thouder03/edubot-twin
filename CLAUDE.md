# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Edubot Twin 是一个面向移动机器人实训的数字孪生评测平台，采用 Monorepo 架构：
- **前端** (`edubot-twin-web`): Vue 3.5 + Vite 6 + TypeScript + Element Plus
- **后端** (`edubot-twin-server`): Python FastAPI + SQLAlchemy + SQLite
- **核心功能**: 基于 WebGL 的 ROS 3D 可视化、容器化仿真环境管理、在线教学评测

## 开发环境

### 前端开发

```bash
cd edubot-twin-web

# 安装依赖
pnpm install

# 启动开发服务器 (http://localhost:4000)
pnpm run dev

# 类型检查
pnpm ts:check

# 代码格式化
pnpm lint:eslint
pnpm lint:format

# 构建
pnpm build:pro    # 生产环境
pnpm build:dev    # 开发环境
pnpm build:test   # 测试环境
```

**要求**: Node.js >= 18.0.0, pnpm >= 8.1.0

### 后端开发

```bash
cd edubot-twin-server

# 安装依赖 (使用项目根目录的虚拟环境)
../.venv/bin/pip install -r requirements.txt

# 初始化数据库 (首次运行)
../.venv/bin/python init_db.py

# 启动开发服务器 (http://localhost:8000)
../.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# API 文档
# - Swagger UI: http://localhost:8000/docs
# - ReDoc: http://localhost:8000/redoc
```

## 核心架构

### 前端架构

**目录结构**:
```
edubot-twin-web/src/
├── views/
│   ├── Simulation/          # ★ 核心仿真工作台 (Golden Layout v2.6)
│   │   ├── Simulation.vue   # 主容器
│   │   ├── panels/          # 功能面板 (ROS3DViewer, Terminal, GzWeb)
│   │   ├── composables/     # useRenderer, useRosConnection
│   │   └── stores/          # 面板状态管理
│   ├── Student/             # 学生端页面
│   └── Authorization/       # 教师管理端
├── api/                     # HTTP 请求封装
├── components/Ros/          # ROS 通用组件
└── hooks/web/               # useRos, useTerminal
```

**关键技术点**:
- **ROS 通信**: 使用 `roslibjs` 通过 WebSocket 连接 ROS
- **3D 渲染**: 基于 `ros3djs` + Three.js，采用 Lichtblick Renderer 架构
- **布局系统**: Golden Layout 2.6.0 支持面板拖拽、拆分、堆叠
- **状态管理**: Pinia (全局) + 局部 stores (Simulation)

### 后端架构

**模块化分层设计**:
```
edubot-twin-server/app/
├── api/v1/endpoints/
│   ├── student/             # 学生模块 (CRUD, auth, exams)
│   ├── teacher/             # 教师模块 (容器管理, 资源分发)
│   └── common/              # 公共接口 (健康检查)
├── models/                  # SQLAlchemy ORM 模型
├── schemas/                 # Pydantic 数据验证
├── crud/                    # 数据库操作层
└── db/                      # 数据库配置
```

**安全特性**:
- 密码使用 bcrypt 哈希存储
- API 响应自动过滤敏感字段
- CORS 配置限制跨域访问

## ROS3D Renderer 架构 (重要)

本项目的 `ROS3DViewer` 采用移植自 Lichtblick 的 Renderer-Extension 架构：

### 核心原则

1. **解耦设计**: `Renderer` 类不直接依赖 `roslib`，通过 `addMessageEvent()` 接收标准化数据
2. **桥接模式**: `index.vue` 作为桥接层，负责 ROS 连接和消息注入
3. **扩展注册**: 所有 3D 功能 (网格、坐标系、雷达) 都是 `SceneExtension`，必须在 `useRenderer.ts` 的 `createExtensionConfig()` 中显式注册
4. **按需渲染**: 非连续渲染循环，状态变化时必须调用 `queueAnimationFrame()` 触发渲染
5. **双向同步**: 3D 交互 ↔ 设置面板的状态同步，浮点数必须 `round` 处理防止抖动

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
- **LaserScans**: 激光雷达点云
- **Markers**: visualization_msgs/Marker(Array)，支持 12 种类型
- **Poses / PoseArrays**: 姿态可视化 (axis/arrow/line 模式)
- **PublishClickTool**: 3D 场景点击发布 (goal/point/pose_estimate)

## 角色与路由系统

### 测试账号

| 用户名  | 密码    | 角色    | 说明                     |
|---------|---------|---------|--------------------------|
| admin   | admin   | admin   | 超级管理员，完整管理菜单 |
| test    | test    | test    | 测试账号，部分管理菜单   |
| student | student | student | 学生账号，仅学生工作台   |

### 双重配置原则 (重要)

每个角色的路由必须在两处配置：
1. `src/router/index.ts` 的 `asyncRouterMap` (静态路由)
2. `mock/role/index.mock.ts` 对应角色的路由列表 (动态路由)

**常见错误**: 只在 `asyncRouterMap` 中定义路由，但 mock 中未配置，导致用户无法访问。

## 开发规范

### TypeScript

- 为 ROS Message 定义 Interface (如 `Twist`, `Odometry`)，避免滥用 `any`
- 使用 Composition API + `<script setup>`
- 严格模式: `pnpm ts:check` 必须通过

### 样式系统

- **BEM (Less)**: 复杂组件 (如 RosViewer)
- **Atomic CSS (UnoCSS)**: 布局和间距
- **样式隔离**: 使用 `useDesign` Hook 生成前缀 (默认 `v-`)

### Git 提交规范

遵循 Conventional Commits:
- `feat`: 新功能
- `fix`: Bug 修复
- `refactor`: 重构
- `docs`: 文档更新
- `style`: 代码格式调整

## 常见任务

### 添加新的 SceneExtension

1. 在 `edubot-twin-web/src/views/Simulation/panels/ROS3DViewer/extensions/` 创建扩展类
2. 继承 `SceneExtension` 并实现 `startFrame()`, `handleSettingsAction()` 等方法
3. 在 `composables/useRenderer.ts` 的 `createExtensionConfig()` 中注册
4. 在 `index.vue` 中订阅对应的 ROS Topic 并调用 `renderer.addMessageEvent()`

### 添加后端 API 端点

1. 在 `app/models/` 创建 ORM 模型
2. 在 `app/schemas/` 创建 Pydantic Schema
3. 在 `app/crud/` 创建 CRUD 操作
4. 在 `app/api/v1/endpoints/` 对应模块创建路由
5. 在模块的 `__init__.py` 中注册路由

### 调试 ROS 连接

```typescript
// 在浏览器控制台查看 ROS 连接状态
console.log(ros.isConnected)

// 查看已订阅的 Topics
console.log(renderer.topics)

// 手动触发渲染
renderer.queueAnimationFrame()
```

## 项目记忆系统

项目使用 `.ai_memory/` 目录维护长期上下文：
- `1_project_context.md`: 核心知识库 (只读)
- `2_active_task.md`: 当前任务状态 (快照覆盖)
- `3_work_log.md`: 开发流水账 (追加)
- `0_archive_context.md`: 思维演变历史 (追加)

**注意**: 这些文件使用简体中文编写。

## 技术债务与已知问题

1. **GzWeb 集成**: 采用 iframe 嵌入，通信能力有限
2. **数据库迁移**: 当前使用 SQLite，生产环境需切换到 PostgreSQL
3. **Token 认证**: 前后端联调中，Token 存储和使用机制待完善
4. **容器管理**: Docker SDK 集成尚未完成

## 相关文档

- 前端 README: `edubot-twin-web/README.md`
- 后端 README: `edubot-twin-server/README.md`
- API 架构设计: `edubot-twin-server/API_ARCHITECTURE.md`
- ROS3D 面板差异: `edubot-twin-web/src/views/Simulation/3D_PANEL_DIFF_CN.md`
