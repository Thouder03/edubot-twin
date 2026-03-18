# 开发流水账

## 2026-02-07

### 后端 API 架构重构

- **时间**: 21:55 - 00:30
- **内容**: 将单文件 API 架构重构为模块化分层架构
  - 创建 `student/` 模块目录 (basic.py + 预留 6 个子模块)
  - 创建 `teacher/` 占位模块
  - 创建 `common/` 公共功能模块
  - 更新主路由聚合器 `api.py`
  - 删除旧的单文件 `student.py`
- **验证**: 所有 API 端点正常运行,服务器自动重启成功
- **文档**: 创建 `API_ARCHITECTURE.md` 架构设计文档

### FastAPI 学生 API 后端实现

- **时间**: 18:39 - 21:14
- **内容**:
  - 创建异步 SQLAlchemy 数据库层 (database.py, base.py)
  - 创建学生 ORM 模型 (8 个核心字段)
  - 实现学生 CRUD 操作 (异步, bcrypt 密码哈希)
  - 实现 5 个 RESTful API 端点 (增删改查+列表分页)
  - 配置 FastAPI 主应用 (CORS、生命周期事件)
  - 创建数据库初始化脚本 (4 个示例学生)
- **解决问题**:
  - Python 3.8 类型注解兼容性 (改用 Optional)
  - bcrypt 与 passlib 版本冲突 (改用原生 bcrypt API)
  - email-validator 缺失依赖
- **成果**: API 服务器运行在 http://localhost:8000

## 2026-02-06

### 学生首页功能开发

- 添加学生首页状态卡片和操作按钮
- 实现图标系统和悬停动画
- 创建 API 接口和 Mock 数据
- 添加骨架屏加载状态

### 路由权限系统修复

- 修复学生登录 404 问题
- 完善学生路由 Mock 配置
- 实现动态首页重定向逻辑

### 前端接口对接

- **时间**: 01:46
- **内容**: 前端已修改登录接口地址
  - 从 `/mock/user/login` 改为 `/api/v1/students/auth/login`
  - 文件: `edubot-twin-web/src/api/login/index.ts`
- **下一步**: 前后端联调测试

### 统一登录端点重构

- **时间**: 13:50-13:53
- **内容**: 重构认证架构,合并学生和教师登录
  - 创建 `app/api/v1/endpoints/common/auth.py` (统一认证)
  - 删除 `app/api/v1/endpoints/student/auth.py` (学生独立认证)
  - 新端点: `POST /api/v1/auth/login` (自动识别角色)
  - 前端接口已同步更新
- **测试**: 所有端点测试通过,旧端点已删除

### 前后端对接问题修复 & 跨域配置

- **时间**: 18:10
- **内容**: 修复登录流程，解决前端无法跳转问题
  - **后端**: 重构 `LoginResponse`，增加 `code: 0` 字段以通过 Axios 拦截器校验
  - **后端**: 允许前端 `4000` 端口跨域访问
  - **前端**: 修正 `vite.config.ts` 代理配置，透传 `/api` 路径
  - **前端**: 修正 Mock 数据，兼容 `student001` 用户名的路由权限
- **结果**: 前端登录成功并正确跳转至学生首页

## 2026-02-10 ~ 2026-02-11

### 统一认证接口错误响应格式

- **时间**: 2026-02-10 17:00
- **内容**: 重构认证模块错误处理机制
  - 将 HTTPException 改为 JSONResponse (HTTP 200)
  - 统一错误响应结构: `{ code, message, data: null }`
  - 规范化错误码: 500(密码错误), 403(禁用), 401(Token失效), 404(不存在), 400(未知角色)
  - 新增文档: API_ANALYSIS.md, ROUTING_ANALYSIS.md
- **影响**: 前端 Axios 拦截器可统一处理所有认证错误

### 前端动态路由模式及后端路由权限接口

- **时间**: 2026-02-10 23:00
- **内容**: 实现基于角色的动态路由
  - **后端**: 新增 `GET /api/v1/auth/routes` 接口，返回角色对应的路由列表
  - **后端**: 新增 RoutesResponse Schema
  - **前端**: 启用前端动态路由模式 (serverDynamicRouter: false)
  - **前端**: 登录成功后通过 role 字段获取路由权限，替代基于 username 的判断
  - **前端**: 移除 Student 路由的 alwaysShow 配置
- **新增文档**: route_modes_analysis.md (路由模式分析)
- **结果**: 学生登录后正确加载学生路由，避免权限泄露

### JWT Token 持久化认证及"记住登录"功能

