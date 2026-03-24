# SDD 第三期：Docker 全真接入与仿真启动流程

> 前置：第二期已完成容器管理 API 的 Mock 版本（`crud/container.py` 中 4 处 `# TODO: DOCKER`），前端已能通过 API 获取 gzbridge_url 动态初始化 GzWeb iframe。本期将 Mock 替换为真实 Docker 调用，并补齐"仿真启动 → 容器分配 → 自动连接"的完整闭环。

---

## 一、需求清单

| # | 需求 | 简述 |
|---|---|---|
| 1 | Docker SDK 接入 | 替换 `crud/container.py` 中 4 处 Mock，调用真实 Docker 管理镜像 `gzweb_sim:v1` |
| 2 | ROS3DViewer URL 自动注入 | 容器创建后，ROS3DViewer 的 `rosUrl` 自动设为该容器的 `rosbridge_url` |
| 3 | "开始仿真"弹窗 | 学生点击开始仿真后，根据已有容器状态弹出"继续/重建"确认 |
| 4 | JWT 鉴权改造 | 后端从 `Authorization: Bearer xxx` 自动提取 `student_id`，去掉 query param |

---

## 二、模块 A — Docker SDK 接入

### A.1 目标镜像

```
镜像名: gzweb_sim:v1
镜像 ID: 5a2d634a9e69
暴露端口:
  - 8080/tcp → GzBridge (GzWeb HTTP + WebSocket)
  - 9090/tcp → ROS Bridge (rosbridge_websocket)
```

### A.2 新建文件

#### `app/core/docker_client.py` — Docker 客户端单例

```python
"""
Docker 客户端单例

连接策略：
1. 优先读取环境变量 DOCKER_HOST（支持远程 Docker）
2. 默认使用 unix:///var/run/docker.sock
"""
import docker
from docker import DockerClient
from docker.errors import DockerException

_client: DockerClient | None = None


class DockerConnectionError(Exception):
    """Docker 守护进程连接失败"""
    pass


def get_docker_client() -> DockerClient:
    """
    获取 Docker 客户端（模块级单例）

    Raises:
        DockerConnectionError: Docker 守护进程不可达
    """
    global _client
    if _client is None:
        try:
            _client = docker.from_env(timeout=10)
            _client.ping()  # 验证连接
        except DockerException as e:
            _client = None
            raise DockerConnectionError(
                f"无法连接 Docker 守护进程: {e}"
            ) from e
    return _client
```

#### `app/core/container_manager.py` — 容器生命周期管理器

