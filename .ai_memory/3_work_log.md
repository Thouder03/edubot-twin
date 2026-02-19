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