- **时间**: 2026-02-11 00:30
- **内容**: 用 Token 替代明文密码存储，提升安全性
  - **后端**: 已有 `POST /api/v1/auth/token` (生成 JWT) 和 `GET /api/v1/auth/me` (验证 Token)
  - **前端类型**: 移除 `UserLoginType.password` 字段
  - **前端 API**: 新增 `getTokenApi` 和 `getUserInfoByTokenApi`
  - **前端登录流程**: 成功后立即获取并存储 JWT Token，只保存 username
  - **前端路由守卫**: 检测到 Token 时自动验证并恢复用户信息，实现免登录
  - **前端初始化**: 只自动填充用户名，不填充密码
- **安全提升**: localStorage 不再存储明文密码，改为存储有时效的 JWT Token
- **用户体验**: Token 有效期内刷新页面自动登录

### 后端 API 响应格式统一化

- **时间**: 2026-02-11 01:00
- **内容**: 将所有后端 API 统一为 `{ code, data, message }` 格式
  - **新建**: `app/schemas/common.py` (ApiResponse[T] 泛型 Schema)
  - **简化**: `app/schemas/auth.py` (移除自定义 Response，改用 ApiResponse)
  - **修改认证端点**: login, token, me, routes (4个)
  - **修改学生端点**: 列表、单个、创建、更新、删除 (5个)
  - **错误处理**: 所有 HTTPException 改为 JSONResponse
- **验证**: curl 测试所有接口，格式完全统一
- **影响**: 前端无需修改代码，Axios 拦截器自动处理统一格式

## 2026-02-14

### ROS3DViewer 渲染修复与功能完善

- **时间**: 15:30
- **内容**: 修复 ROS3DViewer 面板的运行时渲染问题，实现网格显示和 TF 坐标系同步
  - **PanelSettings 修复**: 处理 `node.fields` 为 undefined 导致的崩溃问题
  - **性能优化**: 对 `settingsTreeChange` 事件进行 `requestAnimationFrame` 节流，避免渲染风暴
  - **Grid 渲染**:
    - 完整实现 `RenderableLineList` (Three.js `LineSegments`)，替换原有的空桩
    - 在 `defaultRendererConfig` 中添加默认 Grid 层配置
    - 注册 `Grids` 扩展
  - **相机控制**: 修复 `OrbitControls` 虽然触发事件但未调用 `queueAnimationFrame` 导致画面不刷新的问题
  - **TF 显示**:
    - 注册 `FrameAxes` 扩展
    - 在 `index.vue` 实现 ROS `/tf` & `/tf_static` 消息到 Renderer `addMessageEvent` 的桥接
- **验证**: 浏览器中 Grid 可见，相机可缩放/旋转，连接 ROS 后 TF 坐标系数据流打通
- **架构确认**: 成功落地 Lichtblick Renderer-Extension 架构，证明该架构在 Vue 3 + TypeScript 环境下的可行性

### Settings Panel UX 优化与交互修复