```python
"""
容器生命周期管理器

所有 Docker SDK 调用（同步）通过 run_in_executor 包装为异步，
避免阻塞 FastAPI 事件循环。
"""
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from docker.errors import NotFound, APIError

from app.core.docker_client import get_docker_client, DockerConnectionError

logger = logging.getLogger(__name__)

# 专用线程池：Docker 操作可能耗时较长，独立于默认线程池
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="docker")


async def _run_in_executor(func, *args):
    """将同步 Docker 调用包装为异步"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, func, *args)


# ─── 容器创建 ───────────────────────────────────────────────

async def create_container(
    image: str,
    student_id: int,
    gz_port: int,
    ros_port: int,
) -> str:
    """
    创建并启动 Docker 容器

    Args:
        image: 镜像名 (如 gzweb_sim:v1)
        student_id: 学生 ID（用于容器命名和标签）
        gz_port: 宿主机 gzbridge 映射端口
        ros_port: 宿主机 rosbridge 映射端口

    Returns:
        容器 short_id (12 位 hex)

    Raises:
        DockerConnectionError: Docker 不可达
        APIError: 容器创建失败（如端口冲突、镜像不存在）
    """
    def _sync():
        client = get_docker_client()
        container_name = f"edubot-sim-{student_id}"

        # 清理同名残留容器（防止 name conflict）
        try:
            old = client.containers.get(container_name)
            old.remove(force=True)
            logger.warning(f"已清理残留容器: {container_name}")
        except NotFound:
            pass

        container = client.containers.run(
            image=image,
            detach=True,
            name=container_name,
            ports={
                "8080/tcp": gz_port,
                "9090/tcp": ros_port,
            },
            mem_limit="2g",
            nano_cpus=2_000_000_000,  # 2 CPU cores
            labels={
                "edubot.student_id": str(student_id),
                "edubot.type": "simulation",
            },
            remove=False,
        )
        return container.short_id

    return await _run_in_executor(_sync)


# ─── 容器启动 ───────────────────────────────────────────────

async def start_container(container_id: str) -> None:
    """启动已停止的容器"""
    def _sync():
        client = get_docker_client()
        container = client.containers.get(container_id)
        container.start()

    await _run_in_executor(_sync)


# ─── 容器停止 ───────────────────────────────────────────────

async def stop_container(container_id: str, timeout: int = 10) -> None:
    """
    停止运行中的容器

    Args:
        container_id: Docker 容器 ID
        timeout: 等待优雅退出的秒数，超时后 SIGKILL
    """
    def _sync():
        client = get_docker_client()
        container = client.containers.get(container_id)
        container.stop(timeout=timeout)

    await _run_in_executor(_sync)


# ─── 容器删除 ───────────────────────────────────────────────

async def remove_container(container_id: str, force: bool = True) -> None:
    """删除容器"""
    def _sync():
        client = get_docker_client()
        try:
            container = client.containers.get(container_id)
            container.remove(force=force)
        except NotFound:
            logger.info(f"容器 {container_id} 已不存在，跳过删除")

    await _run_in_executor(_sync)


# ─── 容器状态查询 ─────────────────────────────────────────────

async def inspect_container(container_id: str) -> str | None:
    """
    查询容器运行状态

    Returns:
        Docker 原生状态字符串 ('running', 'exited', 'created', 'dead', 等)
        容器不存在时返回 None
    """
    def _sync():
        client = get_docker_client()
        try:
            container = client.containers.get(container_id)
            container.reload()
            return container.status
        except NotFound:
            return None

    return await _run_in_executor(_sync)
```

### A.3 改造 `crud/container.py`

将 4 处 `# TODO: DOCKER` 替换为 `container_manager` 调用。关键改动：

```python
# ─── create_container ────────────────────────────────
# BEFORE (Mock):
#   mock_container_id = _generate_mock_container_id()
#   container = SimContainer(..., status=ContainerStatus.RUNNING)

# AFTER:
from app.core import container_manager
from app.core.docker_client import DockerConnectionError

async def create_container(db, data):
    gz_port, ros_port = await allocate_ports(db)

    # 先写入数据库（status=CREATING）
    container = SimContainer(
        container_id=None,
        student_id=data.student_id,
        image_name=data.image_name,
        status=ContainerStatus.CREATING,
        gzbridge_port=gz_port,
        rosbridge_port=ros_port,
    )
    db.add(container)
    await db.commit()
    await db.refresh(container)

    # 异步创建 Docker 容器
    try:
        docker_id = await container_manager.create_container(
            image=data.image_name,
            student_id=data.student_id,
            gz_port=gz_port,
            ros_port=ros_port,
        )
        container.container_id = docker_id
        container.status = ContainerStatus.RUNNING
    except (DockerConnectionError, Exception) as e:
        container.status = ContainerStatus.ERROR
        container.error_message = str(e)

    container.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(container)
    return container


# ─── start_container ─────────────────────────────────
# BEFORE: container.status = ContainerStatus.RUNNING
# AFTER:
async def start_container(db, container):
    try:
        await container_manager.start_container(container.container_id)
        container.status = ContainerStatus.RUNNING
    except Exception as e:
        container.status = ContainerStatus.ERROR
        container.error_message = str(e)
    container.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(container)
    return container


# ─── stop_container ──────────────────────────────────
# BEFORE: container.status = ContainerStatus.STOPPED
# AFTER:
async def stop_container(db, container):
    try:
        await container_manager.stop_container(container.container_id)
        container.status = ContainerStatus.STOPPED
    except Exception as e:
        container.status = ContainerStatus.ERROR
        container.error_message = str(e)
    container.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(container)
    return container


# ─── delete_container ────────────────────────────────
# BEFORE: await db.delete(container)
# AFTER:
async def delete_container(db, container):
    if container.container_id:
        await container_manager.remove_container(container.container_id)
    await db.delete(container)
    await db.commit()
    return True
```

