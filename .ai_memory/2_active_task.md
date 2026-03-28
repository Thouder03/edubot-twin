# 当前任务状态

## 当前阶段：第六期仿真页面功能面板 - 已完成 ✅

## 已完成事项（本轮）

### 后端
- **新建 `terminal.py`** (`/api/v1/students/terminal/ws`): WebSocket 终端端点，JWT 从 query param 鉴权，asyncio 双向透传 docker exec stdin/stdout
- **`student/__init__.py`**: 注册 terminal 路由（前缀 `/terminal`）

### 前端
- **`Simulation.vue`**: 新增 `containerStatus ref` + `provide('containerStatus')`；心跳和初始化均同步状态
- **新建 `KeyboardControl/settings.ts`**: 线速度、角速度、cmd_vel Topic 配置
- **新建 `KeyboardControl/index.vue`**: WASD/方向键控制、急停、聚焦激活、容器状态联动
- **新建 `ContainerTerminal/settings.ts`**: 字体大小、主题配置
- **新建 `ContainerTerminal/index.vue`**: xterm.js + FitAddon、WebSocket 终端、断连重连、状态联动
- **`registry.ts`**: 注册 KeyboardControl、ContainerTerminal
- **`predefined-layouts.ts`**: 新增"全功能工作台"四面板预设，availablePanels 扩充

### 依赖
- 安装 `xterm@^5.3.0`、`@xterm/addon-fit@^0.11.0`（pnpm）

## 关键说明
- containerStatus 通过 provide/inject 实现跨面板状态联动，无需引入新 Pinia store
- 键盘控制面板仅在面板聚焦时监听键盘，避免干扰终端输入
- WebSocket Token 放 query param（WebSocket 规范不允许自定义 Header）
- 后端 AsyncSessionLocal 是正确的会话工厂名称（非 async_session_maker）

## 下一步（候选）
- P1：基础日志面板（LogViewer）
- 前端启动验证：`npm run dev`
- 手动验收：四面板全功能工作台联调测试
