from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.simulation_task import SimulationTask, SimulationTaskStage, SimulationTaskStatus


async def create_task(
    db: AsyncSession,
    *,
    student_id: int,
    target_version_id: int,
    container_id: Optional[int],
) -> SimulationTask:
    task = SimulationTask(
        task_id=str(uuid4()),
        student_id=student_id,
        container_id=container_id,
        target_version_id=target_version_id,
        status=SimulationTaskStatus.PENDING,
        current_stage=SimulationTaskStage.PREPARING_CONFIG,
        stage_statuses=[],
        elapsed_ms=0,
        retryable=True,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def get_task(db: AsyncSession, task_id: str) -> Optional[SimulationTask]:
    result = await db.execute(select(SimulationTask).where(SimulationTask.task_id == task_id))
    return result.scalar_one_or_none()


async def get_active_task_by_student(db: AsyncSession, student_id: int) -> Optional[SimulationTask]:
    result = await db.execute(
        select(SimulationTask)
        .where(
            SimulationTask.student_id == student_id,
            SimulationTask.status.in_([SimulationTaskStatus.PENDING, SimulationTaskStatus.IN_PROGRESS]),
        )
        .order_by(SimulationTask.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def mark_stage(
    db: AsyncSession,
    *,
    task: SimulationTask,
    stage: SimulationTaskStage,
    status: str,
    elapsed_ms: int,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
) -> None:
    stage_list = list(task.stage_statuses or [])
    stage_list.append(
        {
            "stage": stage.value,
            "status": status,
            "elapsed_ms": elapsed_ms,
        }
    )
    task.stage_statuses = stage_list
    task.current_stage = stage
    if error_code:
        task.error_code = error_code
    if error_message:
        task.error_message = error_message
    task.updated_at = datetime.utcnow()
    await db.commit()


async def mark_task_running(db: AsyncSession, *, task: SimulationTask) -> None:
    task.status = SimulationTaskStatus.IN_PROGRESS
    task.updated_at = datetime.utcnow()
    await db.commit()


async def finish_task(
    db: AsyncSession,
    *,
    task: SimulationTask,
    status: SimulationTaskStatus,
    elapsed_ms: int,
    retryable: bool,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
) -> None:
    task.status = status
    task.elapsed_ms = elapsed_ms
    task.retryable = retryable
    task.error_code = error_code
    task.error_message = error_message
    task.updated_at = datetime.utcnow()
    await db.commit()


async def recover_orphan_tasks(db: AsyncSession, stale_minutes: int = 5) -> int:
    """服务重启时扫描孤儿任务（updated_at 超过 stale_minutes 分钟仍 PENDING/IN_PROGRESS），标记为 FAILED+retryable。
    返回被回收的任务数量。"""
    from datetime import timedelta
    from sqlalchemy import and_

    cutoff = datetime.utcnow() - timedelta(minutes=stale_minutes)
    result = await db.execute(
        select(SimulationTask).where(
            and_(
                SimulationTask.status.in_([SimulationTaskStatus.PENDING, SimulationTaskStatus.IN_PROGRESS]),
                SimulationTask.updated_at < cutoff,
            )
        )
    )
    orphans = result.scalars().all()
    for task in orphans:
        task.status = SimulationTaskStatus.FAILED
        task.retryable = True
        task.error_code = "ORPHAN_TASK_RECOVERED"
        task.error_message = "服务重启时检测到孤儿任务，已自动标记为失败，可重试"
        task.updated_at = datetime.utcnow()
    if orphans:
        await db.commit()
    return len(orphans)
