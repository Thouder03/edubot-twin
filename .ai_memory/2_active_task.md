# 当前任务状态

## 最新任务：修复教师端文件树点击报错 (getFilesApi is not a function)

### 状态：✅ 已修复

---

## 核心工作内容记录

1. **Bug 定位**：
   - 用户反馈：教师端实验文件和环境管理页，点击文件夹显示“加载目录失败: props.getFilesApi is not a function”。
   - 追踪发现：教师端复用了学生端的 `FileTreeContainer.vue`，其中目录展开逻辑依赖于传入的 `getFilesApi().listFiles` 方法来实现懒加载。
   - 问题根源：教师端使用的 `useBundleWorkspace.ts`（扮演了兼容层角色）暴露了与其他模块一致的接口，但缺失了暴露 `getFilesApi` 的 mock。

2. **代码修改**：
   - 修改 `edubot-twin-web/src/views/Teacher/Experiments/composables/useBundleWorkspace.ts`。
   - 在其 `return` 中增加 `getFilesApi` 函数，模拟返回 `listFiles`。
   - 内部将 `listFiles` 请求代理到 `bundleListFiles` 并按照 `FileTreeContainer` 期望的结构（`{code:0, data: ...}`）返回，彻底解决了文件夹点击报错无法展开的问题。
