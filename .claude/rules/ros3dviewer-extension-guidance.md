---
description: "# ROS3DViewer 扩展开发规范  本规则适用于在 `src/views/Simulation/panels/ROS3DViewer/extensions/` 下开发或移植新扩展时。"
---

# ROS3DViewer 扩展开发规范

本规则适用于 `src/views/Simulation/panels/ROS3DViewer/extensions/` 下的扩展开发与移植。

---

## ⚠️ 关键规范：`handleSettingsAction` 必须处理两种 path 长度

**这是最常见的 bug 来源。** 扩展中的 `handleSettingsAction` 必须同时处理 **两种** 操作：

| `path.length` | 触发方式 | `path` 示例 | 含义 |
|---|---|---|---|
| `2` | 点击眼睛图标 | `['topics', '/scan']` | 话题可见性 (visible) 切换 |
| `3` | 修改字段值 | `['topics', '/scan', 'pointSize']` | 字段设置更新 |

### ❌ 错误写法（视图无法通过眼睛图标开关）

```typescript
public override handleSettingsAction = (action: SettingsTreeAction): void => {
  const path = action.payload.path
  // 只处理 length=3，眼睛图标（length=2）会被直接丢弃！
  if (action.action !== 'update' || !path || path.length !== 3) return

  this.saveSetting(path as string[], action.payload.value)
  // ...
}
```

### ✅ 正确写法（参照 LaserScans.ts 标准模式）

```typescript
public override handleSettingsAction = (action: SettingsTreeAction): void => {
  const path = action.payload.path
  if (action.action !== 'update') return
  if (path == undefined || path.length < 2 || path[0] !== 'topics') return

  const topicName = path[1]!

  // ── 1. 眼睛图标：visible 切换 (path.length === 2) ──────────────────────────
  if (path.length === 2) {
    const visible = action.payload.value as boolean
    const renderable = this.renderables.get(topicName)
    if (renderable) {
      renderable.userData.settings.visible = visible
      renderable.visible = visible          // ← 必须同时设置 THREE.Object3D 的 visible
    }
    this.renderer.updateConfig((draft) => {
      const prev = (draft.topics[topicName] ?? {}) as Partial<LayerSettings>
      draft.topics[topicName] = { ...prev, visible } as any
    })
    this.updateSettingsTree()             // ← 刷新设置树，让 UI 反映新状态
    return
  }

  // ── 2. 字段更新 (path.length === 3) ───────────────────────────────────────
  if (path.length !== 3) return

  this.saveSetting(path as string[], action.payload.value)

  const renderable = this.renderables.get(topicName)
  if (!renderable) return

  // 从 config 重建完整 settings（saveSetting 已写入 config）
  const prevSettings = this.renderer.config.topics[topicName] as Partial<LayerSettings> | undefined
  const settings = { ...DEFAULT_SETTINGS, ...prevSettings }
  renderable.userData.settings = settings   // ← 同步 userData，使 startFrame 获得最新值

  // 触发重新渲染
  renderable.updateXxx(
    renderable.userData.latestData,
    renderable.userData.latestOriginalMessage,
    settings,
    renderable.userData.receiveTime
  )
}
```

---

## startFrame 注意事项

若扩展使用了 `RenderObjectHistory`（多帧 decayTime 支持），**必须覆盖** `startFrame` 手动管理 pose 更新，参照 **LaserScans.ts 标准写法**。

### ❌ 错误写法（开启后不显示！）

```typescript
public override startFrame(...): void {
  for (const [topic, renderable] of this.renderables) {
    if (!renderable.userData.settings.visible) {
      renderable.removeFromParent()  // ← 严禁！隐藏时 dispose 会丢失数据
      renderable.dispose()           // ← 下次开启收不到新消息时永远空白
      this.renderables.delete(topic)
      continue
    }
    renderable.startFrame(...)
  }
}
```

### ✅ 正确写法（LaserScans.ts 标准模式）

```typescript
public override startFrame(currentTime: bigint, renderFrameId: string, fixedFrameId: string): void {
  // 只设置 visible 标志，不 dispose —— 数据保留在 renderable 中
  for (const renderable of this.renderables.values()) {
    renderable.visible = renderable.userData.settings.visible
    if (!renderable.visible) continue
    renderable.startFrame(currentTime, renderFrameId, fixedFrameId) // 更新子 History pose
  }
}
```

**原则**：
- 不可见时只设 `renderable.visible = false`，数据和 THREE 对象保留在内存中
- 重新开启时 `renderable.visible = true`，历史帧立刻恢复显示
- `super.startFrame()` 不要调用（基类的 updatePose 针对 HistoryRenderable 本身，而 History 内部的子节点 pose 由 `RenderObjectHistory.updatePoses()` 管理）


---

## 新扩展开发 Checklist

- [ ] `getSubscriptions()` — 订阅正确的 `schemaNames`，`filterQueue` 用于去重/decay 控制
- [ ] `settingsNodes()` — 每个话题生成一个 `SettingsTreeEntry`，设置 `node.handler = handler`
- [ ] `handleSettingsAction` — **同时处理** `path.length=2`（visible）和 `path.length=3`（字段）
- [ ] `startFrame()` — 若使用 History，覆盖并手动管理 visible 判断和 pose 更新
- [ ] 注册到 `useRenderer.ts` 的 `extensionsById`
- [ ] Z-fighting 处理 — 若渲染平面图层（如 OccupancyGrid），在材质上加 `polygonOffset: true, polygonOffsetFactor: 3, polygonOffsetUnits: 3`

---

## 参考实现文件

| 扩展 | 文件 | 特点 |
|---|---|---|
| LaserScan | `extensions/LaserScans.ts` | **标准参考**，handleSettingsAction 最完整 |
| PointCloud2 | `extensions/PointClouds.ts` | 含 Stixel、decayTime History、fieldReaders |
| OccupancyGrid | `extensions/OccupancyGrids.ts` | DataTexture 渲染、polygonOffset 修复 |
| Markers | `extensions/Markers.ts` | 多类型 Marker 消息分发 |