### A.4 模型变更

`app/models/container.py` 增加 `error_message` 字段：

```python
error_message: Mapped[Optional[str]] = mapped_column(
    String(500), nullable=True,
    comment="Docker 操作异常信息"
)
```

### A.5 Schema 变更

`app/schemas/container.py`:

- `ContainerCreate.image_name` 默认值改为 `"gzweb_sim:v1"`
- `ContainerResponse` 增加 `error_message: Optional[str] = None`

### A.6 异常处理策略

| 异常场景 | 处理方式 |
|---|---|
| Docker 守护进程不可达 | `DockerConnectionError` → API 返回 503 |
| 镜像不存在 | `ImageNotFound` → API 返回 400，提示镜像名 |
| 端口冲突（宿主机端口被占） | `APIError` → 回滚端口分配，重试一次 |
| 容器创建超时 | `asyncio.wait_for(timeout=60)` → status=ERROR |
| 同名容器残留 | 创建前 `remove(force=True)` 清理 |

### A.7 环境要求

```bash
# requirements.txt 新增
docker>=7.0

# 运行时要求
# 1. Docker Engine >= 20.10
# 2. FastAPI 进程用户需在 docker 组中
sudo usermod -aG docker $USER

# 3. 确认镜像存在
docker images gzweb_sim:v1
```

---

## 三、模块 B — ROS3DViewer URL 自动注入

### B.1 当前问题

- `Simulation.vue` 从 API 获取 `gzbridge_url` 用于 GzWeb，但 `rosbridge_url` 被丢弃
- `ROS3DViewer` 的 `rosUrl` 默认 `ws://localhost:9090`，需手动在设置面板修改
- 学生无从知道自己容器的 rosbridge 端口

### B.2 方案：provide/inject

**`Simulation.vue`（提供方）：**

```typescript
// 新增：容器连接信息 provide
const containerRosUrl = ref<string | null>(null)
provide('containerRosUrl', readonly(containerRosUrl))

onMounted(async () => {
  // ... 现有暗色模式逻辑 ...

  try {
    const res = await getMyContainerApi()
    const gzUrl = res?.data?.gzbridge_url
    const rosUrl = res?.data?.rosbridge_url

    // GzWeb 初始化（现有逻辑）
    initGzBridge(gzUrl || gzDefaultConfig.gzwebUrl)

    // ROS URL 注入（新增）
    if (rosUrl) {
      containerRosUrl.value = rosUrl
    }
  } catch (err) {
    initGzBridge(gzDefaultConfig.gzwebUrl)
  }
})
```

**`ROS3DViewer/index.vue`（消费方）：**

```typescript
// 新增：接收容器 ROS URL
const containerRosUrl = inject<Readonly<Ref<string | null>>>('containerRosUrl', ref(null))

// 监听注入值变化，自动更新 Renderer 配置
watch(containerRosUrl, (newUrl) => {
  if (newUrl && renderer.value) {
    renderer.value.updateConfig((draft) => {
      draft.connection.rosUrl = newUrl
    })
  }
}, { immediate: true })
```

### B.3 优先级规则

```
1. API 返回的 rosbridge_url（容器动态端口）  ← 最高优先
2. 用户在设置面板手动输入的值
3. RendererConfig localStorage 持久化值
4. 默认值 ws://localhost:9090                ← 最低优先
```

设置面板仍可手动修改 rosUrl（覆盖自动注入值），便于调试。

---

## 四、模块 C — "开始仿真"弹窗

### C.1 交互流程

