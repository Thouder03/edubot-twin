# SDD 第四期：容器生命周期与在线检测

> 前置：第三期已完成 Docker 全真接入、ROS URL 自动注入、开始仿真弹窗、JWT 鉴权改造。本期在此基础上实现容器生命周期的自动化管理——心跳检测、超时关闭、重新激活提示、退出确认。

---

## 一、需求清单

| # | 需求 | 简述 |
|---|---|---|
| 1 | 心跳上报 + 容器自动关闭 | 前端定时向后端报告在线状态，后端超时未收到心跳则自动停止容器 |
| 2 | 页面重新激活提示 | 仿真页面从休眠/后台恢复后，若容器已关闭，弹窗提示是否重新打开 |
| 3 | 退出仿真确认 | 学生退出仿真页面时弹窗提醒"退出将关闭容器" |

---

## 二、模块 D — 心跳上报与容器自动关闭

### D.1 整体架构

```
┌──────────────┐         每 30s          ┌──────────────────┐
│   前端        │ ── POST /heartbeat ──→ │   后端             │
│ Simulation   │                         │ student/container │
│ .vue         │ ←── { status } ──────── │                   │
└──────────────┘                         └────────┬─────────┘
                                                  │
                                         每 60s 定时扫描
                                                  │
                                                  ▼
                                         ┌──────────────────┐
                                         │  定时任务          │
                                         │  扫描 stale 容器   │
                                         │  last_heartbeat   │
                                         │  > 2 min → stop   │
                                         └──────────────────┘
```

### D.2 数据模型变更

`app/models/container.py` 新增字段：

```python
from datetime import datetime

last_heartbeat_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime, nullable=True,
    comment="前端最后一次心跳时间，用于超时检测"
)
```

### D.3 新增后端端点

#### `POST /api/v1/students/container/heartbeat`

```python
@router.post(
    "/heartbeat",
    response_model=ContainerStatusResponse,
    summary="心跳上报",
)
async def heartbeat(
    student_id: int = Depends(get_current_student_id),
    db: AsyncSession = Depends(get_db),
):
    """
    前端定期调用，更新 last_heartbeat_at。

    返回容器当前状态，前端据此判断容器是否仍然存活。
    若容器不存在或已停止，前端可触发重新激活弹窗。
    """
    container = await crud_container.get_container_by_student(db, student_id)
    if not container:
        raise HTTPException(404, "尚未分配容器")

    container.last_heartbeat_at = datetime.utcnow()
    container.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(container)

    return ContainerStatusResponse.from_orm_with_host(container)
```

#### `POST /api/v1/students/container/stop`

学生端主动停止自己的容器（退出时调用）。

```python
@router.post(
    "/stop",
    response_model=ContainerStatusResponse,
    summary="停止我的容器",
)
async def stop_my_container(
    student_id: int = Depends(get_current_student_id),
    db: AsyncSession = Depends(get_db),
):
    container = await crud_container.get_container_by_student(db, student_id)
    if not container:
        raise HTTPException(404, "尚未分配容器")
    if container.status != ContainerStatus.RUNNING:
        return ContainerStatusResponse.from_orm_with_host(container)

    container = await crud_container.stop_container(db, container)
    return ContainerStatusResponse.from_orm_with_host(container)
```

### D.4 CRUD 层新增

`app/crud/container.py` 新增：

```python
async def update_heartbeat(db: AsyncSession, container: SimContainer) -> None:
    """更新心跳时间"""
    container.last_heartbeat_at = datetime.utcnow()
    container.updated_at = datetime.utcnow()
    await db.commit()


async def find_stale_containers(
    db: AsyncSession,
    timeout_seconds: int = 120,
) -> list[SimContainer]:
    """
    查找心跳超时的 running 容器

    Args:
        timeout_seconds: 超时阈值（秒），默认 120 秒（2 分钟）

    Returns:
        超时容器列表
    """
    cutoff = datetime.utcnow() - timedelta(seconds=timeout_seconds)
    result = await db.execute(
        select(SimContainer).where(
            SimContainer.status == ContainerStatus.RUNNING,
            # last_heartbeat_at 为 NULL 或早于 cutoff
            (SimContainer.last_heartbeat_at == None)  # noqa: E711
            | (SimContainer.last_heartbeat_at < cutoff),
        )
    )
    return list(result.scalars().all())
```

