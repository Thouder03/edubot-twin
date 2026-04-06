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
    - launch_file_path / launch_args
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
            launch_file_path=data.launch_file_path or "/home/ubuntu20/catkin_ws/src/bingda_tutorials/launch/simulation_robot.launch",
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
            # 已有心跳：按心跳时间判定
            # 无心跳：按创建时间判定（给新容器首心跳留出超时窗口）
            ((SimContainer.last_heartbeat_at != None) & (SimContainer.last_heartbeat_at < cutoff))  # noqa: E711
            | ((SimContainer.last_heartbeat_at == None) & (SimContainer.created_at < cutoff)),  # noqa: E711
        )
    )
    return list(result.scalars().all())
