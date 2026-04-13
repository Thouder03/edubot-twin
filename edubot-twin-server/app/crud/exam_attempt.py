"""
考试运行记录 CRUD（第12期）

包含：
- exam_attempts 的增删改查
- exam_evidence_events 的写入与查询
- 并发控制（单学生同时只能有一个 pending/running/scoring attempt）
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exam_attempt import (
    ExamAttempt,
    ExamAttemptStatus,
    ExamAttemptReviewStatus,
    ExamEvidenceEvent,
    EvidenceEventType,
)

logger = logging.getLogger(__name__)

# pending 状态超时回收阈值（分钟）
PENDING_STALE_MINUTES = 10

# 进行中状态集合（并发控制）
IN_PROGRESS_STATUSES = {
    ExamAttemptStatus.PENDING,
    ExamAttemptStatus.RUNNING,
    ExamAttemptStatus.SCORING,
}


# ─── ExamAttempt CRUD ─────────────────────────────────────────────────────────


async def create_attempt(
    db: AsyncSession,
    *,
    exam_id: int,
    student_id: int,
    container_id: Optional[int],
    sim_container_docker_id: Optional[str],
    attempt_exam_mode: str,
    attempt_runtime_policy_json: dict,
    attempt_panel_policy_json: dict,
    attempt_scoring_policy_json: dict,
    attempt_sidecar_policy_json: dict,
) -> ExamAttempt:
    """创建考试尝试记录（status=pending）"""
    attempt = ExamAttempt(
        exam_id=exam_id,
        student_id=student_id,
        container_id=container_id,
        sim_container_docker_id=sim_container_docker_id,
        status=ExamAttemptStatus.PENDING,
        attempt_exam_mode=attempt_exam_mode,
        attempt_runtime_policy_json=attempt_runtime_policy_json,
        attempt_panel_policy_json=attempt_panel_policy_json,
        attempt_scoring_policy_json=attempt_scoring_policy_json,
        attempt_sidecar_policy_json=attempt_sidecar_policy_json,
    )
    db.add(attempt)
    await db.commit()
    await db.refresh(attempt)
    return attempt


async def get_attempt(db: AsyncSession, attempt_id: int) -> Optional[ExamAttempt]:
    """通过 ID 获取考试尝试"""
    result = await db.execute(
        select(ExamAttempt).where(ExamAttempt.id == attempt_id)
    )
    return result.scalar_one_or_none()


async def get_in_progress_attempt(
    db: AsyncSession, student_id: int, exam_id: int
) -> Optional[ExamAttempt]:
    """查询该学生对该考试是否有进行中的 attempt（pending/running/scoring）"""
    result = await db.execute(
        select(ExamAttempt).where(
            and_(
                ExamAttempt.student_id == student_id,
                ExamAttempt.exam_id == exam_id,
                ExamAttempt.status.in_(list(IN_PROGRESS_STATUSES)),
            )
        )
    )
    return result.scalar_one_or_none()


async def count_completed_attempts(
    db: AsyncSession, student_id: int, exam_id: int
) -> int:
    """统计该学生对该考试的已完成尝试次数（completed + aborted + error 均计入）"""
    result = await db.execute(
        select(func.count()).select_from(ExamAttempt).where(
            and_(
                ExamAttempt.student_id == student_id,
                ExamAttempt.exam_id == exam_id,
                ExamAttempt.status.in_([
                    ExamAttemptStatus.COMPLETED,
                    ExamAttemptStatus.ABORTED,
                    ExamAttemptStatus.ERROR,
                ]),
            )
        )
    )
    return result.scalar_one()


async def count_all_attempts(
    db: AsyncSession, student_id: int, exam_id: int
) -> int:
    """统计该学生对该考试的全部尝试次数（含 pending/running/scoring）"""
    result = await db.execute(
        select(func.count()).select_from(ExamAttempt).where(
            and_(
                ExamAttempt.student_id == student_id,
                ExamAttempt.exam_id == exam_id,
            )
        )
    )
    return result.scalar_one()


async def update_attempt_status(
    db: AsyncSession,
    attempt: ExamAttempt,
    status: ExamAttemptStatus,
    *,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
    started_at: Optional[datetime] = None,
    ended_at: Optional[datetime] = None,
    duration_ms: Optional[int] = None,
    sidecar_container_id: Optional[str] = None,
    submission_snapshot_path: Optional[str] = None,
    artifacts_path: Optional[str] = None,
) -> ExamAttempt:
    """更新 attempt 状态（带可选字段）"""
    attempt.status = status
    attempt.updated_at = datetime.utcnow()

    if error_code is not None:
        attempt.error_code = error_code
    if error_message is not None:
        attempt.error_message = error_message
    if started_at is not None:
        attempt.started_at = started_at
    if ended_at is not None:
        attempt.ended_at = ended_at
    if duration_ms is not None:
        attempt.duration_ms = duration_ms
    if sidecar_container_id is not None:
        attempt.sidecar_container_id = sidecar_container_id
    if submission_snapshot_path is not None:
        attempt.submission_snapshot_path = submission_snapshot_path
    if artifacts_path is not None:
        attempt.artifacts_path = artifacts_path

    await db.commit()
    await db.refresh(attempt)
    return attempt


async def finalize_attempt(
    db: AsyncSession,
    attempt: ExamAttempt,
    *,
    status: ExamAttemptStatus,
    objective_score: Optional[float] = None,
    pass_: Optional[bool] = None,
    summary: Optional[str] = None,
    result_json: Optional[dict] = None,
    custom_fields_json: Optional[dict] = None,
    artifact_index_json: Optional[dict] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
) -> ExamAttempt:
    """固化考试结果（scoring → completed/error）"""
    attempt.status = status
    attempt.ended_at = datetime.utcnow()

    if attempt.started_at:
        delta = attempt.ended_at - attempt.started_at
        attempt.duration_ms = int(delta.total_seconds() * 1000)

    if objective_score is not None:
        # Clamp 到 [0, 100]
        attempt.objective_score = max(0.0, min(100.0, objective_score))
    if pass_ is not None:
        attempt.pass_ = pass_
    if summary is not None:
        attempt.summary = summary[:512] if summary else None
    if result_json is not None:
        attempt.result_json = result_json
    if custom_fields_json is not None:
        attempt.custom_fields_json = custom_fields_json
    if artifact_index_json is not None:
        attempt.artifact_index_json = artifact_index_json
    if error_code is not None:
        attempt.error_code = error_code
    if error_message is not None:
        attempt.error_message = error_message

    attempt.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(attempt)
    return attempt


async def list_student_attempts(
    db: AsyncSession,
    student_id: int,
    exam_id: int,
) -> list[ExamAttempt]:
    """获取学生对某考试的全部 attempt（按创建时间倒序）"""
    result = await db.execute(
        select(ExamAttempt)
        .where(
            and_(
                ExamAttempt.student_id == student_id,
                ExamAttempt.exam_id == exam_id,
            )
        )
        .order_by(ExamAttempt.created_at.desc())
    )
    return list(result.scalars().all())


async def list_attempts_for_teacher(
    db: AsyncSession,
    *,
    exam_id: Optional[int] = None,
    student_id: Optional[int] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[ExamAttempt], int]:
    """教师端分页查询运行记录"""
    query = select(ExamAttempt).order_by(ExamAttempt.created_at.desc())
    count_query = select(func.count()).select_from(ExamAttempt)

    conditions = []
    if exam_id is not None:
        conditions.append(ExamAttempt.exam_id == exam_id)
    if student_id is not None:
        conditions.append(ExamAttempt.student_id == student_id)
    if status is not None:
        conditions.append(ExamAttempt.status == status)

    if conditions:
        query = query.where(and_(*conditions))
        count_query = count_query.where(and_(*conditions))

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    return list(result.scalars().all()), total


async def find_stale_pending_attempts(
    db: AsyncSession,
    stale_minutes: int = PENDING_STALE_MINUTES,
) -> list[ExamAttempt]:
    """查询超时未调用 /start 的 pending attempt（需回收）"""
    cutoff = datetime.utcnow() - timedelta(minutes=stale_minutes)
    result = await db.execute(
        select(ExamAttempt).where(
            and_(
                ExamAttempt.status == ExamAttemptStatus.PENDING,
                ExamAttempt.created_at < cutoff,
            )
        )
    )
    return list(result.scalars().all())


async def find_timeout_running_attempts(db: AsyncSession) -> list[ExamAttempt]:
    """查询超过运行时限 + 30s 缓冲的 running attempt（需强制终止）"""
    now = datetime.utcnow()
    result = await db.execute(
        select(ExamAttempt).where(
            and_(
                ExamAttempt.status == ExamAttemptStatus.RUNNING,
                ExamAttempt.started_at.is_not(None),
            )
        )
    )
    candidates = list(result.scalars().all())

    # 按各自的 runtime_policy 判断是否超时
    timeout_list = []
    for attempt in candidates:
        policy = attempt.attempt_runtime_policy_json or {}
        max_ms = policy.get("max_duration_ms", 600000)  # 默认 10 分钟
        buffer_ms = 30000  # 30 秒缓冲
        deadline = attempt.started_at + timedelta(milliseconds=max_ms + buffer_ms)
        if now > deadline:
            timeout_list.append(attempt)

    return timeout_list


# ─── ExamEvidenceEvent CRUD ───────────────────────────────────────────────────


async def record_event(
    db: AsyncSession,
    *,
    attempt_id: int,
    event_type: EvidenceEventType,
    payload: Optional[dict] = None,
    source: str = "backend",
) -> ExamEvidenceEvent:
    """写入一条生命周期事件（自动计算 sequence_no）"""
    # 查询当前 attempt 的最大 sequence_no
    result = await db.execute(
        select(func.max(ExamEvidenceEvent.sequence_no)).where(
            ExamEvidenceEvent.attempt_id == attempt_id
        )
    )
    max_seq = result.scalar_one_or_none()
    next_seq = (max_seq or 0) + 1

    event = ExamEvidenceEvent(
        attempt_id=attempt_id,
        event_type=event_type,
        event_time_ms=int(time.time() * 1000),
        sequence_no=next_seq,
        source=source,
        payload_json=payload or {},
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def list_events(
    db: AsyncSession, attempt_id: int
) -> list[ExamEvidenceEvent]:
    """查询 attempt 的全部生命周期事件（按 sequence_no 升序）"""
    result = await db.execute(
        select(ExamEvidenceEvent)
        .where(ExamEvidenceEvent.attempt_id == attempt_id)
        .order_by(ExamEvidenceEvent.sequence_no)
    )
    return list(result.scalars().all())