- **时间**: 20:30
- **内容**: 完成 Phase 5 用户体验优化
  - **视觉重构**: 实现 Lichtblick 风格的 Accordion 折叠面板，优化输入框布局（紧凑型+左对齐Label）
  - **功能修复**:
    - 修复 WebSocket 断开时各订阅未正确清理导致的 Console 报错
    - 实现 \`vec3\` 类型输入组件，解决 Target/TF Offset 无法编辑问题
    - 修复 \`undefined\` 分组标题显示
  - **双向同步**:
    - 实现 View -> Settings 的实时参数同步（OrbitControls -> Config）
    - 实现 Settings -> View 的即时应用（Config -> CameraState）
    - 优化数值显示精度（保留 3 位小数）
- **状态**: ROS3DViewer 核心功能与交互体验已达到交付标准

### 设置面板空内容修复

- **时间**: 20:50
- **内容**: 修复设置面板部分分组展开后无内容的问题
  - **原因**: 原实现仅遍历了顶层节点的 \`fields\`，忽略了拥有嵌套子节点 (\`children\`) 的分组（如 Custom Layers）。
  - **修复**: 在 \`PanelSettings.vue\` 中实现了递归展平逻辑 (Recursive Flatten)，将所有嵌套子节点的字段提升到顶层分组显示，并自动添加父级 Label 前缀（如 \`Layer 1 - Visible\`）。
  - **同步**: 更新 \`SettingsTreeNode\` 类型定义，添加 \`children\` 属性支持。

## 2026-02-18
- 分析 lichtblick 原版 3D 面板（React）与本工程 EduBot-Twin（Vue 3）的架构差异
- 生成差异对比文档：`edubot-twin-web/src/views/Simulation/3D_PANEL_DIFF_CN.md`
- 文档涵盖：整体架构、核心文件对照、数据源差异、设置面板架构、扩展数量（3/19已实现）、配置持久化、HUD 覆盖层、数据流图、后续开发建议

## 2026-02-19

### ROS Markers SceneExtension 完整实现

- **新增** `extensions/markers/` — 15个文件（materials.ts + MarkerPool.ts + 12种Renderable类 + RenderableMarker基类）
- **新增** `extensions/TopicMarkers.ts` — 管理单topic下所有namespace/marker生命周期，含过期检测
- **新增** `extensions/Markers.ts` — 主SceneExtension，订阅Marker/MarkerArray，管理设置树和命名空间visibility
- **修改** `core/IRenderer.ts` — 新增 `normalizeFrameId(frameId): string` 接口声明
- **修改** `core/Renderer.ts` — 实现 `normalizeFrameId()`（ROS模式去前导/）
- **修改** `composables/useRenderer.ts` — 在createExtensionConfig()中注册Markers extension
- **修复** `extensions/Grids.ts` — 删除 `RenderableLineList` 调用的多余第5参数 `LINE_OPTIONS`
- **修复** `extensions/markers/Markers.ts` — path可选链检查（path?.length）
- **最终状态**: tsc --noEmit 零错误

## 2026-03-12

### LaserScan 全链路修复

- **排查**: 通过代码静态分析逐层排查 /scan 不显示的根因（浏览器子智能体 503 失败，改用代码分析）
- **根因1（最关键）**: `index.vue` 的 `syncRosTopicsToRenderer()` 只订阅 Marker 类型，`sensor_msgs/LaserScan` 消息永远不路由到 renderer
  - **修复**: 加入 `LASERSCAN_SCHEMAS` + `VISUALIZABLE_SCHEMAS`，LaserScan 话题现在也被 ROSLIB 订阅
- **根因2**: `DEFAULT_POINT_SETTINGS.visible=false`，首次接收消息时 renderable 的 visible=false，startFrame skip
  - **修复**: `#handleLaserScan` 首次发现话题时强制 `visible=true` 并写入 config
- **根因3**: `handleSettingsAction` 只处理 `path.length===3`，眼睛图标的 `path.length===2` 动作被忽略
  - **修复**: 加入 `path.length===2` 分支，直接更新 renderable.visible + config + updateSettingsTree
- **附带**: settingsNodes 过滤逻辑（Markers/LaserScans 两处）防止话题串台
- **最终状态**: tsc --noEmit 零错误，/scan 端到端渲染链路完整

- **[2026-03-13]** 增加 ROS 3D Viewer 话题设置中“渐变”配置类型的界面渲染支持
  - 在 `SettingsNestedGroup.vue` 中添加了对 `field.input === 'gradient'` 的解析。
  - 使用了双端 `ElColorPicker` 组合作为输入，中间通过箭头分隔。
  - 提取了 `handleGradientChange` 方法以保证规范和无 lint error 发出 field-change 事件。
- [$(date '+%Y-%m-%d %H:%M:%S')] 修复 SettingsNestedGroup.vue 中 field.input 比较 'gradient' 导致的 TS 类型报错（TS2367），在 src/views/Simulation/types/settings.ts 的 SettingsTreeField 接口 input 联合类型中增加 'gradient' 支持。

## [2026-03-16]

- 实现 `Poses.ts` 扩展：支持 PoseStamped / PoseWithCovarianceStamped，axis/arrow/covariance 三种显示模式
- 实现 `PoseArrays.ts` 扩展：支持 PoseArray / Path，对象池 + 渐变色优化
- 实现 `PublishClickTool.ts`：状态机点击发布工具（idle→point1→point2），鼠标预览（小球/箭头）
- 实现 `PublishSettings.ts`：Settings Tree publish 节点，type/topic/偏差动态字段
- 修改 `IRenderer.ts`：添加 `RendererConfig.publish?` 字段和 `publishClickTool` 接口属性
- 修改 `Renderer.ts`：PublishClickTool 初始化顺序前移（先于 sceneExtensionConfig 注册循环）
- 修改 `useRenderer.ts`：onPublish 回调注入模式；startPublish/stopPublish 暴露
- 新建 `components/ROS3DToolbar.vue`：右上角工具栏（解耦）
- Bug 修复：切换设置面板类型后按钮文字实时同步（renderer.on('configChange') 事件驱动）
- Bug 修复：刷新页面后可直接切换回点类型（PublishClickTool 构造函数读配置初始化）

### 修复 LaserScan 异常运动与全局时钟 (decayTime)

