from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from datetime import datetime, timedelta
from typing import List, Optional

from app.models.container_metrics import ContainerMetrics
from app.schemas.container_metrics import ContainerMetricsCreate


async def create_metrics(db: AsyncSession, metrics: ContainerMetricsCreate) -> ContainerMetrics:
    """创建容器性能指标记录"""
    db_metrics = ContainerMetrics(**metrics.model_dump())
    db.add(db_metrics)
    await db.commit()
    await db.refresh(db_metrics)
    return db_metrics


async def get_latest_metrics(db: AsyncSession, container_id: int) -> Optional[ContainerMetrics]:
    """获取容器最新的性能指标"""
    result = await db.execute(
        select(ContainerMetrics)
        .where(ContainerMetrics.container_id == container_id)
        .order_by(ContainerMetrics.timestamp.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def cleanup_old_metrics(db: AsyncSession, days: int = 7) -> int:
    """清理指定天数之前的历史数据"""
    cutoff = datetime.utcnow() - timedelta(days=days)
    result = await db.execute(
        delete(ContainerMetrics).where(ContainerMetrics.timestamp < cutoff)
    )
    await db.commit()
    return result.rowcount