```
学生点击 [开始仿真] (Home.vue)
    │
    ├─ 调用 getMyContainerApi()
    │
    ├── 情况 1: 404（无容器）
    │   └─ 自动调用 requestContainerApi() 创建
    │   └─ 等待 status → running（轮询，最多 60s）
    │   └─ 成功 → 打开仿真页 / 失败 → "启动失败，请联系教师"
    │
    ├── 情况 2: status === 'running'
    │   └─ 弹窗确认:
    │       ┌─────────────────────────────────────┐
    │       │  发现正在运行的仿真环境               │
    │       │  是否继续使用？                       │
    │       │                                     │
    │       │  [继续使用]          [重新创建]       │
    │       └─────────────────────────────────────┘
    │       ├─ [继续使用] → 直接打开仿真页
    │       └─ [重新创建] → 调用 destroyAndRecreateApi()
    │           → 等待 running → 打开仿真页
    │
    ├── 情况 3: status === 'stopped'
    │   └─ 弹窗确认:
    │       ┌─────────────────────────────────────┐
    │       │  发现上次的仿真环境（已暂停）          │
    │       │  是否恢复使用？                       │
    │       │                                     │
    │       │  [恢复使用]          [重新创建]       │
    │       └─────────────────────────────────────┘
    │       ├─ [恢复使用] → 调用 startMyContainerApi()
    │       │   → 等待 running → 打开仿真页
    │       └─ [重新创建] → 调用 destroyAndRecreateApi()
    │           → 等待 running → 打开仿真页
    │
    ├── 情况 4: status === 'error' 或 'creating'
    │   └─ 自动调用 destroyAndRecreateApi()
    │   └─ 等待 running → 打开仿真页
    │
    └── API 异常
        ├─ 503 → "服务器资源已满，请稍后再试"
        └─ 其他 → "网络错误，请检查连接"
```

### C.2 等待容器就绪的轮询逻辑

```typescript
/**
 * 等待容器进入 running 状态
 *
 * @param maxWaitMs 最大等待时间（默认 60 秒）
 * @param intervalMs 轮询间隔（默认 2 秒）
 * @returns 容器信息（成功）或 null（超时）
 */
async function waitForContainerRunning(
  maxWaitMs = 60_000,
  intervalMs = 2_000
): Promise<ContainerStatusResponse | null> {
  const deadline = Date.now() + maxWaitMs
  while (Date.now() < deadline) {
    const res = await getMyContainerApi()
    if (res?.data?.status === 'running') return res.data
    if (res?.data?.status === 'error') return null // 创建失败，不再等待
    await new Promise(r => setTimeout(r, intervalMs))
  }
  return null // 超时
}
```

### C.3 新增后端端点

#### `POST /api/v1/students/container/destroy-and-recreate`

原子操作：销毁当前容器 + 创建新容器。避免前端分两步调用导致的竞态条件。

```python
@router.post(
    "/destroy-and-recreate",
    response_model=ContainerResponse,
    summary="销毁当前容器并创建新容器",
)
async def destroy_and_recreate(
    student_id: int = Depends(get_current_student_id),
    db: AsyncSession = Depends(get_db),
):
    """
    1. 查找学生当前容器
    2. 若存在 → 停止并删除（释放端口）
    3. 创建新容器
    """
    existing = await crud_container.get_container_by_student(db, student_id)
    if existing:
        await crud_container.delete_container(db, existing)

    container = await crud_container.create_container(
        db, ContainerCreate(student_id=student_id)
    )
    return ContainerResponse.model_validate(container)
```

#### `POST /api/v1/students/container/start`

学生端启动已停止的容器（现有 `request` 端点只创建不启动）。

```python
@router.post(
    "/start",
    response_model=ContainerStatusResponse,
    summary="启动学生的已停止容器",
)
async def start_my_container(
    student_id: int = Depends(get_current_student_id),
    db: AsyncSession = Depends(get_db),
):
    container = await crud_container.get_container_by_student(db, student_id)
    if not container:
        raise HTTPException(404, "尚未分配容器")
    if container.status == ContainerStatus.RUNNING:
        return ContainerStatusResponse.from_orm_with_host(container)
    if container.status not in (ContainerStatus.STOPPED,):
        raise HTTPException(400, f"容器状态 {container.status} 不可启动")

    container = await crud_container.start_container(db, container)
    return ContainerStatusResponse.from_orm_with_host(container)
```

