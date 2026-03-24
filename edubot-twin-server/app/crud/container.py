"""
容器 CRUD 操作

注意：Docker 实际调用以 Mock 方式占位（直接设 status=RUNNING），
接口与 SDD 完全一致，后续接入真实 Docker 环境时只需替换带 # TODO: DOCKER 注释的部分。
"""
import random
import string
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.container import SimContainer, ContainerStatus
from app.schemas.container import ContainerCreate
from app.core.port_allocator import allocate_ports


def _generate_mock_container_id() -> str:
    """生成模拟的 Docker 容器 ID（12 位 hex）"""
    return "".join(random.choices(string.hexdigits[:16], k=12)).lower()


async def create_container(
    db: AsyncSession, data: ContainerCreate
) -> SimContainer:
    """
    创建仿真容器记录并（Mock）启动 Docker 容器

    Args:
        db: 数据库会话
        data: 创建请求

    Returns:
        创建的 SimContainer 对象
    """
    gz_port, ros_port = await allocate_ports(db)

    # TODO: DOCKER — 替换为真实 docker run 调用
    # docker_client.containers.run(
    #     image=data.image_name, detach=True,
    #     ports={'8080/tcp': gz_port, '9090/tcp': ros_port},
    #     mem_limit='2g', cpus=2.0,
    #     name=f'edubot-sim-{data.student_id}'
    # )
    mock_container_id = _generate_mock_container_id()

    container = SimContainer(
        container_id=mock_container_id,
        student_id=data.student_id,
        image_name=data.image_name,
        status=ContainerStatus.RUNNING,  # Mock：跳过 CREATING 阶段
        gzbridge_port=gz_port,
        rosbridge_port=ros_port,
    )
    db.add(container)
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
    """根据 ID 获取容器"""
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
    # TODO: DOCKER — docker_client.containers.get(container.container_id).start()
    container.status = ContainerStatus.RUNNING
    container.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(container)
    return container


async def stop_container(
    db: AsyncSession, container: SimContainer
) -> SimContainer:
    """停止运行中的容器"""
    # TODO: DOCKER — docker_client.containers.get(container.container_id).stop()
    container.status = ContainerStatus.STOPPED
    container.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(container)
    return container


async def delete_container(db: AsyncSession, container: SimContainer) -> bool:
    """删除容器记录（并 Mock 删除 Docker 容器）"""
    # TODO: DOCKER — docker_client.containers.get(container.container_id).remove(force=True)
    await db.delete(container)
    await db.commit()
    return True
