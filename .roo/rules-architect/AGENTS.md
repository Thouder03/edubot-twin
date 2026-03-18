# 架构模式规则（仅非显而易见内容）

## Renderer-Extension 解耦架构

**关键约束**：`Renderer` 类不直接依赖 `roslib`
- `index.vue` 作为桥接层订阅 ROS Topics
- 通过 `addMessageEvent()` 注入标准化消息
- 扩展必须在 `useRenderer.ts` 显式注册才能生效

## 非连续渲染模式

**性能设计**：Three.js 场景不是 `requestAnimationFrame` 循环
- 状态变化时必须调用 `queueAnimationFrame()` 触发单次渲染
- 避免不必要的 GPU 开销

## 设置树 JSON 驱动 UI

**扩展性设计**：面板设置 UI 由 JSON 描述生成
- `buildSettingsTree()` 返回配置对象
- `PanelSettings.vue` 通用渲染器解析 JSON
- 新面板无需编写 UI 组件代码

## 双重路由配置约束

**权限架构**：前端路由 + 后端权限列表
- `asyncRouterMap` 定义所有可能路由
- `mock/role/index.mock.ts` 控制角色可见路由
- 缺一不可，否则 404 或权限错误

## Monorepo 虚拟环境布局

**非标准结构**：`.venv/` 在项目根，但后端代码在子目录
- 命令必须从 `edubot-twin-server/` 运行
- 使用 `../.venv/bin/python` 访问虚拟环境