- **时间**: 2026-03-16 20:13
- **内容**:
  - **时间戳解析修复**: 修改 `normalizeMessages.ts`，正确处理 `roslibjs` 中的 `secs/nsecs`，修复 TransformTree 因为时间戳解析报错引起的位置偏离和画面卡顿现象。
  - **全局时钟驱动**: 在 `useRenderer.ts` 中引入 100ms `setInterval`（全局播放器时钟），解决无外部 ROS 消息推入时画面不更新、历史点云不衰减的问题。
  - **仿真时间优先**: 在 `index.vue` 自动订阅 `/clock`，使 Renderer.currentTime 切换并完美跟踪 Gazebo 仿真时间。
  - **decayTime 修正**: 在 `useRenderer.ts` 转发消息前，统一使用 `clockTimeNs` 重写原始事件的 `receiveTime`，消除了壁钟 2026 年（17亿秒）与仿真时间（11000秒）跨时间域对比造成的 `expireTime` 计算失效。
- **状态**: 代码清理与人工验证均已通过。
- **[修复]** 限制 `ROS3DViewer` 3D 面板视角的更新频率 (`CameraStateSettings.ts`)，使用 `lodash` 的 `throttle` (200ms) 显著降低了由于过度频繁的 vue state/settings 同步而造成的卡顿。并修复了“同步相机”设定无效的问题，在开启该设定时会解除节流实现实时更新。
- **[修复]** 进一步解决了 `ROS3DViewer` 拖拽视角时越改越卡的问题。此前虽然节流了 `cameraMove`，但是由于 OrbitControls 仍在频繁触发 `cameraMove` 并连带触发全局的 `this.updateSettingsTree()`，导致 Vue 递归比对巨大的 settings tree 而产生极其严重的性能问题。将 `updateSettingsTree` 也在拖拽期间（默认）进行 1000ms 的防抖/节流限制，从根源解耦了视图渲染与 UI 状态同步。
- **[修复]** 撤销了针对 `CameraStateSettings.ts` 中 `cameraMove` 本身的节流处理。`cameraMove` 被节流会阻断 `OrbitControls` 发出的实时更新请求 (`renderer.queueAnimationFrame`) 导致 3D 画面的帧率实质性下降（即越拖越卡）。将节流仅作用于 `updateSettingsTree` 才能达到既不让 Vue 渲染卡顿，又保证 3D 画布 60fps 拖拽的效果。
- **[修复]** 修复了设定更新时每秒卡顿一下的问题：`SettingsTree` 是极其庞大的嵌套数据结构（包含大量 topic、图层节点等对象），通过 `immer` 不断生成新树。过去更新触发时，Vue `reactive`/`ref` 会深层介入产生不可承受的 `Proxy` 开销（表现为此前的 1秒 卡 1下）。通过引入 `import('vue').then({ markRaw })` 将注入 panelsState 的配置树节点强行脱离深层代理，瞬间排除了更新界面的性能开销，做到了真正的如丝般顺滑。
- **[修复]** 为 `CameraStateSettings` 增加了 `pointerdown` / `pointerup` 事件监听，用于标识 `#isDragging` 拖拽状态。在鼠标按下拖拽视角期间，完全跳过 `updateSettingsTree()` 的触发，使得拖拽过程获得近乎原生的纯 WebGL 渲染性能。松开鼠标后补发一次更新以确保左侧界面的坐标数据一致。
- **[修复]** 进一步解决 3D 面板拖拽视角时的卡顿问题。通过在 canvas 和 document 上监听 mousedown/mouseup 事件，在鼠标按下时设置 `#isDragging = true`，期间跳过 `updateSettingsTree()` 调用（从而消除了 Vue 渲染侧栏带来的开销），松开鼠标后延迟 100ms 执行一次最终的设置树更新。`syncCamera` 打开时不受此限制，始终实时更新。
- **[修复]** 去除了 `CameraStateSettings.ts` 中的 `1s` 定时刷新机制，完全依赖于鼠标拖拽判定。拖拽结束后立刻更新页面数值，没有多余延迟。

## 2026-03-18
- 修复 3D 面板坐标系文字标签（TF frame labels）不显示的问题
- 根因：lichtblick-shim.ts 中 Label/LabelPool/LabelMaterial 是空壳（Object3D stub），无任何实际渲染逻辑
- 解决：通过 pnpm 安装 @lichtblick/three-text v1.0.0（SDF + WebGL Shader 文字渲染），更新 shim 直接 re-export 真实实现
- 同时将 `import * as THREE from 'three'` 移至文件顶部（原放在 stub 区块内）
- TypeScript 编译零错误
