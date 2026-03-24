# 当前任务状态

## 当前阶段：第三期已完成 ✅

## 已完成事项

### 后端（edubot-twin-server）
- `app/core/docker_client.py` — Docker 客户端单例（新建）
- `app/core/container_manager.py` — 容器生命周期异步管理器（新建）
- `app/core/security.py` — 新增 `get_current_student_id()` JWT 依赖注入
- `app/crud/container.py` — 4 处 Mock 替换为真实 Docker 调用
- `app/models/container.py` — 新增 `error_message` 字段
- `app/schemas/container.py` — `image_name` 默认值 → `gzweb_sim:v1`；`error_message` 字段
- `app/api/v1/endpoints/student/container.py` — JWT 鉴权 + 新增 `/start`、`/destroy-and-recreate` 端点
- `requirements.txt` — 新增 `docker>=7.0`

### 前端（edubot-twin-web）
- `src/views/Student/Home.vue` — 「开始仿真」完整容器预检 + 弹窗流程（4 种情况）
- `src/views/Simulation/Simulation.vue` — provide `containerRosUrl`；去掉 `TEMP_STUDENT_ID`
- `src/views/Simulation/panels/ROS3DViewer/index.vue` — inject `containerRosUrl`，watch 自动更新 rosUrl
- `src/api/container/index.ts` — 去掉 `studentId` 参数；新增 `destroyAndRecreateApi`、`startMyContainerApi`
- `src/api/container/types.ts` — `ContainerResponse` 增加 `error_message`

## 关键注意事项
- Python 版本：3.9.5（使用 `Optional[X]` 不用 `X | None`）
- 虚拟环境路径：`edubot-twin-server/../.venv/`
- `gzweb_sim:v1` 镜像需要在宿主机提前存在

## 下一步（第四期候选）
- 学生端 Terminal 集成（xterm.js + WebSocket 反向代理）
- 教师端容器监控看板（实时 CPU/内存）
- 考试/测试模块