### D.5 后端定时任务

使用 FastAPI 的 lifespan 机制注册后台定时任务：

```python
# app/main.py

import asyncio
import logging
from contextlib import asynccontextmanager

from app.db.database import AsyncSessionLocal
from app.crud import container as crud_container
from app.core import container_manager

logger = logging.getLogger(__name__)

STALE_CHECK_INTERVAL = 60     # 每 60 秒扫描一次
HEARTBEAT_TIMEOUT = 120       # 心跳超时阈值：2 分钟


async def _stale_container_cleanup_loop():
    """后台循环：定期扫描并停止心跳超时的容器"""
    while True:
        try:
            async with AsyncSessionLocal() as db:
                stale = await crud_container.find_stale_containers(
                    db, timeout_seconds=HEARTBEAT_TIMEOUT
                )
                for container in stale:
                    logger.info(
                        f"容器 {container.id} (学生 {container.student_id}) "
                        f"心跳超时，自动停止"
                    )
                    await crud_container.stop_container(db, container)
        except Exception as e:
            logger.error(f"Stale container cleanup error: {e}")

        await asyncio.sleep(STALE_CHECK_INTERVAL)


@asynccontextmanager
async def lifespan(app):
    # 启动后台任务
    task = asyncio.create_task(_stale_container_cleanup_loop())
    yield
    # 关闭后台任务
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

app = FastAPI(lifespan=lifespan)
```

### D.6 前端心跳实现

在 `Simulation.vue` 中新增心跳逻辑：

```typescript
import { heartbeatApi } from '@/api/container'

// ─── 心跳定时器 ───────────────────────────────────────

const HEARTBEAT_INTERVAL = 30_000  // 正常：30 秒
const HEARTBEAT_INTERVAL_BG = 120_000  // 后台/低频：120 秒
let heartbeatTimer: ReturnType<typeof setInterval> | null = null
let currentInterval = HEARTBEAT_INTERVAL

function startHeartbeat() {
  stopHeartbeat()
  heartbeatTimer = setInterval(sendHeartbeat, currentInterval)
  sendHeartbeat() // 立即发一次
}

function stopHeartbeat() {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer)
    heartbeatTimer = null
  }
}

async function sendHeartbeat() {
  try {
    const res = await heartbeatApi()
    const status = res?.data?.status

    if (status && status !== 'running') {
      // 容器已不在运行 → 触发重新激活弹窗
      stopHeartbeat()
      handleContainerStopped()
    }
  } catch (err) {
    // 网络错误：静默处理，等下次心跳重试
    console.warn('[Heartbeat] 心跳失败:', err)
  }
}

onMounted(() => {
  // ... 现有初始化逻辑 ...
  startHeartbeat()
})

onBeforeUnmount(() => {
  stopHeartbeat()
  // ... 现有清理逻辑 ...
})
```

### D.7 Page Visibility 联动

```typescript
// ─── Page Visibility 心跳降频 ──────────────────────────

function handleVisibilityChange() {
  if (document.hidden) {
    // 页面进入后台：降频心跳
    currentInterval = HEARTBEAT_INTERVAL_BG
    startHeartbeat()  // 重启定时器使用新间隔
  } else {
    // 页面恢复前台：恢复正常心跳 + 立即检查状态
    currentInterval = HEARTBEAT_INTERVAL
    startHeartbeat()
    checkContainerOnReactivation()
  }
}

onMounted(() => {
  document.addEventListener('visibilitychange', handleVisibilityChange)
})

onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', handleVisibilityChange)
})
```

### D.8 参数配置表

| 参数 | 位置 | 默认值 | 说明 |
|---|---|---|---|
| `HEARTBEAT_INTERVAL` | 前端 Simulation.vue | 30s | 页面前台时的心跳间隔 |
| `HEARTBEAT_INTERVAL_BG` | 前端 Simulation.vue | 120s | 页面后台时的心跳间隔 |
| `STALE_CHECK_INTERVAL` | 后端 main.py | 60s | 后端扫描超时容器的频率 |
| `HEARTBEAT_TIMEOUT` | 后端 main.py | 120s | 心跳超过此时间视为离线 |

> 注：浏览器在页面长时间 hidden 后（通常 5 分钟）会冻结 JS 定时器，心跳自然停止。后端 120s 超时阈值确保此场景下容器也能被自动关闭。

---

