"""
教师端 - 容器运行监控 API

路由前缀：/api/v1/teachers/containers/monitor
"""
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.core.security import get_current_teacher
from app.core.container_manager import get_container_stats
from app.models.container import SimContainer, ContainerStatus
from app.schemas.container import ContainerMonitorInfo, ContainerMonitorListResponse
from app.schemas.common import ApiResponse

router = APIRouter()


@router.get(
    "",
    response_model=ApiResponse[ContainerMonitorListResponse],
    summary="获取容器运行监控列表",
)
async def get_container_monitor(
    pageIndex: int = Query(default=1, ge=1, description="页码"),
    pageSize: int = Query(default=50, ge=1, le=200, description="每页数量"),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_teacher),
):
    """
    获取所有容器的实时运行监控数据。

    - 通过 selectinload 预加载关联用户，避免 N+1 查询
    - 对 running 状态的容器调用 Docker stats 获取 CPU/内存数据
    - 非 running 状态的容器，CPU/内存返回 0，uptime_seconds 返回 0
    """
    offset = (pageIndex - 1) * pageSize

    # 获取总数
    count_result = await db.execute(select(func.count()).select_from(SimContainer))
    total = count_result.scalar_one()

    # 分页查询，预加载 user 关联
    result = await db.execute(
        select(SimContainer)
        .options(selectinload(SimContainer.user))
        .offset(offset)
        .limit(pageSize)
        .order_by(SimContainer.id.desc())
    )
    containers: List[SimContainer] = list(result.scalars().all())

    now = datetime.utcnow()
    monitor_list = []

    for container in containers:
        user = container.user
        cpu_percent = 0.0
        memory_mb = 0
        memory_limit_mb = 2048

        # 仅对 running 状态容器调用 Docker stats
        if container.status == ContainerStatus.RUNNING and container.container_id:
            try:
                import asyncio
                stats = await asyncio.wait_for(
                    get_container_stats(container.container_id),
                    timeout=3.0
                )
                if stats:
                    cpu_percent = stats.cpu_percent
                    memory_mb = int(stats.memory_usage / 1024 / 1024)
                    memory_limit_mb = int(stats.memory_limit / 1024 / 1024) or 2048
            except Exception:
                # 单个容器 stats 失败不影响整体列表
                pass

        # 运行时长：仅 running 状态下累计
        uptime_seconds = 0
        if container.status == ContainerStatus.RUNNING:
            uptime_seconds = int((now - container.created_at).total_seconds())

        monitor_list.append(ContainerMonitorInfo(
            id=container.id,
            container_id=container.container_id,
            student_id=user.id if user else 0,
            student_name=user.real_name if user else "未知",
            student_username=user.username if user else "未知",
            purpose=container.purpose or "",
            status=container.status.value if hasattr(container.status, 'value') else str(container.status),
            image_name=container.image_name,
            cpu_percent=cpu_percent,
            memory_mb=memory_mb,
            memory_limit_mb=memory_limit_mb,
            uptime_seconds=uptime_seconds,
            created_at=container.created_at,
            last_heartbeat_at=container.last_heartbeat_at,
        ))

    return ApiResponse(data=ContainerMonitorListResponse(
        total=total,
        list=monitor_list,
    ))
