# Dry Run 重构计划：Shadow 学生身份方案

## Context

当前教师 Dry Run 采用内存态会话管理（`dry_run_manager.py`），容器不写入数据库，前端 `Simulation.vue` 中有大量 `isDryRun` 条件分支。教师体验与学生端不一致：无心跳、无重激活、退出即清理。

本次重构将 Dry Run 改为"Shadow 学生身份"方案：教师获得一个代理学生账号，用该账号的 JWT 访问所有学生接口，获得与学生完全一致的仿真体验。同时新增 Dry Run 专属悬浮工具栏（Docker Logs + 失败回顾）和终端/文件面板的 ROOT 切换功能。

## 已确认设计决策

| 决策项 | 结论 |
|--------|------|
| 并发 | 同时 1 个（与学生一致，force_recreate） |
| Token | sessionStorage 隔离（新标签页独立，不影响教师原标签页） |
| Docker logs | REST API 一次性获取最近 N 行 + 手动刷新 |
| ROOT 文件范围 | 容器内全部文件系统（docker exec） |

---

## Step 1: User 模型扩展 + Shadow 账号服务

### 1.1 User 模型增加字段

**文件**: `edubot-twin-server/app/models/student.py`

```python
# 新增两个字段
is_shadow: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
shadow_owner_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
```

- `is_shadow=True` 标记为 Shadow 学生（用于查询过滤、权限判断）
- `shadow_owner_id` 指向拥有者教师的 `user_id`

### 1.2 Shadow 账号 CRUD 服务

**新建文件**: `edubot-twin-server/app/crud/shadow_student.py`

```python
async def get_or_create_shadow(db, teacher_id: int) -> User:
    """幂等：查询或创建教师的 Shadow 学生"""
    # SELECT WHERE is_shadow=True AND shadow_owner_id=teacher_id
    # 不存在则 INSERT: username="_shadow_{teacher_id}", role_code="student", is_shadow=True

async def is_shadow_user(db, user_id: int) -> bool:
    """快速检查是否为 Shadow 学生"""
```

- Shadow 学生 `role_code = "student"`，JWT 包含 `role: "student"`
- 命名规范: `_shadow_{teacher_id}`（下划线前缀防与真实用户名冲突）
- 密码: 随机 bcrypt hash（永远不会通过登录页面使用）

### 1.3 学生列表过滤

**文件**: `edubot-twin-server/app/crud/student.py`

`get_users()` / `get_students()` 查询添加 `WHERE is_shadow = False`，防止 Shadow 账号出现在教师管理的学生列表中。

---

## Step 2: 重写教师 Dry Run 启动端点

### 2.1 替换旧端点

**文件**: `edubot-twin-server/app/api/v1/endpoints/teacher/env_bundles.py`

删除旧的三个 dry-run 端点，替换为新端点：

```
POST /api/v1/teachers/env-bundles/{env_bundle_id}/dry-run
```

**新流程**:
1. 验证 env_bundle 归属 + startup.sh 存在（复用现有逻辑）
2. 读取 version 配置（**跳过 publish_status 检查**，教师可访问草稿版本）
3. `get_or_create_shadow(db, teacher_id)` -> 获取 Shadow 学生
4. 若 Shadow 学生已有容器 -> `delete_container(db, existing)`（force_recreate 语义）
5. `crud_container.create_container(db, ContainerCreate(user_id=shadow.id, ...))` -> 写入 DB
6. 就绪检测（gzweb + rosbridge，复用 `check_gzweb_ready` / `check_rosbridge_ready`）
7. 签发 Shadow JWT: `create_access_token({"sub": shadow.username, "user_id": shadow.id, "role": "student", "role_id": "10", "is_shadow": True, "shadow_owner_id": teacher_id})`
8. 返回 `{shadow_token, container_id}`

### 2.2 删除旧端点

从 `env_bundles.py` 删除:
- `DELETE /dry-run/mine/all`（cleanup_my_dry_runs）
- `DELETE /dry-run/{container_id}`（stop_dry_run_container）