## 三、模块 E — 页面重新激活提示

### E.1 触发条件

- 页面从 `hidden` → `visible`（`visibilitychange` 事件）
- 浏览器标签页从后台切回前台
- 笔记本合盖再开盖

### E.2 检查与弹窗流程

```
页面 visibilitychange (hidden → visible)
    │
    ├─ 立即调用 getMyContainerApi()
    │
    ├── status === 'running'
    │   └─ 正常：恢复心跳，无弹窗
    │
    ├── status === 'stopped'
    │   └─ 弹窗:
    │       ┌─────────────────────────────────────────┐
    │       │  ⚠ 仿真容器已关闭                         │
    │       │                                         │
    │       │  由于长时间未活动，您的仿真容器已自动关闭。  │
    │       │  是否重新启动？                            │
    │       │                                         │
    │       │  [重新启动]              [返回首页]        │
    │       └─────────────────────────────────────────┘
    │       ├─ [重新启动]
    │       │   → 调用 startMyContainerApi()
    │       │   → 等待 running
    │       │   → 重新初始化 GzBridge + 重设 containerRosUrl
    │       │   → 恢复心跳
    │       └─ [返回首页]
    │           → window.close() 或 router.push('/student/home')
    │
    ├── 404（容器已被删除）
    │   └─ 弹窗:
    │       ┌─────────────────────────────────────────┐
    │       │  ⚠ 容器已被回收                           │
    │       │                                         │
    │       │  您的仿真容器已被管理员回收。              │
    │       │  请返回首页重新申请。                      │
    │       │                                         │
    │       │                         [返回首页]        │
    │       └─────────────────────────────────────────┘
    │       → window.close() 或 router.push('/student/home')
    │
    └── 网络错误
        └─ ElMessage.warning("网络连接异常，请检查网络")
        └─ 不弹窗，等下次心跳重试
```

### E.3 实现代码

```typescript
async function checkContainerOnReactivation() {
  try {
    const res = await getMyContainerApi()
    const status = res?.data?.status

    if (status === 'running') {
      // 一切正常，恢复心跳
      return
    }

    if (status === 'stopped') {
      await handleContainerStopped()
    } else {
      // error / creating / removing → 提示异常
      await ElMessageBox.alert(
        '仿真容器状态异常，请返回首页重新操作。',
        '容器异常',
        {
          confirmButtonText: '返回首页',
          type: 'error',
        }
      )
      navigateToHome()
    }
  } catch (err: any) {
    if (err?.response?.status === 404) {
      await ElMessageBox.alert(
        '您的仿真容器已被管理员回收，请返回首页重新申请。',
        '容器已回收',
        {
          confirmButtonText: '返回首页',
          type: 'warning',
        }
      )
      navigateToHome()
    } else {
      ElMessage.warning('网络连接异常，请检查网络')
    }
  }
}

async function handleContainerStopped() {
  try {
    await ElMessageBox.confirm(
      '由于长时间未活动，您的仿真容器已自动关闭。是否重新启动？',
      '仿真容器已关闭',
      {
        confirmButtonText: '重新启动',
        cancelButtonText: '返回首页',
        type: 'warning',
        closeOnClickModal: false,
        closeOnPressEscape: false,
      }
    )
    // 用户点击"重新启动"
    await restartContainer()
  } catch {
    // 用户点击"返回首页"
    navigateToHome()
  }
}

async function restartContainer() {
  const loading = ElLoading.service({ text: '正在重新启动仿真容器...' })
  try {
    await startMyContainerApi()
    const result = await waitForContainerRunning()
    if (result) {
      // 重新初始化连接
      const gzUrl = result.gzbridge_url
      const rosUrl = result.rosbridge_url
      if (gzUrl) updateGzwebUrl(gzUrl)
      if (rosUrl) containerRosUrl.value = rosUrl
      startHeartbeat()
      ElMessage.success('仿真容器已重新启动')
    } else {
      ElMessage.error('容器启动失败')
      navigateToHome()
    }
  } finally {
    loading.close()
  }
}

function navigateToHome() {
  // 仿真页是新标签页打开的，尝试关闭
  window.close()
  // 如果 window.close() 不起作用（非 JS 打开的标签页）
  setTimeout(() => {
    window.location.href = '/student/home'
  }, 300)
}
```

---

## 四、模块 F — 退出仿真确认

### F.1 两个退出路径

