"""
容器 CRUD 操作（第三期：接入真实 Docker SDK）
"""
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import container_manager
from app.core.docker_client import DockerConnectionError
from app.core.port_allocator import allocate_ports
from app.models.container import ContainerStatus, SimContainer
from app.schemas.container import ContainerCreate


async def create_container(
    db: AsyncSession, data: ContainerCreate
) -> SimContainer:
    """
    创建仿真容器：先写 DB（status=CREATING），再调 Docker SDK。

    支持 10-S1 动态注入参数链路：
    - launch_args
    - startup_script_path
    - env_volumes

    若 Docker 操作失败，status 改为 ERROR 并记录 error_message。
    """
    gz_port, ros_port = await allocate_ports(db)

    # 先建数据库记录（status=CREATING）
    container = SimContainer(
        container_id=None,
        user_id=data.user_id,
        image_name=data.image_name,
        status=ContainerStatus.CREATING,
        gzbridge_port=gz_port,
        rosbridge_port=ros_port,
        current_version_id=data.current_version_id,
        purpose=data.purpose,
    )
    db.add(container)
    await db.commit()
    await db.refresh(container)

    # 调用 Docker SDK 创建并启动容器
    try:
        docker_id = await container_manager.create_container(
            image=data.image_name,
            student_id=data.user_id,
            gz_port=gz_port,
            ros_port=ros_port,
            launch_args=data.launch_args,
            startup_script_path=data.startup_script_path,
            env_volumes=data.env_volumes,
        )
        container.container_id = docker_id
        container.status = ContainerStatus.RUNNING
        container.error_message = None
        # 避免“容器刚启动、首个前端心跳未到”被定时任务误判为超时
        container.last_heartbeat_at = datetime.utcnow()
    except (DockerConnectionError, Exception) as e:
        container.status = ContainerStatus.ERROR
        container.error_message = str(e)

    container.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(container)
    return container


async def list_containers(
    db: AsyncSession, skip: int = 0, limit: int = 100
) -> list[SimContainer]:
    """获取所有容器列表（分页）"""
    result = await db.execute(
        select(SimContainer).offset(skip).limit(limit).order_by(SimContainer.id)
    )
    return list(result.scalars().all())


async def get_container(db: AsyncSession, container_id: int) -> Optional[SimContainer]:
    """根据 DB id 获取容器"""
    result = await db.execute(
        select(SimContainer).where(SimContainer.id == container_id)
    )
    return result.scalar_one_or_none()


