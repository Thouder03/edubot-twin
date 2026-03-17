# 当前任务状态
- [x] 限制 3D 面板移动时的视角更新频率，解决卡顿问题
- [x] 修复“同步相机”选项，在开启时恢复实时更新
- [x] 分析并修复由于 `updateSettingsTree` 频繁触发导致 Vue 渲染器与 THREE 渲染器互相干涉造成严重卡顿的问题
- [x] 撤销对 OrbitControls 视角的节流限制，因为这会阻碍 render frame loop
- [x] 修复 `1s` 同步设置树带来的瞬间卡顿：对 `settingsTree` 通过 `markRaw` 剥离 Vue 深度响应劫持，消除 proxy 遍历导致的性能瓶颈
- [x] 在 `CameraStateSettings` 中增加 `isDragging` 鼠标拖拽状态检测，拖拽期间完全暂停 Vue 响应式数据同步，拖放结束后自动补发一次更新，实现绝对纯净的拖拽帧率。
