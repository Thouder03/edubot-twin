# ROS3D Viewer Panel

该面板为 `/home/ubuntu20/lichtblick/` 下的 lichtblick 项目（Foxglove 的分支）的 3D 面板的移植版本。

## 架构概述

这是一个基于 Three.js 的 ROS 3D 可视化面板，用于实时渲染机器人传感器数据和状态信息。

### 核心组件

- **Renderer** ([core/Renderer.ts](core/Renderer.ts)) - 主渲染器，管理 Three.js 场景、相机、渲染循环
- **SceneExtension** ([core/SceneExtension.ts](core/SceneExtension.ts)) - 扩展基类，所有可视化功能都继承此类
- **TransformTree** ([core/transforms/TransformTree.ts](core/transforms/TransformTree.ts)) - TF 坐标变换树，处理 ROS 坐标系转换
- **SettingsManager** ([core/SettingsManager.ts](core/SettingsManager.ts)) - 设置面板管理器

### 目录结构

```
ROS3DViewer/
├── core/              # 核心系统代码
│   ├── Renderer.ts    # 主渲染器
│   ├── SceneExtension.ts  # 扩展基类
│   ├── transforms/    # 坐标变换系统
│   ├── camera.ts      # 相机控制
│   └── ...
├── extensions/        # 各类可视化扩展
│   ├── Markers.ts     # ROS Marker 可视化
│   ├── PointClouds.ts # 点云可视化
│   ├── LaserScans.ts  # 激光扫描可视化
│   └── markers/       # Marker 子类型实现
├── composables/       # Vue 组合式函数
│   ├── useRenderer.ts # 渲染器集成
│   ├── useThreeScene.ts # Three.js 场景管理
│   └── ...
└── index.vue          # 主 Vue 组件
```

## 关键概念

### 1. SceneExtension 扩展系统

所有可视化功能都通过 `SceneExtension` 实现，每个扩展负责：

- 订阅特定 ROS 话题
- 将消息数据转换为 Three.js 对象
- 管理自己的设置项
- 处理坐标变换

**示例扩展：**

- `Markers` - 可视化 `visualization_msgs/Marker`
- `PointClouds` - 可视化 `sensor_msgs/PointCloud2`
- `LaserScans` - 可视化 `sensor_msgs/LaserScan`
- `Poses` - 可视化 `geometry_msgs/PoseStamped`

### 2. Renderable 对象

`Renderable` 是带有坐标系信息的 Three.js 对象，会自动根据 TF 树更新位置。

### 3. 坐标变换流程

```
消息坐标系 (frame_id)
  → TransformTree 查找变换
  → Fixed Frame (通常是 map/odom)
  → Render Frame (相机参考系)
  → 最终渲染位置
```

## 开发指南

### 添加新的可视化扩展

1. 在 `extensions/` 目录创建新文件，继承 `SceneExtension`
2. 实现必要方法：
   - `constructor()` - 初始化，调用 `this.add()` 添加 Three.js 对象
   - `settingsNodes()` - 返回设置项配置
   - `handleSettingsAction()` - 处理设置项交互
   - `startFrame()` - 每帧开始时调用，更新可视化
3. 在 `Renderer.ts` 中注册扩展

### 修改现有扩展

**重要原则：**

- 所有 Three.js 对象的创建/销毁必须正确管理，避免内存泄漏
- 使用 `dispose()` 方法清理 GPU 资源（geometry、material、texture）
- 坐标变换通过 `updatePose()` 自动处理，不要手动设置 position/rotation
- 大量对象使用对象池（`ObjectPool`）复用，避免频繁创建销毁

### 常见模式

#### 1. 订阅话题并渲染

```typescript
export class MyExtension extends SceneExtension {
  public constructor(renderer: IRenderer) {
    super('my_extension', renderer)

    // 订阅话题
    renderer.addTopicSubscription('my_topic', this.handleMessage)
  }

  private handleMessage = (messageEvent: MessageEvent<MyMsg>) => {
    // 处理消息，更新 Three.js 对象
  }
}
```

#### 2. 使用 Renderable 自动处理坐标变换

```typescript
const renderable = new Renderable('object_id', this.renderer, {
  receiveTime: message.receiveTime,
  messageTime: message.message.header.stamp,
  frameId: message.message.header.frame_id,
  pose: somePose
  // ...
})
this.add(renderable)
this.renderables.set('object_id', renderable)
```

#### 3. 对象池复用

