"""
考试定义 CRUD（第11期）

包含：创建 / 获取 / 列表 / 更新 / 删除 / 发布 / 归档 / 重新发布
"""
from datetime import datetime
from typing import Optional
import logging

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exam import Exam, ExamMode, ExamStatus

logger = logging.getLogger(__name__)

# 发布后冻结的字段名列表
FROZEN_FIELDS = {"exam_mode", "env_snapshot_id", "file_snapshot_id", "eval_script_id", "sidecar_policy"}


async def create_exam(
    db: AsyncSession,
    *,
    name: str,
    code: str,
    exam_mode: str,
    description: Optional[str] = None,
    created_by: int,
) -> Exam:
    """创建考试（草稿状态）"""
    exam = Exam(
        name=name,
        code=code,
        description=description,
        exam_mode=ExamMode(exam_mode),
        status=ExamStatus.DRAFT,
        created_by=created_by,
        runtime_policy_json={
            "max_duration_ms": 600000,
            "max_attempts": 3,
            "allow_debug_before_start": True,
            "valid_attempts_only": False,
            "highest_objective_only": False,
            "image": "gzweb_sim:v1",
            "launch_args": {}
        },
        panel_policy_json={
            "lock_panels_during_exam": False,
            "allowed_panels": ["ROS3DViewer", "WorkspacePanel", "ContainerTerminal", "RosoutPanel"]
        },
        scoring_policy_json={
            "pass_threshold": 60,
            "scoring_mode": "objective_only"
        },
        sidecar_policy_json={
            "image": "sidecar-runner:v1",
            "cpu_limit": 1.0,
            "memory_limit_mb": 512,
            "eval_script_id": None,
            "env_snapshot_id": None,
            "file_snapshot_id": None
        }
    )
    db.add(exam)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError("EXAM_CODE_DUPLICATED") from e
    await db.refresh(exam)
    return exam


async def get_exam(db: AsyncSession, exam_id: int) -> Optional[Exam]:
    """通过 ID 获取考试"""
    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    return result.scalar_one_or_none()


async def list_exams(
    db: AsyncSession,
    *,
    created_by: int,
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    status: Optional[str] = None,
    exam_mode: Optional[str] = None,
) -> tuple[list[Exam], int]:
    """分页查询考试列表"""
    query = select(Exam).where(Exam.created_by == created_by)
    count_query = select(func.count()).select_from(Exam).where(Exam.created_by == created_by)

    if keyword:
        like = f"%{keyword}%"
        query = query.where((Exam.name.like(like)) | (Exam.code.like(like)))
        count_query = count_query.where((Exam.name.like(like)) | (Exam.code.like(like)))

    if status:
        query = query.where(Exam.status == status)
        count_query = count_query.where(Exam.status == status)

    if exam_mode:
        query = query.where(Exam.exam_mode == exam_mode)
        count_query = count_query.where(Exam.exam_mode == exam_mode)

    total = (await db.execute(count_query)).scalar_one()
    rows = (
        await db.execute(
            query.order_by(Exam.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return list(rows), int(total)


async def update_exam(
    db: AsyncSession,
    *,
    exam: Exam,
    update_data: dict,
) -> Exam:
    """
    更新考试字段（按字段级更新）。

    若考试已发布，冻结字段的更新请求会抛出 ValueError("EXAM_FIELD_FROZEN")。
    乐观锁校验使用 updated_at 字段。
    """
    # 乐观锁校验
    client_updated_at = update_data.pop("updated_at", None)
    if client_updated_at is not None:
        try:
            client_dt = datetime.fromisoformat(client_updated_at)
        except (ValueError, TypeError):
            client_dt = None
        if client_dt and exam.updated_at:
            diff = abs((exam.updated_at - client_dt).total_seconds())
            if diff > 1.0:
                raise ValueError("EXAM_CONCURRENT_MODIFIED")

    # 冻结字段校验（仅 published 状态）
    if exam.status == ExamStatus.PUBLISHED:
        for field in FROZEN_FIELDS:
            if field in update_data and update_data[field] is not None:
                raise ValueError("EXAM_FIELD_FROZEN")

    # 字段映射
    field_map = {
        "name": "name",
        "description": "description",
        "exam_mode": "exam_mode",
        "env_snapshot_id": "env_snapshot_id",
        "file_snapshot_id": "file_snapshot_id",
        "eval_script_id": "eval_script_id",
        "runtime_policy": "runtime_policy_json",
        "panel_policy": "panel_policy_json",
        "scoring_policy": "scoring_policy_json",
        "sidecar_policy": "sidecar_policy_json",
        "teacher_comment_template": "teacher_comment_template",
    }

    for req_field, model_field in field_map.items():
        if req_field in update_data and update_data[req_field] is not None:
            value = update_data[req_field]
            if req_field == "exam_mode":
                value = ExamMode(value)
            setattr(exam, model_field, value)

    # 强制同步资源引用到 sidecar_policy_json 保证单一事实来源
    if getattr(exam, "sidecar_policy_json", None) is not None:
        policy_data = dict(exam.sidecar_policy_json)
        policy_data["eval_script_id"] = exam.eval_script_id
        policy_data["env_snapshot_id"] = exam.env_snapshot_id
        policy_data["file_snapshot_id"] = exam.file_snapshot_id
        exam.sidecar_policy_json = policy_data

    exam.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(exam)
    return exam


async def delete_exam(db: AsyncSession, *, exam: Exam) -> None:
    """删除考试（第11期仅允许删除 archived 状态）"""
    if exam.status != ExamStatus.ARCHIVED:
        raise ValueError("EXAM_DELETE_REQUIRES_ARCHIVED")

    await db.delete(exam)
    await db.commit()


async def publish_exam(db: AsyncSession, *, exam: Exam) -> Exam:
    """
    发布考试（draft → published）。

    校验必填项：env_snapshot_id / file_snapshot_id / eval_script_id / exam_mode。
    """
    if exam.status != ExamStatus.DRAFT:
        raise ValueError("EXAM_NOT_DRAFT")

    # 必填校验
    missing = []
    if not exam.env_snapshot_id:
        missing.append("env_snapshot_id")
    if not exam.file_snapshot_id:
        missing.append("file_snapshot_id")
    if not exam.eval_script_id:
        missing.append("eval_script_id")
    if not exam.exam_mode:
        missing.append("exam_mode")

    if missing:
        raise ValueError(f"EXAM_PUBLISH_INCOMPLETE:{','.join(missing)}")

    exam.status = ExamStatus.PUBLISHED
    exam.published_at = exam.published_at or datetime.utcnow()
    exam.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(exam)
    return exam


async def archive_exam(db: AsyncSession, *, exam: Exam) -> Exam:
    """归档考试（published → archived）"""
    if exam.status != ExamStatus.PUBLISHED:
        raise ValueError("EXAM_NOT_PUBLISHED")

    exam.status = ExamStatus.ARCHIVED
    exam.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(exam)
    return exam


async def republish_exam(db: AsyncSession, *, exam: Exam) -> Exam:
    """重新发布考试（archived → published）"""
    if exam.status != ExamStatus.ARCHIVED:
        raise ValueError("EXAM_NOT_ARCHIVED")

    exam.status = ExamStatus.PUBLISHED
    exam.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(exam)
    return exam
