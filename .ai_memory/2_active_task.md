# 当前任务状态

## SDD 第一期：GzWeb iframe 嵌入 + 基础仿真控制 ✅ 已完成

- [x] gzweb: `embed.html` + `embed-bridge.js` (postMessage L1/L2 桥接)
- [x] 前端: `types.ts` (TypeScript 类型契约)
- [x] 前端: `useGzBridge.ts` (Simulation/composables/ 下的模块级单例 composable)
- [x] 前端: `GzWebViewer/index.vue` (占位 → iframe 嵌入 + 连接遮罩)
- [x] 前端: `settings.ts` (showCollisions / showOrbitIndicator)
- [x] 前端: `SimControlBar.vue` (状态灯 + 控制按钮 + 时间显示)
- [x] 前端: `SimulationHeader.vue` (集成 SimControlBar)
- [x] `vue-tsc --noEmit` 编译零错误

## Bug 修复

- [x] **[BUG] gz:showCollisions 功能无效**
  - 根因：直接赋值 `scene.showCollisions = ...` 属性，只更新了状态标志，未触发场景遍历
  - 修复：改为调用 `scene.showCollision(show)` **方法**，该方法遍历场景所有 COLLISION_VISUAL 对象并设置子 Mesh 可见性
  - 修改文件：`gzweb/http/client/js/embed-bridge.js`、`gzweb/gz3d/client/js/embed-bridge.js`、文档 `sdd-gzweb-proxy-integration.md`

## 下一步

- [ ] 等待用户人工验收 gz:showCollisions 修复效果