| 退出方式 | 触发点 | 弹窗类型 |
|---|---|---|
| 点击"返回"按钮 | `SimulationHeader.vue` | Element Plus `ElMessageBox.confirm` |
| 关闭标签页 / 导航离开 | `beforeunload` 事件 | 浏览器原生确认弹窗 |

### F.2 路径 1：返回按钮

`SimulationHeader.vue` 的返回按钮改造：

```typescript
// BEFORE:
function handleBack() {
  window.close()
}

// AFTER:
async function handleBack() {
  try {
    await ElMessageBox.confirm(
      '退出将关闭仿真容器，确定要离开吗？',
      '退出确认',
      {
        confirmButtonText: '确定退出',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
    // 用户确认退出 → 停止容器
    try {
      await stopMyContainerApi()
    } catch {
      // 停止失败也要退出（容器会被后端定时任务清理）
    }
    emit('back')
  } catch {
    // 用户取消 → 不操作
  }
}
```

`Simulation.vue` 中 `handleBack` 保持关闭标签页逻辑不变。

### F.3 路径 2：关闭标签页 / 导航离开

```typescript
// Simulation.vue

function handleBeforeUnload(event: BeforeUnloadEvent) {
  // 浏览器原生确认弹窗（文案由浏览器控制，无法自定义）
  event.preventDefault()
  event.returnValue = '退出将关闭仿真容器，确定要离开吗？'
}

onMounted(() => {
  window.addEventListener('beforeunload', handleBeforeUnload)
})

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', handleBeforeUnload)

  // 组件卸载时尝试停止容器
  // 使用 navigator.sendBeacon 发送最后一次请求
  // （因为 onBeforeUnmount 中 fetch 可能被浏览器取消）
  try {
    const token = getToken() // 从 storage 读取
    navigator.sendBeacon(
      '/api/v1/students/container/stop',
      new Blob(
        [JSON.stringify({})],
        { type: 'application/json' }
      )
    )
  } catch {
    // sendBeacon 不支持自定义 Header（无法带 JWT）
    // 退出后容器将由后端定时任务在心跳超时后自动关闭
  }
})
```

### F.4 sendBeacon 的 JWT 局限

`navigator.sendBeacon()` 无法设置 `Authorization` Header。解决方案：

**方案一（推荐）：专用退出端点，Token 放 body**

```python
# 后端新增
@router.post("/stop-on-exit", summary="页面退出时停止容器")
async def stop_on_exit(
    body: StopOnExitRequest,  # { token: str }
    db: AsyncSession = Depends(get_db),
):
    payload = verify_token(body.token)
    if not payload:
        return  # 静默失败
    student_id = payload.get("user_id")
    if not student_id:
        return
    container = await crud_container.get_container_by_student(db, student_id)
    if container and container.status == ContainerStatus.RUNNING:
        await crud_container.stop_container(db, container)
```

```typescript
// 前端
onBeforeUnmount(() => {
  const token = wsCache.get('token') // 从 sessionStorage 读取
  if (token) {
    navigator.sendBeacon(
      '/api/v1/students/container/stop-on-exit',
      new Blob(
        [JSON.stringify({ token })],
        { type: 'application/json' }
      )
    )
  }
})
```

**方案二：依赖心跳超时兜底**

不在退出时主动停止，完全依赖后端定时任务在心跳超时（2 分钟）后自动关闭。
- 优点：实现简单，无需处理 sendBeacon 的 JWT 问题
- 缺点：容器会多运行 ~2 分钟

> 建议：采用方案一 + 方案二双保险。sendBeacon 立即停止，心跳超时兜底。

---

## 五、文件变更清单

### 后端 (edubot-twin-server)

| 文件 | 操作 | 说明 |
|---|---|---|
| `app/models/container.py` | 修改 | 新增 `last_heartbeat_at` 字段 |
| `app/schemas/container.py` | 修改 | 新增 `StopOnExitRequest` Schema |
| `app/crud/container.py` | 修改 | 新增 `update_heartbeat()`、`find_stale_containers()` |
| `app/api/v1/endpoints/student/container.py` | 修改 | 新增 `/heartbeat`、`/stop`、`/stop-on-exit` 端点 |
| `app/main.py` | 修改 | 注册 lifespan 定时清理任务 |

### 前端 (edubot-twin-web)

