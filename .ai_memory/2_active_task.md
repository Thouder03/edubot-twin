# 当前任务状态

## 当前阶段：教师端管理模块待实现功能 - 已完成 ✅

## 已完成事项（本轮）

### 后端
- **新建 `monitor.py`** (`/api/v1/teachers/containers/monitor`): 专用容器监控端点，支持分页，使用 `selectinload` 预加载学生避免 N+1 查询，对 running 容器调用 `get_container_stats()` 获取实时数据
- **`container_manager.py`**: 新增 `ContainerStats` 数据类 + `get_container_stats()` 方法，实现 Docker 官方 CPU % 计算算法
- **`schemas/container.py`**: 新增 `ContainerMonitorInfo` + `ContainerMonitorListResponse`
- **`schemas/student.py`**: 新增 `StudentListResponse`（含 total + list）
- **`crud/student.py`**: `get_students()` 支持 `keyword` 模糊搜索（username / real_name），返回 `(list, total)` 元组
- **`endpoints/teacher/students.py`**: 支持 `pageIndex` / `pageSize` / `keyword` 参数，返回带 total 的分页格式
- **`teacher/__init__.py`**: 注册 `/containers/monitor` 路由

### 前端
- **新建 `src/api/teacher/types.ts`**: 统一类型定义（StudentInfo, ContainerMonitorInfo 等）
- **新建 `src/api/teacher/index.ts`**: 教师端 API 汇总模块，monitor 端点已更新至 `/containers/monitor`
- **`Student.vue`**: 添加搜索表单（ElInput + keyword 参数）+ 批量删除功能（多选 + 逐个删除）
- **`Monitor.vue`**: 新增 cpu_percent（进度条）、memory_mb（进度条）、uptime_seconds 列；status 完整映射含 `removing`；轮询间隔改为 30s
- **`Write.vue`**: 导入路径更新至 `@/api/teacher`

## 关键说明
- 后端 `/containers/monitor` 路由因 FastAPI 路由匹配规则，必须在 `/containers/{id}` 之前注册（已在 `__init__.py` 中正确顺序配置）

## 下一步（候选）
- 学生端 Terminal 集成（xterm.js + WebSocket 反向代理）
- 教师首页数据看板（学生数、容器使用率等）
