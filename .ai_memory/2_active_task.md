# 当前任务状态

## 当前阶段：第二期已完成 ✅

第二期任务"容器管理 API + 动态连接"全部完成。

## 已完成事项

### 后端（edubot-twin-server）
- `app/models/container.py` — SimContainer 模型 + ContainerStatus 枚举
- `app/schemas/container.py` — Pydantic Schema（含 gzbridge_url/rosbridge_url 计算字段）
- `app/core/port_allocator.py` — 端口分配器（9000-9499 / 9500-9999）
- `app/crud/container.py` — 7 个 CRUD 函数（Docker 调用以 # TODO: DOCKER 注释占位）
- `app/api/v1/endpoints/teacher/containers.py` — 教师端 6 个端点
- `app/api/v1/endpoints/student/container.py` — 学生端 2 个端点
- `app/api/v1/endpoints/teacher/__init__.py` — 注册 containers 路由
- `app/api/v1/endpoints/student/__init__.py` — 注册 container 路由
- `init_db.py` — 添加 SimContainer 导入，运行后创建 sim_containers 表

### 前端（edubot-twin-web）
- `src/api/container/types.ts` — ContainerResponse、ContainerStatusResponse、ContainerCreate 类型
- `src/api/container/index.ts` — 8 个 API 封装函数（教师/学生端全覆盖）
- `panels/GzWebViewer/index.vue` — onMounted 新增 fetchAndApplyContainerUrl()，从 API 动态获取 gzbridge URL，失败时 fallback 到手动配置

## 下一步（第三期）

- [ ] 场景树：`gz:getSceneTree` / `gz:selectEntity` / `gz:setManipMode` / `gz:deleteEntity` / `gz:spawnEntity`
- [ ] JWT 鉴权：GzWebViewer 中 studentId 改为从 userStore.userInfo.id 读取
- [ ] Docker 真实接入：替换 crud/container.py 中所有 `# TODO: DOCKER` 注释处