不再需要：容器走标准学生生命周期（心跳超时自动停止、stopOnExit）。

### 2.3 更新 Response Schema

**文件**: `edubot-twin-server/app/schemas/experiment.py`

```python
class EnvBundleDryRunByVersionResponse(BaseModel):
    shadow_token: str      # Shadow 学生 JWT（前端用于 API 调用）
    container_id: str      # 容器 ID（前端展示用）
```

---

## Step 3: sessionStorage Token 隔离（前端）

### 3.1 请求拦截器修改

**文件**: `edubot-twin-web/src/axios/index.ts`

```typescript
const request = (option: AxiosConfig) => {
  const userStore = useUserStoreWithOut()
  const shadowToken = sessionStorage.getItem('simulation_token')  // 优先读 sessionStorage
  const token = shadowToken || userStore.getToken
  return service.request({
    headers: {
      'Content-Type': CONTENT_TYPE,
      [userStore.getTokenKey ?? 'Authorization']: token ? `Bearer ${token}` : '',
      ...headers
    }
  })
}
```

sessionStorage 按标签页隔离，教师原标签页不受影响。

### 3.2 教师入口页面修改

**文件**: `edubot-twin-web/src/views/Teacher/Experiments/ExperimentEnvs.vue`

```typescript
const startDryRun = async () => {
  const res = await startDryRunApi(envBundleId, versionId)
  const { shadow_token, container_id } = res.data
  const url = router.resolve({
    name: 'Simulation',
    query: { simulation_token: shadow_token, env_bundle_name: ... }
  }).href
  window.open(url, '_blank')
}
```

删除:
- `cleanupMyDryRunsApi` 引用和 429 自动重试逻辑（不再需要）
- `stopDryRunApi` 引用

### 3.3 Simulation.vue Token 接收

**文件**: `edubot-twin-web/src/views/Simulation/Simulation.vue`

`onMounted` 中:
```typescript
const simToken = route.query.simulation_token
if (typeof simToken === 'string') {
  sessionStorage.setItem('simulation_token', simToken)
  // 从 URL 移除 token（防泄露到浏览器历史）
  router.replace({ ...route, query: { ...route.query, simulation_token: undefined } })
}
const isDryRunMode = computed(() => !!sessionStorage.getItem('simulation_token'))
```

### 3.4 终端 WebSocket Token

**文件**: `edubot-twin-web/src/views/Simulation/panels/ContainerTerminal/index.vue`

```typescript
function getWsUrl(): string {
  const shadowToken = sessionStorage.getItem('simulation_token')
  const token = shadowToken || userStore.getToken
  // ...使用 token 构造 WS URL
}
```

### 3.5 stopOnExit Token

```typescript
// Simulation.vue onBeforeUnmount
const token = sessionStorage.getItem('simulation_token') || userStore.getToken
if (token) stopOnExitApi(token)
```

### 3.6 onBeforeUnmount 清理 sessionStorage

```typescript
sessionStorage.removeItem('simulation_token')
```

---

## Step 4: Simulation.vue 清理

**文件**: `edubot-twin-web/src/views/Simulation/Simulation.vue`

### 删除内容

| 行号区域 | 内容 | 原因 |
|----------|------|------|
| L51-52 | `isDryRun` ref, `dryRunContainerId` ref | Shadow JWT 后无需区分 |
| L175-176 | `handleVisibilityChange` 中 `if (isDryRun.value) return` | Shadow 学生有真实容器，心跳正常工作 |
| L346-350 | Dry Run 检测 + container_id 读取 | 不再需要 |
| L353-370 | `isDryRun` 分支（从 URL 获取 gzbridge/rosbridge） | 统一走 `/mine` API |
| L409 | `if (!isDryRun.value) { startHeartbeat() }` | 始终启动心跳 |
| L420-425 | `if (!isDryRun.value) { stopOnExitApi() }` | 始终调用 stopOnExit |
| L439-441 | `if (isDryRun.value) { stopDryRunApi() }` | 不再需要 |
| L457 | `<div v-if="isDryRun" class="dry-run-banner">` | 需求 2: 删除提示栏 |
| L486-495 | `.dry-run-banner` CSS | 配套删除 |
| L35 | `import { stopDryRunApi }` | 不再使用 |

