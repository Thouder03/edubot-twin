"""
容器 CRUD 操作（第三期：接入真实 Docker SDK）
"""
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.container import SimContainer, ContainerStatus
from app.schemas.container import ContainerCreate
from app.core.port_allocator import allocate_ports
from app.core import container_manager
from app.core.docker_client import DockerConnectionError


async def create_container(
    db: AsyncSession, data: ContainerCreate
) -> SimContainer:
    """
    创建仿真容器：先写 DB（status=CREATING），再调 Docker SDK

    若 Docker 操作失败，status 改为 ERROR 并记录 error_message。
    """
    gz_port, ros_port = await allocate_ports(db)

    # 先建数据库记录（status=CREATING）
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

    # 调用 Docker SDK 创建并启动容器
    try:
        docker_id = await container_manager.create_container(
            image=data.image_name,
            student_id=data.student_id,
            gz_port=gz_port,
            ros_port=ros_port,
        )
        container.container_id = docker_id
        container.status = ContainerStatus.RUNNING
        container.error_message = None
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


async def get_container_by_student(
    db: AsyncSession, student_id: int
) -> Optional[SimContainer]:
    """获取学生当前的容器（取最新的一个）"""
    result = await db.execute(
        select(SimContainer)
        .where(SimContainer.student_id == student_id)
        .order_by(SimContainer.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def start_container(
    db: AsyncSession, container: SimContainer
) -> SimContainer:
    """启动已停止的容器"""
    try:
        await container_manager.start_container(container.container_id)
        container.status = ContainerStatus.RUNNING
        container.error_message = None
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
    """停止运行中的容器"""
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
    """删除容器记录并移除 Docker 容器"""
    if container.container_id:
        await container_manager.remove_container(container.container_id)
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
            # last_heartbeat_at 为 NULL 或早于 cutoff
            (SimContainer.last_heartbeat_at == None)  # noqa: E711
            | (SimContainer.last_heartbeat_at < cutoff),
        )
    )
    return list(result.scalars().all())
