# 当前任务状态

## 目标
已完成本次会话全部核心目标：Poses/PoseArrays/PublishClickTool/PublishSettings 四个 SceneExtension 的完整实现。

## 已完成

- [x] `Poses.ts`：支持 `geometry_msgs/PoseStamped` 和 `PoseWithCovarianceStamped`，axis/arrow/协方差球三种显示模式
- [x] `PoseArrays.ts`：支持 `geometry_msgs/PoseArray` 和 `nav_msgs/Path`，对象池 + 渐变色优化
- [x] `PublishClickTool.ts`：3D 视图点击发布工具，状态机 + 鼠标预览（小球/箭头）
- [x] `PublishSettings.ts`：Settings Tree publish 节点（type/topic/协方差偏差动态字段）
- [x] `IRenderer.ts`：添加 `RendererConfig.publish?` 字段、`publishClickTool` 接口属性
- [x] `Renderer.ts`：PublishClickTool 初始化顺序前移（先于 sceneExtensionConfig 循环）
- [x] `useRenderer.ts`：onPublish 回调注入模式；startPublish/stopPublish 暴露
- [x] `ROS3DToolbar.vue`：右上角工具栏独立组件（解耦自 index.vue）
- [x] Bug 修复：切换设置面板类型后按钮文字实时同步（renderer.on('configChange') 驱动）
- [x] Bug 修复：刷新页面后可直接切换回点类型（构造函数读取配置初始化 publishClickType）

## 下一步

- [ ] 实现 `nav_msgs/OccupancyGrid`（地图）可视化扩展
- [ ] 端到端测试 Pose 发布功能（连接真实 ROS 环境）
- [ ] 考虑将 VISUALIZABLE_SCHEMAS 提取为常量文件，避免分散维护