```typescript
// 获取或创建对象
const obj = this.pool.acquire()
// 使用对象
// ...
// 释放回池
this.pool.release(obj)
```

## 重要注意事项

### 性能优化

1. **按需订阅** - 只订阅用户启用的话题，避免不必要的数据处理
2. **LOD (Level of Detail)** - 大量对象时使用 LOD 系统降低渲染复杂度
3. **Instancing** - 相同几何体使用 `InstancedMesh` 批量渲染
4. **衰减时间 (Decay Time)** - 旧数据自动淡出并清理，避免无限累积

### 坐标系问题

- **ROS 坐标系**: 右手系，X 前 Y 左 Z 上
- **Three.js 坐标系**: 右手系，X 右 Y 上 Z 前
- 转换在 `core/ros.ts` 中处理，通常不需要手动转换
- 所有带 `frame_id` 的消息都会通过 TF 树自动变换

### 常见问题排查

1. **物体不显示**

   - 检查 TF 树是否包含该 frame_id
   - 检查物体是否在相机视野内
   - 检查 material 的 visible 属性
   - 使用浏览器开发工具查看 Three.js 场景树

2. **坐标变换错误**

   - 确认 Fixed Frame 设置正确
   - 检查 TransformTree 是否收到 TF 数据
   - 查看控制台的 "MISSING_TRANSFORM" 错误

3. **性能问题**
   - 减少点云密度或使用降采样
   - 启用 Decay Time 自动清理旧数据
   - 检查是否有内存泄漏（未 dispose 的对象）

### 内存管理

**必须 dispose 的资源：**

- `THREE.BufferGeometry`
- `THREE.Material`
- `THREE.Texture`
- `THREE.WebGLRenderTarget`

**示例：**

```typescript
public override dispose(): void {
  this.geometry.dispose()
  this.material.dispose()
  super.dispose()
}
```

## 核心文件说明

### Renderer.ts

主渲染器，负责：

- 管理 Three.js 场景、相机、渲染循环
- 注册和管理所有 SceneExtension
- 处理话题订阅和消息分发
- 管理设置树和用户交互

### SceneExtension.ts

扩展基类，提供：

- 自动坐标变换更新（通过 `updatePose()`）
- 设置项管理接口
- 生命周期钩子（`startFrame()`, `dispose()`）
- Renderable 对象管理

### TransformTree.ts

TF 坐标变换树，功能：

- 存储和查询坐标系之间的变换关系
- 支持时间插值
- 处理 `tf2_msgs/TFMessage` 消息

### 关键 Extensions

- **LaserScans.ts** - 激光扫描可视化，支持衰减时间和点云转换
- **PointClouds.ts** - 点云可视化，支持多种颜色模式
- **Markers.ts** - ROS Marker 可视化，支持所有标准 Marker 类型
- **Grids.ts** - 网格显示
- **FrameAxes.ts** - 坐标系轴显示

## 修改建议

### 修改代码时应该：

✅ **DO:**

- 阅读相关扩展的完整代码，理解现有逻辑
- 复用现有的工具函数和模式
- 正确处理资源释放，避免内存泄漏
- 测试坐标变换是否正确
- 考虑性能影响，特别是高频消息

❌ **DON'T:**

- 不要直接修改 `core/lichtblick-shim.ts`（这是上游兼容层）
- 不要绕过 TransformTree 手动计算坐标变换
- 不要在渲染循环中创建新对象（使用对象池）
- 不要忘记在 `dispose()` 中清理资源
- 不要假设消息一定有 `header.frame_id`（某些消息类型没有）

## 调试技巧

1. **启用 Three.js 调试工具**

   - 浏览器控制台输入 `window.__THREE_DEVTOOLS__` 查看场景树

2. **查看 TF 树状态**

   - 在 Renderer 中添加日志查看 `this.transformTree`

3. **性能分析**

   - 使用 Chrome DevTools Performance 面板
   - 关注 `startFrame()` 和消息处理函数的耗时

4. **消息数据检查**
   - 在扩展的消息处理函数中添加 `console.log`
   - 确认消息格式和数据是否符合预期

## 相关资源

- [Three.js 文档](https://threejs.org/docs/)
- [ROS 消息类型](http://wiki.ros.org/msg)
- [TF2 坐标变换](http://wiki.ros.org/tf2)
- [Lichtblick 原始项目](https://github.com/Lichtblick-Suite/lichtblick)
