# 当前任务状态

## 当前阶段：第四期已完成 ✅

## 已完成事项

### 后端（edubot-twin-server）
- `app/models/container.py` — 新增 `last_heartbeat_at: Optional[datetime]` 字段
- `app/schemas/container.py` — 新增 `StopOnExitRequest(BaseModel)` Schema
- `app/crud/container.py` — 新增 `update_heartbeat()`、`find_stale_containers()` 函数；引入 `timedelta`
- `app/api/v1/endpoints/student/container.py` — 新增 `/heartbeat`（JWT）、`/stop`（JWT）、`/stop-on-exit`（Token in body）三个端点
- `app/main.py` — 改用 `lifespan` 机制替换 `@on_event`；注册 `_stale_container_cleanup_loop()` 后台任务（60s 扫描，120s 超时阈值）
- SQLite 数据库已手动 `ALTER TABLE sim_containers ADD COLUMN last_heartbeat_at DATETIME`

### 前端（edubot-twin-web）
- `src/api/container/types.ts` — 新增 `StopOnExitRequest` 接口
- `src/api/container/index.ts` — 新增 `heartbeatApi()`、`stopMyContainerApi()`、`stopOnExitApi()`
- `src/views/Simulation/Simulation.vue` — 完整重写，新增：
  - 心跳定时器（30s 前台 / 120s 后台）
  - `document.visibilitychange` 监听（降频 + 状态检查）
  - `window.beforeunload` 拦截
  - `sendBeacon` 退出（userStore.getToken）
  - 重新激活弹窗（`checkContainerOnReactivation` + `handleContainerStopped` + `restartContainer`）
  - `reinitGzBridge()`（dispose + initialize，用于容器重启后重连）
- `src/views/Simulation/components/SimulationHeader.vue` — `handleBack()` 改为弹窗确认退出 + 调用 `stopMyContainerApi()`

## 关键注意事项
- Python 版本：3.9.5（使用 `Optional[X]` 不用 `X | None`）
- 虚拟环境路径：`edubot-twin-server/../.venv/`
- `gzweb_sim:v1` 镜像需要在宿主机提前存在
- Token 从 `useUserStore().getToken` 获取（不用 wsCache）

## 下一步（候选）
- 学生端 Terminal 集成（xterm.js + WebSocket 反向代理）
- 教师端容器监控看板（实时 CPU/内存）
- 考试/测试模块
