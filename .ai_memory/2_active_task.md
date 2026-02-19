# 当前任务状态

## 最近完成

- ✅ ROS3DViewer 集成 (渲染/TF/Grid/相机) — 2026-02-14
  - 落地 Lichtblick Renderer 架构
  - 实现 Three.js 场景与 ROS 消息桥接
  - 修复运行时渲染崩溃与性能问题
- ✅ 仿真页面架构重构（Settings Tree + Sidebar）— 2026-02-12
  - 将 Simulation 目录移至 `src/views/Simulation`
  - 引入 `panels/` 目录结构，模块化管理面板
  - 实现基于 `settings.ts` 的设置树定义
  - 实现 Flex 布局的 `SettingsSidebar`，支持拖拽调整宽度
  - 实现 ROS3DViewer 和 GzWebViewer 的基础配置集成

## 下一步待办

- [ ] GzWebViewer 嵌入 GzWeb iframe
- [ ] 仿真页面与后端 WebSocket 通信 (Docker 状态等)
- [ ] 根据 URDF 自动加载机器人模型 (RobotModel 扩展)
- [ ] 添加更多面板类型（Terminal、CodeEditor 等）
- [ ] 优化设置面板 UX（分组折叠、实时预览）