### 统一后的 onMounted 逻辑

```typescript
onMounted(async () => {
  // ... 暗色模式、事件监听 ...

  // Token 接收（Step 3.3）
  handleSimulationToken()

  // 统一走学生 API（Shadow JWT 或学生 JWT 都走这条路径）
  const res = await getMyContainerApi()
  const gzUrl = res?.data?.gzbridge_url
  const rosUrl = res?.data?.rosbridge_url
  if (gzUrl) initGzBridge(gzUrl)
  if (rosUrl) containerRosUrl.value = rosUrl

  startHeartbeat()
})
```

---

## Step 5: 悬浮工具栏（Dry Run 专属）

### 5.1 新建工具栏组件

**新建文件**: `edubot-twin-web/src/views/Simulation/components/DryRunToolbar.vue`

- `position: fixed` 浮在右下角
- 可收起/展开的按钮组
- 仅当 `isDryRunMode` 为 true 时显示（通过 prop 控制）
- 两个功能按钮: "Docker Logs" 和 "运行失败回顾"

### 5.2 Docker Logs API

**新建后端文件**: `edubot-twin-server/app/api/v1/endpoints/teacher/dry_run_tools.py`

```
GET /api/v1/teachers/dry-run-tools/docker-logs?lines=500
```

- 认证: Shadow JWT（`get_current_user_id` -> 检查 `is_shadow=True`）
- 实现: 查找该 Shadow 学生的容器 -> `docker logs --tail={lines} {container_id}`
- 返回: `{ logs: string }`

**新增 container_manager 函数**:

```python
async def get_container_logs(container_id: str, tail: int = 500) -> str:
    """获取容器日志"""
    proc = await asyncio.create_subprocess_exec(
        "docker", "logs", "--tail", str(tail), container_id,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    stdout, _ = await proc.communicate()
    return stdout.decode("utf-8", errors="replace")
```

### 5.3 运行失败回顾 API

```
GET /api/v1/teachers/dry-run-tools/failure-review
```

- 认证: 同上（Shadow JWT）
- 返回: 容器 status、error_message、最近 SimulationTask 的各阶段状态信息

### 5.4 前端 API 层

**新建**: `edubot-twin-web/src/api/dryrun/index.ts`

```typescript
export const getDockerLogsApi = (lines = 500) =>
  request.get({ url: `/api/v1/teachers/dry-run-tools/docker-logs?lines=${lines}` })
export const getFailureReviewApi = () =>
  request.get({ url: '/api/v1/teachers/dry-run-tools/failure-review' })
```

### 5.5 集成到 Simulation.vue

```html
<DryRunToolbar v-if="isDryRunMode" />
```

---

## Step 6: ROOT 模式

### 6A: 终端 ROOT 切换

**后端**: `edubot-twin-server/app/api/v1/endpoints/student/terminal.py`

- 接受 `root` 查询参数（WebSocket URL: `?token=xxx&root=1`）
- `root=1` 时: 验证 JWT 中 `is_shadow=True`，使用 `docker exec -u 0 -w /` 代替 `-u 1000 -w /home/student/workspace`
- `root=0` 或无参数: 保持现有行为（uid=1000）

**前端**: `edubot-twin-web/src/views/Simulation/panels/ContainerTerminal/index.vue`

- 新增 `rootMode` ref（默认 false）
- 工具栏添加 ROOT 切换按钮（仅 `isDryRunMode` 时可见）
- 切换时断开当前 WebSocket -> 以 `root=1` 重新连接

### 6B: 文件管理 ROOT 模式

**新建后端文件**: `edubot-twin-server/app/api/v1/endpoints/teacher/container_files.py`

基于 docker exec 的容器内文件操作 API:

```
GET    /api/v1/teachers/dry-run-tools/files/list?path=/
GET    /api/v1/teachers/dry-run-tools/files/read?path=/etc/hosts
POST   /api/v1/teachers/dry-run-tools/files/write     {path, content}
POST   /api/v1/teachers/dry-run-tools/files/mkdir      {path}
DELETE /api/v1/teachers/dry-run-tools/files/delete?path=/tmp/foo
```