### C.4 前端 API 层变更

`src/api/container/index.ts` 新增：

```typescript
/** 销毁当前容器并创建新容器 */
export const destroyAndRecreateApi = (): Promise<IResponse<ContainerResponse>> => {
  return request.post({ url: '/students/container/destroy-and-recreate' })
}

/** 启动学生的已停止容器 */
export const startMyContainerApi = (): Promise<IResponse<ContainerStatusResponse>> => {
  return request.post({ url: '/students/container/start' })
}
```

同时，`getMyContainerApi` 和 `requestContainerApi` **去掉 `studentId` 参数**（后端从 JWT 自动提取）：

```typescript
// BEFORE: getMyContainerApi(studentId: number)
// AFTER:
export const getMyContainerApi = (): Promise<IResponse<ContainerStatusResponse>> => {
  return request.get({ url: '/students/container/mine' })
}

export const requestContainerApi = (): Promise<IResponse<ContainerResponse>> => {
  return request.post({ url: '/students/container/request' })
}
```

---

## 五、模块 D — JWT 鉴权改造

### D.1 现状

- `security.py` 已有 `create_access_token()` 和 `verify_token()`
- Token payload 包含 `{ sub: username, user_id: student.id, role: "student" }`
- `/me` 端点通过 query param `?token=xxx` 传递 token
- 容器端点通过 query param `?student_id=xxx` 传递学生 ID

### D.2 改造内容

#### 后端：`app/core/security.py` 新增依赖注入函数

```python
from fastapi import Header, HTTPException, status


async def get_current_student_id(
    authorization: str = Header(
        ...,
        description="Bearer token，格式: Bearer <jwt_token>"
    ),
) -> int:
    """
    从 Authorization Header 提取 student_id

    用法: student_id: int = Depends(get_current_student_id)

    Raises:
        HTTPException(401): Token 无效或角色不是学生
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header 格式错误，需要 'Bearer <token>'"
        )

    token = authorization[7:]  # 去掉 "Bearer " 前缀
    payload = verify_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期"
        )

    user_id = payload.get("user_id")
    role = payload.get("role")

    if not user_id or role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅学生可访问此接口"
        )

    return user_id
```

#### 后端：`student/container.py` 端点改造

```python
# BEFORE:
# async def get_my_container(
#     student_id: int = Query(...),
#     db: AsyncSession = Depends(get_db),
# ):

# AFTER:
from app.core.security import get_current_student_id

async def get_my_container(
    student_id: int = Depends(get_current_student_id),
    db: AsyncSession = Depends(get_db),
):
    # 函数体不变，student_id 从 JWT 自动获取
```

所有学生端容器端点（`/mine`, `/request`, `/destroy-and-recreate`, `/start`）统一使用 `Depends(get_current_student_id)`。

#### 前端：去掉硬编码

```typescript
// Simulation.vue
// BEFORE: const TEMP_STUDENT_ID = 1
// AFTER:  删除此行。API 调用不再需要 studentId 参数。
```

---

## 六、文件变更清单

### 后端 (edubot-twin-server)

| 文件 | 操作 | 说明 |
|---|---|---|
| `app/core/docker_client.py` | **新建** | Docker 客户端单例 |
| `app/core/container_manager.py` | **新建** | 容器生命周期管理器（异步封装） |
| `app/core/security.py` | 修改 | 新增 `get_current_student_id()` |
| `app/crud/container.py` | 修改 | 4 处 TODO: DOCKER 替换为真实调用 |
| `app/models/container.py` | 修改 | 新增 `error_message` 字段 |
| `app/schemas/container.py` | 修改 | `image_name` 默认值 → `gzweb_sim:v1`；`ContainerResponse` 增加 `error_message` |
| `app/api/v1/endpoints/student/container.py` | 修改 | JWT 鉴权 + 新增 `destroy-and-recreate`, `start` 端点 |
| `requirements.txt` | 修改 | 新增 `docker>=7.0` |

