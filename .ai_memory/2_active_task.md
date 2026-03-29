# 当前任务状态

## 最新进展：文件树 Bug 修复 (2026-03-29)

### 已修复的三个 Bug
**文件：** `FileTreeContainer.vue`

**Bug 1 - 文件打不开**：
- 根因：旧代码用 `@click` 绑定在 `FileTreeNodeRenderer` 上，但 `@he-tree/vue` 会拦截拖拽相关的鼠标事件，导致 click 不触发
- 修复：改用 he-tree 官方的 `@click:node` 事件，回调参数是 `stat` 对象（`.data` 包含节点数据）

**Bug 2 - 文件夹打不开**：
- 根因：同 Bug 1，click 事件被 he-tree 拦截，导致 `onSelectFile` → `toggleNodeExpand` 无法触发
- 修复：同 Bug 1（`@click:node` 统一处理点击）

**Bug 3 - 拖拽无法移动文件**：
- 根因：旧代码监听 `@drop` 事件，但 he-tree 实际发出的是 `@after-drop`（无参数）
- 旧代码的 `stat.dragNode?.data` 等属性路径全部错误
- 修复：改用 `@after-drop` + 从 `dragContext`（`import { dragContext } from '@he-tree/vue'`）读取拖拽信息
  - `dragContext.dragNode.data` = 被拖动节点数据
  - `dragContext.targetInfo.parent?.data?.path` = 目标目录路径

### he-tree v2.10.x API 关键笔记
- 点击事件：`@click:node` → 回调参数 `(stat: Stat)`, `stat.data` 是节点数据
- 拖拽完成：`@after-drop` → 无参数，从 `dragContext` 读取
- `dragContext.targetInfo` 类型是 `StartInfo { parent: Stat | null, dragNode: Stat, ... }`
- `eachDroppable` 参数是 `Stat`，通过 `stat.data` 访问节点

## 下一步行动
- [ ] 等待分配新功能