async def get_container_by_user(
    db: AsyncSession, user_id: int
) -> Optional[SimContainer]:
    """获取用户当前的容器（取最新的一个）。"""
    result = await db.execute(
        select(SimContainer)
        .where(SimContainer.user_id == user_id)
        .order_by(SimContainer.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_container_by_student(
    db: AsyncSession, student_id: int
) -> Optional[SimContainer]:
    """兼容学生语义的容器查询。"""
    return await get_container_by_user(db, student_id)


async def get_containers_by_user(
    db: AsyncSession, user_id: int
) -> list[SimContainer]:
    """获取用户的所有容器。"""
    result = await db.execute(select(SimContainer).where(SimContainer.user_id == user_id))
    return list(result.scalars().all())


async def get_containers_by_student(
    db: AsyncSession, student_id: int
) -> list[SimContainer]:
    """兼容学生语义的容器列表查询。"""
    return await get_containers_by_user(db, student_id)


async def start_container(
    db: AsyncSession, container: SimContainer
) -> SimContainer:
    """启动已停止的容器"""
    try:
        await container_manager.start_container(container.container_id)
        container.status = ContainerStatus.RUNNING
        container.error_message = None
        # 重启后给首个前端心跳预留窗口，避免被立即判定 stale
        container.last_heartbeat_at = datetime.utcnow()
    except Exception as e:
        container.status = ContainerStatus.ERROR
        container.error_message = str(e)
    container.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(container)
    return container


async def stop_container(
    db: AsyncSession, container: SimContainer
) -> SimContainer:
    """停止运行中的容器。先标记 stopping，再执行 Docker stop，避免启动/停止竞态。"""
    container.status = ContainerStatus.STOPPING
    container.updated_at = datetime.utcnow()
    await db.commit()

    try:
        await container_manager.stop_container(container.container_id)
        container.status = ContainerStatus.STOPPED
        container.error_message = None
    except Exception as e:
        container.status = ContainerStatus.ERROR
        container.error_message = str(e)

    container.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(container)
    return container


async def delete_container(db: AsyncSession, container: SimContainer) -> bool:
    """
    删除容器记录并移除 Docker 容器。

    加固点：先将状态切到 REMOVING 落库，再调 Docker 删除。如果 Docker 侧
    抛异常（daemon 不可达、容器 stuck 等），不再静默吞掉——把 DB 状态
    标记为 ERROR 后抛出异常给调用方，同时让孤儿容器 reconcile 循环
    在下一轮扫描时兜底处理（阶段 B / 阶段 C）。
    """
    container.status = ContainerStatus.REMOVING
    container.updated_at = datetime.utcnow()
    await db.commit()

    if container.container_id:
        try:
            await container_manager.remove_container(container.container_id)
        except Exception as e:
            container.status = ContainerStatus.ERROR
            container.error_message = f"docker remove failed: {e}"[:500]
            container.updated_at = datetime.utcnow()
            await db.commit()
            raise

    await db.delete(container)
    await db.commit()
    return True


async def update_heartbeat(db: AsyncSession, container: SimContainer) -> None:
    """更新心跳时间"""
    container.last_heartbeat_at = datetime.utcnow()
    container.updated_at = datetime.utcnow()
    await db.commit()


async def find_stale_containers(
    db: AsyncSession,
    timeout_seconds: int = 120,
) -> list:
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
            # 已有心跳：按心跳时间判定
            # 无心跳：按创建时间判定（给新容器首心跳留出超时窗口）
            ((SimContainer.last_heartbeat_at != None) & (SimContainer.last_heartbeat_at < cutoff))  # noqa: E711
            | ((SimContainer.last_heartbeat_at == None) & (SimContainer.created_at < cutoff)),  # noqa: E711
        )
    )
    return list(result.scalars().all())


# ─── 孤儿容器自洗支持查询 ───────────────────────────────────────────────

async def find_zombie_state_containers(
    db: AsyncSession,
    timeout_seconds: int = 200,
) -> list[SimContainer]:
    """
    查找状态僵死的容器：处于 CREATING/STOPPING/REMOVING 中间态
    且 updated_at 超过 timeout_seconds 未推进的记录。

    这些记录很可能是协程异常、reload 中断、宿主机重启等导致链路锁
    永远无法推进到终态的「死锁」，由孤儿清洗循环阶段 A 负责回收。
    """
    cutoff = datetime.utcnow() - timedelta(seconds=timeout_seconds)
    result = await db.execute(
        select(SimContainer).where(
            SimContainer.status.in_(
                [
                    ContainerStatus.CREATING,
                    ContainerStatus.STOPPING,
                    ContainerStatus.REMOVING,
                ]
            ),
            SimContainer.updated_at < cutoff,
        )
    )
    return list(result.scalars().all())


async def find_db_containers(db: AsyncSession) -> list[SimContainer]:
    """
    查找 DB 中所有「应当存在对应 Docker 容器」的活跃记录，
    用于孤儿清洗循环阶段 B（DB → Docker 校准）。

    仅返回 container_id 非空、状态为 RUNNING 或 CREATING 的记录。
    """
    result = await db.execute(
        select(SimContainer).where(
            SimContainer.container_id.isnot(None),
        )
    )
    return list(result.scalars().all())


async def get_known_container_ids(db: AsyncSession) -> set[str]:
    """
    返回 DB 中所有非空 container_id 集合，用于孤儿清洗循环阶段 C
    （Docker → DB 反向清洗）做差集计算物理孤儿。

    不限制状态：只要 DB 中存在该 container_id 的记录，就不会被
    视为物理孤儿（哪怕其状态已是 STOPPED / ERROR）。
    """
    result = await db.execute(
        select(SimContainer.container_id).where(
            SimContainer.container_id.isnot(None)
        )
    )
    return {row[0] for row in result.all() if row[0]}