实现:
- `list`: `docker exec {cid} ls -la --time-style=+%s {path}` -> 解析为结构化 JSON
- `read`: `docker exec {cid} cat {path}`（限制 1MB）
- `write`: `docker exec -i {cid} sh -c 'cat > {path}'` + stdin
- `mkdir`: `docker exec {cid} mkdir -p {path}`
- `delete`: `docker exec {cid} rm -rf {path}`（黑名单: `/bin`, `/usr`, `/lib`, `/proc`, `/sys`, `/dev`）
- 认证: Shadow JWT（`is_shadow=True` 检查）

**前端**: `edubot-twin-web/src/views/Simulation/panels/WorkspacePanel/`

- 新增 ROOT 切换按钮（仅 `isDryRunMode` 时可见）
- 切换后 API 调用从 `/api/v1/students/files/*` -> `/api/v1/teachers/dry-run-tools/files/*`
- 工作区根目录从 student workspace -> `/`（容器根目录）
- `composables/useWorkspace.ts` 需要支持动态切换 API base 路径

---

## Step 7: 旧代码清理

### 删除文件
- `edubot-twin-server/app/core/dry_run_manager.py`

### 删除代码段

| 文件 | 删除内容 |
|------|---------|
| `app/main.py` | `from app.core.dry_run_manager import dry_run_manager` 和 `await dry_run_manager.cleanup_all(remove_container)` |
| `app/api/v1/endpoints/teacher/env_bundles.py` | 旧 dry-run 三个端点完整代码、`DryRunSession` / `dry_run_manager` 导入 |
| `app/core/container_manager.py` | `is_dry_run` 参数及其分支逻辑（命名 `edubot-dryrun-*`、标签 `edubot.type=dry-run`） |
| `app/schemas/container.py` | `ContainerCreate.is_dry_run` 字段 |
| `src/api/experiment/index.ts` | `stopDryRunApi()`, `cleanupMyDryRunsApi()` |
| `src/api/experiment/types.ts` | 旧 `DryRunStartResponse`（替换为新 schema） |
| `src/views/Simulation/Simulation.vue` | 全部 `isDryRun` 分支（见 Step 4 表格） |
| `src/views/Teacher/Experiments/ExperimentEnvs.vue` | 429 自动重试逻辑、`cleanupMyDryRunsApi` 调用 |

### 影响范围注意

- `get_users()` / `get_students()` 必须过滤 `is_shadow=False`，防止 Shadow 账号出现在学生管理列表

---

## 实施顺序

```
Step 1 (后端基础) -> Step 2 (新 API) -> Step 3 (前端 Token)
    -> Step 4 (Simulation 清理) -> Step 7 (旧代码删除)
        -> Step 5 (悬浮工具栏)  <- 可并行
        -> Step 6 (ROOT 模式)   <- 可并行
```

## 验证方式

1. **基本流程**: 教师点击 Dry Run -> 容器创建成功（DB 有记录）-> 新标签页打开仿真页面 -> `/mine` 返回容器信息 -> 心跳正常 -> GzWeb/ROS 可用
2. **Token 隔离**: 教师原标签页的操作不受影响（仍使用教师 JWT）
3. **草稿版本**: 教师可对 `publish_status != "published"` 的版本进行 Dry Run
4. **容器生命周期**: 关闭仿真标签页 -> stopOnExit 正常调用 -> 容器停止
5. **Docker Logs**: 悬浮工具栏点击 -> 弹窗显示容器日志 -> 刷新按钮有效
6. **ROOT 终端**: 切换 ROOT -> 终端以 root 用户身份执行命令 -> `whoami` 返回 `root`
7. **ROOT 文件**: 切换 ROOT -> 文件树显示容器根目录 -> 可浏览 `/opt/ros` 等系统目录
8. **学生无影响**: 学生端操作不受任何影响，不显示 ROOT 按钮和工具栏
