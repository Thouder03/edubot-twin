"""
考试运行记录 CRUD（第12期）

包含：
- exam_attempts 的增删改查
- exam_evidence_events 的写入与查询
- 并发控制（单学生同时只能有一个 pending/running/scoring attempt）
"""

import logging
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import path_policy

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
    """统计该学生对该考试的有效尝试次数（不含 error）"""
    result = await db.execute(
        select(func.count()).select_from(ExamAttempt).where(
            and_(
                ExamAttempt.student_id == student_id,
                ExamAttempt.exam_id == exam_id,
                ExamAttempt.status != ExamAttemptStatus.ERROR,
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
    final_score: Optional[float] = None,
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
    if final_score is not None:
        attempt.final_score = max(0.0, min(100.0, final_score))

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
    best_only: bool = False,
) -> tuple[list[ExamAttempt], int]:
    """教师端分页查询运行记录；best_only=True 时每 (student, exam) 只取客观分最高的一条"""
    conditions: list = []
    if exam_id is not None:
        conditions.append(ExamAttempt.exam_id == exam_id)
    if student_id is not None:
        conditions.append(ExamAttempt.student_id == student_id)
    if status is not None:
        conditions.append(ExamAttempt.status == status)

    if best_only:
        score_expr = func.coalesce(ExamAttempt.objective_score, -1.0)
        inner = (
            select(
                ExamAttempt.id,
                func.row_number()
                .over(
                    partition_by=[ExamAttempt.student_id, ExamAttempt.exam_id],
                    order_by=[score_expr.desc(), ExamAttempt.created_at.desc()],
                )
                .label("rn"),
            )
        )
        if conditions:
            inner = inner.where(and_(*conditions))
        inner = inner.subquery()
        best_ids_q = select(inner.c.id).where(inner.c.rn == 1)

        query = select(ExamAttempt).where(ExamAttempt.id.in_(best_ids_q)).order_by(ExamAttempt.created_at.desc())
        count_query = select(func.count()).select_from(ExamAttempt).where(ExamAttempt.id.in_(best_ids_q))
    else:
        query = select(ExamAttempt).order_by(ExamAttempt.created_at.desc())
        count_query = select(func.count()).select_from(ExamAttempt)
        if conditions:
            query = query.where(and_(*conditions))
            count_query = count_query.where(and_(*conditions))

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    return list(result.scalars().all()), total


_SCORED_STATUSES = frozenset([ExamAttemptStatus.COMPLETED, ExamAttemptStatus.REVIEWED])
_NON_ERROR_STATUSES = frozenset([
    ExamAttemptStatus.COMPLETED,
    ExamAttemptStatus.REVIEWED,
    ExamAttemptStatus.ABORTED,
])


async def count_attempts_for_quota(
    db: AsyncSession,
    student_id: int,
    exam_id: int,
    runtime_policy: dict,
) -> int:
    """统计消耗配额的尝试数目（不包括 error）。"""
    statuses = [
        ExamAttemptStatus.COMPLETED,
        ExamAttemptStatus.REVIEWED,
    ]
    result = await db.execute(
        select(func.count()).select_from(ExamAttempt).where(
            and_(
                ExamAttempt.student_id == student_id,
                ExamAttempt.exam_id == exam_id,
                ExamAttempt.status.in_(statuses),
            )
        )
    )
    return result.scalar_one()


def _default_submission_root(attempt_id: int) -> Path:
    return path_policy.EXAM_SUBMISSIONS_ROOT / str(attempt_id)


def _default_artifacts_root(attempt_id: int) -> Path:
    return path_policy.EXAM_ARTIFACTS_ROOT / str(attempt_id)


def _safe_remove_tree(path: Path) -> None:
    if not path.exists():
        return
    if path.is_file():
        path.unlink(missing_ok=True)
        return
    shutil.rmtree(str(path), ignore_errors=True)


def _cleanup_attempt_storage(attempt: ExamAttempt) -> None:
    submission_root = (
        Path(attempt.submission_snapshot_path).resolve().parent
        if attempt.submission_snapshot_path
        else _default_submission_root(attempt.id)
    )
    artifacts_root = (
        Path(attempt.artifacts_path).resolve()
        if attempt.artifacts_path
        else _default_artifacts_root(attempt.id)
    )
    _safe_remove_tree(submission_root)
    _safe_remove_tree(artifacts_root)


async def delete_attempt_with_storage(
    db: AsyncSession,
    attempt: ExamAttempt,
) -> None:
    """删除 attempt 及其 submissions/artifacts 目录。"""
    _cleanup_attempt_storage(attempt)
    await db.delete(attempt)
    await db.commit()


async def batch_delete_attempts_with_storage(
    db: AsyncSession,
    attempts: list[ExamAttempt],
) -> list[int]:
    """批量删除 attempt 及其 submissions/artifacts。"""
    deleted_ids: list[int] = []
    for attempt in attempts:
        _cleanup_attempt_storage(attempt)
        deleted_ids.append(attempt.id)
        await db.delete(attempt)
    await db.commit()
    return deleted_ids


async def list_non_error_attempts_for_exam_student(
    db: AsyncSession,
    exam_id: int,
    student_id: int,
) -> list[ExamAttempt]:
    """查询某学生在某考试下全部非 error 尝试（按创建时间升序）。"""
    result = await db.execute(
        select(ExamAttempt)
        .where(
            and_(
                ExamAttempt.exam_id == exam_id,
                ExamAttempt.student_id == student_id,
                ExamAttempt.status.in_(list(_NON_ERROR_STATUSES)),
            )
        )
        .order_by(ExamAttempt.created_at.asc())
    )
    return list(result.scalars().all())


async def prune_lower_non_error_attempts(
    db: AsyncSession,
    *,
    exam_id: int,
    student_id: int,
) -> list[int]:
    """仅保留一个客观分最高的非 error 尝试，其余全部删除。"""
    attempts = await list_non_error_attempts_for_exam_student(db, exam_id, student_id)
    if len(attempts) <= 1:
        return []

    # objective_score 为空按 -1 处理；同分保留最新记录
    keeper = max(attempts, key=lambda a: ((a.objective_score if a.objective_score is not None else -1.0), a.created_at))
    to_delete = [a for a in attempts if a.id != keeper.id]
    if not to_delete:
        return []
    return await batch_delete_attempts_with_storage(db, to_delete)


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


async def apply_manual_score(
    db: AsyncSession,
    attempt: ExamAttempt,
    *,
    manual_score: float,
    breakdown_json: Optional[dict] = None,
    teacher_comment: Optional[str] = None,
    final_score: float,
    pass_: bool,
) -> ExamAttempt:
    """写入人工评分并核算最终成绩（completed → reviewed）"""
    attempt.manual_score = manual_score
    if breakdown_json is not None:
        attempt.breakdown_json = breakdown_json
    if teacher_comment is not None:
        attempt.teacher_comment = teacher_comment
    attempt.final_score = final_score
    attempt.pass_ = pass_
    attempt.status = ExamAttemptStatus.REVIEWED
    attempt.review_status = ExamAttemptReviewStatus.REVIEWED
    attempt.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(attempt)
    return attempt


async def apply_override(
    db: AsyncSession,
    attempt: ExamAttempt,
    *,
    objective_score: Optional[float] = None,
    pass_flag: Optional[bool] = None,
    final_score: Optional[float] = None,
) -> ExamAttempt:
    """教师覆盖客观分 / pass 并重算最终成绩"""
    if objective_score is not None:
        attempt.objective_score = max(0.0, min(100.0, objective_score))
    if pass_flag is not None:
        attempt.pass_ = pass_flag
    if final_score is not None:
        attempt.final_score = final_score
    attempt.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(attempt)
    return attempt


_ABNORMAL_STATUSES = [ExamAttemptStatus.ERROR, ExamAttemptStatus.ABORTED]
_BEST_STATUSES = [ExamAttemptStatus.COMPLETED, ExamAttemptStatus.REVIEWED]


async def list_best_attempts_per_student(
    db: AsyncSession,
    *,
    exam_id: Optional[int] = None,
    review_status: Optional[str] = None,
    sort: str = "review_pending_first",
    page: int = 1,
    page_size: int = 20,
    best_only: bool = True,
) -> tuple[list[tuple], int]:
    """
    复核列表视图（仅 completed/reviewed），返回 (ExamAttempt, exam_name) 行列表。
    best_only=True（默认）：每学生每考试只取客观分最高的一条；
    best_only=False：返回所有 completed/reviewed 尝试。
    """
    from app.models.exam import Exam  # 避免循环导入

    score_expr = func.coalesce(ExamAttempt.objective_score, -1.0)

    base_conds: list = [ExamAttempt.status.in_(_BEST_STATUSES)]
    if exam_id is not None:
        base_conds.append(ExamAttempt.exam_id == exam_id)

    if best_only:
        # 内层子查询：对每 (student_id, exam_id) 按分数降序+时间降序排序，取 row_number=1
        inner = (
            select(
                ExamAttempt.id,
                func.row_number()
                .over(
                    partition_by=[ExamAttempt.student_id, ExamAttempt.exam_id],
                    order_by=[score_expr.desc(), ExamAttempt.created_at.desc()],
                )
                .label("rn"),
            )
            .where(and_(*base_conds))
        ).subquery()

        best_ids_q = select(inner.c.id).where(inner.c.rn == 1)

        q = (
            select(ExamAttempt, Exam.name.label("exam_name"))
            .join(Exam, ExamAttempt.exam_id == Exam.id)
            .where(ExamAttempt.id.in_(best_ids_q))
        )
        count_q = (
            select(func.count())
            .select_from(ExamAttempt)
            .where(ExamAttempt.id.in_(best_ids_q))
        )
    else:
        # 所有 completed/reviewed 尝试
        q = (
            select(ExamAttempt, Exam.name.label("exam_name"))
            .join(Exam, ExamAttempt.exam_id == Exam.id)
            .where(and_(*base_conds))
        )
        count_q = (
            select(func.count())
            .select_from(ExamAttempt)
            .where(and_(*base_conds))
        )

    # 按 review_status 筛选
    if review_status == "pending":
        q = q.where(ExamAttempt.review_status == ExamAttemptReviewStatus.PENDING)
        count_q = count_q.where(ExamAttempt.review_status == ExamAttemptReviewStatus.PENDING)
    elif review_status == "reviewed":
        q = q.where(ExamAttempt.review_status == ExamAttemptReviewStatus.REVIEWED)
        count_q = count_q.where(ExamAttempt.review_status == ExamAttemptReviewStatus.REVIEWED)

    # 排序
    pending_first = case(
        (ExamAttempt.review_status == ExamAttemptReviewStatus.PENDING, 0),
        else_=1,
    )
    sort_map = {
        "review_pending_first": [pending_first, score_expr.desc()],
        "score_desc": [score_expr.desc()],
        "score_asc": [func.coalesce(ExamAttempt.objective_score, -1.0).asc()],
        "created_at_desc": [ExamAttempt.created_at.desc()],
    }
    q = q.order_by(*sort_map.get(sort, sort_map["review_pending_first"]))

    total_result = await db.execute(count_q)
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    result = await db.execute(q.offset(offset).limit(page_size))
    return list(result.all()), total


async def delete_abnormal_attempts(
    db: AsyncSession,
    *,
    exam_id: Optional[int] = None,
) -> list[int]:
    """删除 status∈{error,aborted} 的 attempt 及文件，返回已删除 id 列表"""
    conds: list = [ExamAttempt.status.in_(_ABNORMAL_STATUSES)]
    if exam_id is not None:
        conds.append(ExamAttempt.exam_id == exam_id)

    result = await db.execute(select(ExamAttempt).where(and_(*conds)))
    attempts = list(result.scalars().all())
    if not attempts:
        return []
    return await batch_delete_attempts_with_storage(db, attempts)


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


# ─── 第16期：成绩预览 CRUD ────────────────────────────────────────────────────


async def list_grade_preview_attempts(
    db: AsyncSession,
    *,
    exam_id: Optional[int] = None,
    student_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 20,
    best_only: bool = False,
) -> tuple[list[tuple], int]:
    """
    教师端成绩预览：查询 completed/reviewed 状态的尝试，支持考试/学生筛选，
    返回 (ExamAttempt, exam_name, student_username, student_real_name) 行列表。
    best_only=True：每学生每考试只取客观分最高的一条。
    """
    from app.models.exam import Exam  # 避免循环导入
    from app.models.student import User

    conds: list = [ExamAttempt.status.in_(_BEST_STATUSES)]
    if exam_id is not None:
        conds.append(ExamAttempt.exam_id == exam_id)
    if student_id is not None:
        conds.append(ExamAttempt.student_id == student_id)

    def _base_q(id_filter=None):
        q = (
            select(
                ExamAttempt,
                Exam.name.label("exam_name"),
                User.username.label("student_username"),
                User.real_name.label("student_real_name"),
            )
            .join(Exam, ExamAttempt.exam_id == Exam.id)
            .join(User, ExamAttempt.student_id == User.id)
            .order_by(ExamAttempt.created_at.desc())
        )
        return q.where(ExamAttempt.id.in_(id_filter)) if id_filter is not None else q.where(and_(*conds))

    def _base_count_q(id_filter=None):
        q = (
            select(func.count())
            .select_from(ExamAttempt)
            .join(Exam, ExamAttempt.exam_id == Exam.id)
            .join(User, ExamAttempt.student_id == User.id)
        )
        return q.where(ExamAttempt.id.in_(id_filter)) if id_filter is not None else q.where(and_(*conds))

    if best_only:
        score_expr = func.coalesce(ExamAttempt.objective_score, -1.0)
        inner = (
            select(
                ExamAttempt.id,
                func.row_number()
                .over(
                    partition_by=[ExamAttempt.student_id, ExamAttempt.exam_id],
                    order_by=[score_expr.desc(), ExamAttempt.created_at.desc()],
                )
                .label("rn"),
            )
            .where(and_(*conds))
        ).subquery()
        best_ids_q = select(inner.c.id).where(inner.c.rn == 1)
        q = _base_q(best_ids_q)
        count_q = _base_count_q(best_ids_q)
    else:
        q = _base_q()
        count_q = _base_count_q()

    total_result = await db.execute(count_q)
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    result = await db.execute(q.offset(offset).limit(page_size))
    return list(result.all()), total


async def list_my_grade_summary(
    db: AsyncSession,
    *,
    student_id: int,
) -> list[tuple]:
    """
    学生端：查询当前学生所有已完成考试的最高分摘要。
    每 (exam_id) 取 objective_score 最高的那条（NULL 视为 -1）。
    返回 (ExamAttempt, exam_name, exam_code) 行列表，按 ended_at DESC 排序。
    """
    from app.models.exam import Exam  # 避免循环导入

    score_expr = func.coalesce(ExamAttempt.objective_score, -1.0)

    # 子查询：对每 exam_id 按分数降序+时间降序取 row_number=1
    inner = (
        select(
            ExamAttempt.id,
            func.row_number()
            .over(
                partition_by=[ExamAttempt.exam_id],
                order_by=[score_expr.desc(), ExamAttempt.created_at.desc()],
            )
            .label("rn"),
        )
        .where(
            and_(
                ExamAttempt.student_id == student_id,
                ExamAttempt.status.in_(_BEST_STATUSES),
            )
        )
    ).subquery()

    best_ids_q = select(inner.c.id).where(inner.c.rn == 1)

    q = (
        select(
            ExamAttempt,
            Exam.name.label("exam_name"),
            Exam.code.label("exam_code"),
        )
        .join(Exam, ExamAttempt.exam_id == Exam.id)
        .where(ExamAttempt.id.in_(best_ids_q))
        .order_by(ExamAttempt.ended_at.desc().nullslast())
    )

    result = await db.execute(q)
    return list(result.all())


async def list_grade_detail_for_student(
    db: AsyncSession,
    *,
    student_id: int,
    exam_id: int,
) -> list[ExamAttempt]:
    """
    学生端：查询该学生在指定考试下的所有尝试（不过滤状态），
    按 created_at DESC 排序。
    """
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
