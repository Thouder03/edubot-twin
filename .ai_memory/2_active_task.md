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
- [ ] 等待用户人工验收
