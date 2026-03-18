# 调试模式规则（仅非显而易见内容）

## ROS3D 渲染调试

**浏览器控制台命令**（非标准调试方式）：
```javascript
// 手动触发渲染（非连续渲染循环）
renderer.queueAnimationFrame()

// 检查已订阅 Topics
console.log(renderer.topics)

// 查看 TransformTree 状态
console.log(renderer.transformTree)
```

## 可见性问题排查

**常见陷阱**：扩展中 `renderable.visible` 和 `renderable.userData.settings.visible` 必须同时设置，只设一个会导致状态不同步。

## 路由 404 调试

**双重配置检查**：
```bash
# 1. 检查前端路由定义
grep -r "path.*simulation" edubot-twin-web/src/router/

# 2. 检查 mock 路由权限
grep -r "simulation" edubot-twin-web/mock/role/
```

## 后端数据库调试

数据库文件位置：`edubot-twin-server/edubot_twin.db`（SQLite，可用 DB Browser 直接打开）

## Golden Layout 状态检查

布局状态存储在 localStorage，key 为 `golden-layout-state`，清除可重置布局。
