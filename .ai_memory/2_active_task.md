# 当前任务状态

## 当前阶段：第七期文件管理与代码编辑模块 - 已完成 ✅

## 已完成事项（本轮）

### 已修复事项
- 修复了后端由于使用绝对路径 `/data/students` 而导致的 `PermissionError` (Errno 13)
- 修正为相对于运行目录的相对路径 `Path("data/students").resolve()`

### 依赖安装
- **pnpm add @monaco-editor/loader**: CDN 懒加载方案

### 后端
- **新建 `files.py`** (`/student/files`): 6 个文件管理 API（上传/列表/读取/保存/删除/mkdir），含路径穿越防护、磁盘配额（100MB/学生）
- **`student/__init__.py`**: 注册 files 路由（前缀 `/files`）
- **`container_manager.py`**: 新增 `create_student_workspace()` 函数，`create_container()` 新增 Volume 挂载（`/data/students/{id}/workspace → /home/student/workspace`）

### 前端 API 层
- **`src/api/files/types.ts`**: FileItem、DirectoryItem、TreeNode 等类型定义
- **`src/api/files/index.ts`**: 6 个 API 封装（基于 service）

### 共享 Composable
- **`src/composables/useWorkspaceSettings.ts`**: localStorage 持久化，key `workspace_settings`，三处页面共享

### 核心组件
- **`src/components/Monaco/MonacoEditor.vue`**: CDN 懒加载、语言自动检测、Ctrl+S、设置同步
- **`src/views/Simulation/panels/WorkspacePanel/composables/useWorkspace.ts`**: 文件 CRUD + 状态管理
- **`src/views/Simulation/panels/WorkspacePanel/FileTree.vue`**: 懒加载树、右键菜单、拖拽上传、文件图标
- **`src/views/Simulation/panels/WorkspacePanel/index.vue`**: 左树右编辑器主面板，可拖拽分隔线

### 独立页面
- **`src/views/Student/FileManager.vue`**: 含设置抽屉（与面板共享配置）
- **`src/views/Student/CodeEditor.vue`**: 含设置抽屉（与面板共享配置）

### 路由配置
- **`src/router/index.ts`**: 新增 `student/files`（StudentFileManager）和 `student/editor`（StudentCodeEditor）
- **`mock/role/index.mock.ts`**: studentList 新增对应子路由

### 仿真集成
- **`panels/registry.ts`**: 注册 WorkspacePanel（key: WorkspacePanel）
- **`panels/predefined-layouts.ts`**: availablePanels 加入 WorkspacePanel

## 关键说明
- Monaco 用 CDN 懒加载（pnpm add @monaco-editor/loader），离线备用方案已记录在 SDD 第11节
- 设置通过 `useWorkspaceSettings` composable 在 WorkspacePanel / FileManager / CodeEditor 三处共享，key = `workspace_settings`
- 路径穿越防护：禁止绝对路径、禁止 `..`、resolve 后验证在 workspace 内
- Volume 挂载仅对**新建容器**生效，已运行容器不受影响

## 下一步（候选）
- 启动前后端验证：`npm run dev` + `uvicorn`
- 在浏览器中以 student 角色测试文件管理页面
- 第八期规划
