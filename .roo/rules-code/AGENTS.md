# 代码模式规则（仅非显而易见内容）

## ROS3D 扩展开发陷阱

**handleSettingsAction 双路径处理**（最常见 bug）：
```typescript
// 必须同时处理 path.length === 2 (visible切换) 和 === 3 (字段更新)
if (path.length === 2) {
  // 眼睛图标点击，必须同时设置 renderable.visible 和 THREE.Object3D.visible
  renderable.userData.settings.visible = visible
  renderable.visible = visible
  this.updateSettingsTree()  // 必须调用，否则 UI 不更新
}
```

**RenderObjectHistory 使用时禁止调用 super.startFrame()**：
- History 内部子节点的 pose 由 `RenderObjectHistory.updatePoses()` 管理
- 调用 super 会导致 pose 更新冲突

**消息注入 receiveTime 必须是纳秒 BigInt**：
```typescript
receiveTime: BigInt(Date.now()) * 1000000n  // 不是毫秒！
```

## 路由配置双重陷阱

添加路由必须在**两处**同时配置：
1. `src/router/index.ts` 的 `asyncRouterMap`
2. `mock/role/index.mock.ts` 对应角色数组

**父路由和子路由都要加**，否则 404。

## 后端命令特殊路径

虚拟环境在项目根 `.venv/`，但命令从 `edubot-twin-server/` 运行：
```bash
cd edubot-twin-server
../.venv/bin/python init_db.py  # 注意 ../ 前缀
```

## 样式隔离

使用 `useDesign` Hook 生成 BEM 前缀（默认 `v-`），不要硬编码类名前缀。