### 前端 (edubot-twin-web)

| 文件 | 操作 | 说明 |
|---|---|---|
| `src/views/Student/Home.vue` | 修改 | "开始仿真"按钮增加容器预检 + 弹窗流程 |
| `src/views/Simulation/Simulation.vue` | 修改 | 去掉 `TEMP_STUDENT_ID`；provide `containerRosUrl` |
| `src/views/Simulation/panels/ROS3DViewer/index.vue` | 修改 | inject `containerRosUrl`，自动更新 `rosUrl` |
| `src/api/container/index.ts` | 修改 | 去掉 `studentId` 参数 + 新增 `destroyAndRecreateApi`, `startMyContainerApi` |
| `src/api/container/types.ts` | 修改 | `ContainerResponse` 增加 `error_message` |

---

## 七、API 端点总览（改造后）

### 学生端（`/api/v1/students/container`）

| 方法 | 路径 | 说明 | 鉴权 |
|---|---|---|---|
| GET | `/mine` | 获取我的容器状态 | JWT (自动) |
| POST | `/request` | 请求分配容器（无则创建） | JWT |
| POST | `/start` | **新增** 启动已停止的容器 | JWT |
| POST | `/destroy-and-recreate` | **新增** 销毁旧容器并新建 | JWT |

### 教师端（`/api/v1/teachers/containers`）— 不变

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/` | 创建容器 |
| GET | `/` | 列出所有容器 |
| GET | `/{id}` | 获取容器详情 |
| POST | `/{id}/start` | 启动容器 |
| POST | `/{id}/stop` | 停止容器 |
| DELETE | `/{id}` | 删除容器 |

---

## 八、风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| Docker 守护进程不可达 | 所有容器操作失败 | `docker_client.py` 启动时 ping 检测；API 返回 503 + 明确错误信息 |
| 容器创建慢（首次拉取镜像） | API 超时 | 前端异步轮询（最多 60s），不阻塞 API 请求 |
| 宿主机端口被占 | 容器创建失败 | `create_container` 捕获 `APIError`，设 status=ERROR 并提示端口冲突 |
| 同名容器残留 | 创建失败 (Conflict) | 创建前 `remove(force=True)` 清理同名容器 |
| JWT Token 过期 | 容器操作被拒 | 前端请求拦截器检测 401，跳转登录页 |

---

## 九、验证方式

### 后端验证

```bash
# 1. Docker 连接测试
curl -X POST http://localhost:8000/api/v1/students/container/request \
  -H "Authorization: Bearer <student_token>"
# 预期：返回 status=creating 或 status=running

# 2. 容器销毁重建
curl -X POST http://localhost:8000/api/v1/students/container/destroy-and-recreate \
  -H "Authorization: Bearer <student_token>"
# 预期：旧容器被删除，新容器创建

# 3. 验证 Docker 容器存在
docker ps --filter label=edubot.type=simulation
# 预期：看到 edubot-sim-{student_id} 容器

# 4. 端口映射验证
curl http://localhost:9000  # gzbridge 页面
# 预期：GzWeb 界面响应
```

### 前端验证

```
1. 学生登录 → 点击"开始仿真"
   - 首次：自动创建容器 → 等待就绪 → 打开仿真页 → GzWeb + ROS3D 自动连接
   - 有容器(running)：弹窗"继续使用？" → 是 → 直接打开
   - 有容器(stopped)：弹窗"恢复使用？" → 是 → 启动 → 打开
   - 点"重新创建"：旧容器被删 → 新容器创建 → 打开

2. 仿真页面内
   - ROS3DViewer 设置面板中 rosUrl 应自动填充为容器的 rosbridge_url
   - GzWeb iframe 应自动连接到容器的 gzbridge
```
