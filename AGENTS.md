# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## 关键非标准配置

**Python 虚拟环境位置**: 在项目根目录 `.venv/`，不在 `edubot-twin-server/` 内
```bash
# 后端命令必须从 edubot-twin-server/ 运行，但使用根目录的 venv
cd edubot-twin-server
../.venv/bin/python init_db.py
../.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**前端开发服务器**: 运行在 `http://localhost:4000` (非标准 3000/5173)

## 路由系统双重配置陷阱

添加新路由必须在**两处**同时配置，否则用户无法访问：
1. `edubot-twin-web/src/router/index.ts` 的 `asyncRouterMap`
2. `edubot-twin-web/mock/role/index.mock.ts` 对应角色的路由列表

父路由和子路由都必须添加到 mock 中。

## ROS3D 扩展开发关键规则

**handleSettingsAction 必须处理两种 path 长度**（最常见 bug）：
- `path.length === 2`: 眼睛图标可见性切换 `['topics', '/scan']`
- `path.length === 3`: 字段值更新 `['topics', '/scan', 'pointSize']`

**扩展注册**: 新扩展必须在 `composables/useRenderer.ts` 的 `createExtensionConfig()` 中显式注册

**消息注入格式**: `receiveTime` 必须是 BigInt 纳秒精度
```typescript
renderer.addMessageEvent({
  topic: '/scan',
  schemaName: 'sensor_msgs/LaserScan',
  message: rosMessage,
  receiveTime: BigInt(Date.now()) * 1000000n  // 纳秒
})
```

**startFrame 与 RenderObjectHistory**: 使用 History 时不要调用 `super.startFrame()`，子节点 pose 由 `RenderObjectHistory.updatePoses()` 管理

**浮点数同步**: 3D 交互与设置面板同步时必须 `round()` 处理，防止抖动

## 样式系统

- 复杂组件使用 BEM (Less)
- 布局使用 UnoCSS 原子类
- 使用 `useDesign` Hook 生成前缀（默认 `v-`）

## 参考文档

详细规则见 `.agent/rules/` 目录：
- `ros3dviewer-extension-guidance.md` - ROS3D 扩展开发完整规范
- `router-map-guidance.md` - 路由配置详细说明
- `simulation-panel-guidance.md` - 仿真面板开发指南