| 文件 | 操作 | 说明 |
|---|---|---|
| `src/views/Simulation/Simulation.vue` | 修改 | 心跳定时器 + visibilitychange + beforeunload + 弹窗逻辑 |
| `src/views/Simulation/components/SimulationHeader.vue` | 修改 | 返回按钮增加退出确认弹窗 |
| `src/api/container/index.ts` | 修改 | 新增 `heartbeatApi`、`stopMyContainerApi`、`stopOnExitApi` |
| `src/api/container/types.ts` | 修改 | 新增 `StopOnExitRequest` 类型 |

---

## 六、API 端点总览（本期新增部分）

| 方法 | 路径 | 说明 | 鉴权 |
|---|---|---|---|
| POST | `/api/v1/students/container/heartbeat` | 心跳上报 | JWT |
| POST | `/api/v1/students/container/stop` | 主动停止容器 | JWT |
| POST | `/api/v1/students/container/stop-on-exit` | 页面退出时停止 | Token in body |

---

## 七、状态机完整图

```
                     学生点击"开始仿真"
                            │
                            ▼
                    ┌──────────────┐
                    │   CREATING   │◄────── destroy-and-recreate
                    └──────┬───────┘
                           │ Docker 创建成功
                           ▼
    ┌─────────────── ┌──────────────┐ ──────────────┐
    │                │   RUNNING    │               │
    │                └──────┬───────┘               │
    │                       │                       │
    │  心跳超时             │  学生退出              │  手动停止
    │  (2分钟)              │  (beforeunload)        │  (返回按钮)
    │                       │                       │
    │                       ▼                       │
    │                ┌──────────────┐               │
    └──────────────→ │   STOPPED    │◄──────────────┘
                     └──────┬───────┘
                            │
              ┌─────────────┼──────────────┐
              │             │              │
         学生选择         学生选择        管理员
         "重新启动"      "重新创建"       删除
              │             │              │
              ▼             ▼              ▼
         start() →     destroy-and-   delete() →
         RUNNING       recreate →      (记录删除)
                       CREATING →
                       RUNNING
```

---

## 八、风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| 浏览器冻结 JS 定时器 | 心跳停止，容器被误关 | 这是预期行为：长时间后台 = 离线，容器理应被关闭 |
| sendBeacon JWT 问题 | 退出时无法带鉴权 | 专用 `/stop-on-exit` 端点，Token 放 body |
| 定时任务误关正在使用的容器 | 学生操作中容器被停 | 前台心跳 30s < 超时阈值 120s，正常使用不会触发超时 |
| 数据库定时扫描压力 | 高并发时扫描慢 | `last_heartbeat_at` 加索引；当前 SQLite 规模(<500)无压力 |
| 多标签页打开同一仿真 | 心跳竞争 | 无影响：心跳 = 更新同一条记录的 `last_heartbeat_at`，多次更新幂等 |

---

## 九、验证方式

### 心跳机制验证

```bash
# 1. 打开仿真页面，观察后端日志是否每 30s 收到心跳
tail -f logs/server.log | grep heartbeat

# 2. 关闭仿真标签页，等待 2 分钟后检查容器状态
docker ps --filter label=edubot.type=simulation
# 预期：2 分钟后容器自动停止

# 3. 验证 Page Visibility 降频
# 切到其他标签页 → 观察心跳间隔变为 120s
# 切回仿真标签页 → 观察心跳恢复 30s
```

### 重新激活弹窗验证

```
1. 打开仿真页面，等待容器 running
2. 切到其他标签页，等待 > 2 分钟（容器被自动停止）
3. 切回仿真标签页
   预期：弹窗"仿真容器已关闭，是否重新启动？"
4. 点击"重新启动"
   预期：容器重新启动，GzWeb 和 ROS3D 重新连接
5. 重复步骤 2-3，点击"返回首页"
   预期：标签页关闭或跳转到学生首页
```

### 退出确认验证

```
1. 在仿真页面点击左上角"返回"按钮
   预期：弹窗"退出将关闭仿真容器，确定要离开吗？"
   - 点"确定退出"：容器停止，标签页关闭
   - 点"取消"：不操作

2. 直接关闭浏览器标签页（Ctrl+W）
   预期：浏览器原生确认弹窗"确认要离开此页面？"
   - 确认：容器通过 sendBeacon 停止（或 2 分钟后超时停止）
   - 取消：不操作
```
