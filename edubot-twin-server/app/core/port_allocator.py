"""
端口分配器

管理 gzbridge 和 rosbridge 的宿主机端口，避免冲突。

端口范围：
- gzbridge：9000 ~ 9499（支持 500 个并发容器）
- rosbridge：9500 ~ 9999
"""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.container import SimContainer, ContainerStatus

# 端口范围定义
GZBRIDGE_PORT_RANGE = (9000, 9499)
ROSBRIDGE_PORT_RANGE = (9500, 9999)

# 活跃状态（占用端口）
_ACTIVE_STATUSES = (ContainerStatus.CREATING, ContainerStatus.RUNNING)


class PortExhaustedError(Exception):
    """端口耗尽异常"""
    pass


async def allocate_ports(db: AsyncSession) -> tuple[int, int]:
    """
    分配一对可用端口 (gzbridge_port, rosbridge_port)

    算法：
    1. 查询 sim_containers 中 status IN (creating, running) 的记录
    2. 收集已占用的端口
    3. 找第一个未占用的端口对
    4. 若范围耗尽，抛出 PortExhaustedError

    Returns:
        (gzbridge_port, rosbridge_port)
    """
    # 查询活跃容器的端口占用情况
    result = await db.execute(
        select(SimContainer.gzbridge_port, SimContainer.rosbridge_port).where(
            SimContainer.status.in_(_ACTIVE_STATUSES)
        )
    )
    rows = result.all()

    used_gz_ports = {row[0] for row in rows if row[0] is not None}
    used_ros_ports = {row[1] for row in rows if row[1] is not None}

    # 读取内存中目前正在占用的 Dry Run 端口池
    from app.core.dry_run_manager import dry_run_manager
    for container_id in dry_run_manager.list_container_ids():
        session = dry_run_manager.get(container_id)
        if session:
            used_gz_ports.add(session.gzbridge_port)
            used_ros_ports.add(session.rosbridge_port)

    # 找第一个可用的 gzbridge 端口
    gz_port: Optional[int] = None
    for port in range(GZBRIDGE_PORT_RANGE[0], GZBRIDGE_PORT_RANGE[1] + 1):
        if port not in used_gz_ports:
            gz_port = port
            break

    if gz_port is None:
        raise PortExhaustedError(
            f"gzbridge 端口已耗尽（范围 {GZBRIDGE_PORT_RANGE[0]}-{GZBRIDGE_PORT_RANGE[1]}）"
        )

    # 找第一个可用的 rosbridge 端口
    ros_port: Optional[int] = None
    for port in range(ROSBRIDGE_PORT_RANGE[0], ROSBRIDGE_PORT_RANGE[1] + 1):
        if port not in used_ros_ports:
            ros_port = port
            break

    if ros_port is None:
        raise PortExhaustedError(
            f"rosbridge 端口已耗尽（范围 {ROSBRIDGE_PORT_RANGE[0]}-{ROSBRIDGE_PORT_RANGE[1]}）"
        )

    return gz_port, ros_port
