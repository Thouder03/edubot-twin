"""
教师端考试运行记录 API（第12期 S7 + S10，第15期扩展）

路由前缀：/api/v1/teachers/
  GET /exams/{exam_id}/attempts                → 单考试的运行记录列表
  GET /exam-attempts                           → 全局运行记录列表
  GET /exam-attempts/{id}                      → 运行记录详情
  GET /exam-attempts/{id}/events               → 生命周期事件时间轴
  POST /exam-attempts/batch-delete             → 批量删除
  GET /exam-review-list                        → 每学生每考试最高分视图（第15期）
  POST /exam-attempts/delete-abnormal          → 一键删除异常尝试（第15期）
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.security import get_current_user_id
from app.crud import exam_attempt as crud_attempt
from app.crud import exam as crud_exam
from app.db.database import get_db
from app.models.exam_attempt import ExamAttempt
from app.models.student import User
from app.schemas.common import ApiResponse
from app.schemas.exam_attempt import (
    AttemptExamInfo,
    AttemptListResponse,
    AttemptStudentInfo,
    DeleteAbnormalRequest,
    DeleteAbnormalResponse,
    EvidenceEventSchema,
    ExamReviewListItem,
    ExamReviewListResponse,
    TeacherAttemptFullSchema,
    TeacherAttemptListItemSchema,
    TeacherBatchDeleteAttemptsRequest,
    TeacherBatchDeleteAttemptsResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)


async def _get_student_info(db: AsyncSession, student_id: int) -> AttemptStudentInfo:
    """获取学生信息用于 attempt 详情"""
    result = await db.execute(select(User).where(User.id == student_id))
    user = result.scalar_one_or_none()
    if user:
        return AttemptStudentInfo(
            student_id=user.id,
            username=user.username,
            real_name=getattr(user, "real_name", None),
        )
    return AttemptStudentInfo(student_id=student_id, username=f"student_{student_id}")


async def _get_exam_info(db: AsyncSession, exam_id: int) -> AttemptExamInfo:
    """获取考试信息用于 attempt 详情"""
    exam = await crud_exam.get_exam(db, exam_id)
    if exam:
        return AttemptExamInfo(
            exam_id=exam.id,
            name=exam.name,
            exam_mode=exam.exam_mode.value,
        )
    return AttemptExamInfo(exam_id=exam_id, name=f"exam_{exam_id}", exam_mode="unknown")


def _build_teacher_full(attempt, student: AttemptStudentInfo, exam: AttemptExamInfo) -> TeacherAttemptFullSchema:
    """构建教师端完整详情 Schema"""
    return TeacherAttemptFullSchema(
        attempt_id=attempt.id,
        exam_id=attempt.exam_id,
        status=attempt.status.value,
        attempt_exam_mode=attempt.attempt_exam_mode,
        started_at=attempt.started_at,
        ended_at=attempt.ended_at,
        duration_ms=attempt.duration_ms,
        objective_score=attempt.objective_score,
        **{"pass": attempt.pass_},
        summary=attempt.summary,
        result_json=attempt.result_json,
        error_code=attempt.error_code,
        error_message=attempt.error_message,
        created_at=attempt.created_at,
        updated_at=attempt.updated_at,
        student=student,
        exam=exam,
        review_status=attempt.review_status.value,
        manual_score=attempt.manual_score,
        final_score=attempt.final_score,
        breakdown_json=attempt.breakdown_json,
        teacher_comment=attempt.teacher_comment,
        artifact_index_json=attempt.artifact_index_json or {},
        sidecar_container_id=attempt.sidecar_container_id,
        attempt_scoring_policy_json=attempt.attempt_scoring_policy_json or {},
        submission_snapshot_path=attempt.submission_snapshot_path,
    )


# ─── GET /teachers/exams/{exam_id}/attempts ───────────────────────────────────


def _build_list_item(attempt, student: AttemptStudentInfo) -> TeacherAttemptListItemSchema:
    return TeacherAttemptListItemSchema(
        attempt_id=attempt.id,
        exam_id=attempt.exam_id,
        status=attempt.status.value,
        student=student,
        objective_score=attempt.objective_score,
        **{"pass": attempt.pass_},
        started_at=attempt.started_at,
        ended_at=attempt.ended_at,
        duration_ms=attempt.duration_ms,
        error_code=attempt.error_code,
        review_status=attempt.review_status.value,
        manual_score=attempt.manual_score,
        final_score=attempt.final_score,
        created_at=attempt.created_at,
    )


@router.get(
    "/exams/{exam_id}/attempts",
    response_model=ApiResponse[AttemptListResponse],
    summary="获取单个考试的运行记录列表",
)
async def list_exam_attempts(
    exam_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    student_id: Optional[int] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    _user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    page_attempts, total = await crud_attempt.list_attempts_for_teacher(
        db,
        exam_id=exam_id,
        student_id=student_id,
        status=status_filter,
        page=page,
        page_size=page_size,
    )

    items = []
    for attempt in page_attempts:
        student = await _get_student_info(db, attempt.student_id)
        items.append(_build_list_item(attempt, student))

    return ApiResponse(
        code=0,
        data=AttemptListResponse(
            items=[i.model_dump(by_alias=True) for i in items],
            total=total,
            page=page,
            page_size=page_size,
        ),
    )


# ─── GET /teachers/exam-attempts ─────────────────────────────────────────────


@router.get(
    "/exam-attempts",
    response_model=ApiResponse[AttemptListResponse],
    summary="全局运行记录列表",
)
async def list_all_attempts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    student_id: Optional[int] = Query(default=None),
    exam_id: Optional[int] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    best_only: bool = Query(default=False, description="只显示每学生每考试客观分最高的一条"),
    _user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    attempts, total = await crud_attempt.list_attempts_for_teacher(
        db,
        exam_id=exam_id,
        student_id=student_id,
        status=status_filter,
        page=page,
        page_size=page_size,
        best_only=best_only,
    )

    items = []
    for attempt in attempts:
        student = await _get_student_info(db, attempt.student_id)
        items.append(_build_list_item(attempt, student))

    return ApiResponse(
        code=0,
        data=AttemptListResponse(
            items=[i.model_dump(by_alias=True) for i in items],
            total=total,
            page=page,
            page_size=page_size,
        ),
    )


# ─── GET /teachers/exam-attempts/{id} ────────────────────────────────────────


@router.get(
    "/exam-attempts/{attempt_id}",
    response_model=ApiResponse[TeacherAttemptFullSchema],
    summary="运行记录完整详情（含学生信息、result_json 原文）",
)
async def get_attempt_full(
    attempt_id: int,
    _user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    attempt = await crud_attempt.get_attempt(db, attempt_id)
    if attempt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "ATTEMPT_NOT_FOUND", "message": "运行记录不存在"},
        )

    student = await _get_student_info(db, attempt.student_id)
    exam = await _get_exam_info(db, attempt.exam_id)

    return ApiResponse(
        code=0,
        data=_build_teacher_full(attempt, student, exam),
    )


# ─── GET /teachers/exam-attempts/{id}/events ─────────────────────────────────


@router.get(
    "/exam-attempts/{attempt_id}/events",
    response_model=ApiResponse[dict],
    summary="生命周期事件时间轴",
)
async def get_attempt_events(
    attempt_id: int,
    _user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    attempt = await crud_attempt.get_attempt(db, attempt_id)
    if attempt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "ATTEMPT_NOT_FOUND", "message": "运行记录不存在"},
        )

    events = await crud_attempt.list_events(db, attempt_id)
    items = [EvidenceEventSchema.from_orm(e).model_dump() for e in events]

    return ApiResponse(
        code=0,
        data={"items": items},
    )


@router.post(
    "/exam-attempts/batch-delete",
    response_model=ApiResponse[TeacherBatchDeleteAttemptsResponse],
    summary="批量删除考试尝试（含 artifacts/submissions）",
)
async def batch_delete_attempts(
    body: TeacherBatchDeleteAttemptsRequest,
    _user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    ids = list(dict.fromkeys(body.attempt_ids or []))
    if not ids:
        return ApiResponse(code=0, data=TeacherBatchDeleteAttemptsResponse(deleted_ids=[]))

    result = await db.execute(select(ExamAttempt).where(ExamAttempt.id.in_(ids)))
    attempts = list(result.scalars().all())
    if not attempts:
        return ApiResponse(code=0, data=TeacherBatchDeleteAttemptsResponse(deleted_ids=[]))

    deleted_ids = await crud_attempt.batch_delete_attempts_with_storage(db, attempts)
    return ApiResponse(code=0, data=TeacherBatchDeleteAttemptsResponse(deleted_ids=deleted_ids))


# ─── GET /teachers/exam-review-list（第15期）─────────────────────────────────


@router.get(
    "/exam-review-list",
    response_model=ApiResponse[ExamReviewListResponse],
    summary="考试结果复核列表（每学生每考试最高分视图）",
)
async def list_exam_review(
    exam_id: Optional[int] = Query(default=None),
    review_status: Optional[str] = Query(default=None, description="pending / reviewed"),
    sort: str = Query(default="review_pending_first"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    best_only: bool = Query(default=True, description="只显示每学生每考试客观分最高的一条"),
    _user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    rows, total = await crud_attempt.list_best_attempts_per_student(
        db,
        exam_id=exam_id,
        review_status=review_status,
        sort=sort,
        page=page,
        page_size=page_size,
        best_only=best_only,
    )

    items: list[ExamReviewListItem] = []
    for attempt, exam_name in rows:
        student = await _get_student_info(db, attempt.student_id)
        items.append(
            ExamReviewListItem(
                attempt_id=attempt.id,
                exam_id=attempt.exam_id,
                exam_name=exam_name,
                status=attempt.status.value,
                student=student,
                objective_score=attempt.objective_score,
                **{"pass": attempt.pass_},
                started_at=attempt.started_at,
                ended_at=attempt.ended_at,
                duration_ms=attempt.duration_ms,
                error_code=attempt.error_code,
                review_status=attempt.review_status.value,
                manual_score=attempt.manual_score,
                final_score=attempt.final_score,
                created_at=attempt.created_at,
            )
        )

    return ApiResponse(
        code=0,
        data=ExamReviewListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        ),
    )


# ─── POST /teachers/exam-attempts/delete-abnormal（第15期）────────────────────


@router.post(
    "/exam-attempts/delete-abnormal",
    response_model=ApiResponse[DeleteAbnormalResponse],
    summary="一键删除异常尝试（error/aborted，含文件清理）",
)
async def delete_abnormal_attempts(
    body: DeleteAbnormalRequest,
    _user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    deleted_ids = await crud_attempt.delete_abnormal_attempts(
        db, exam_id=body.exam_id
    )
    logger.info(
        "[delete_abnormal] teacher_id=%s exam_id=%s deleted_count=%d",
        _user_id,
        body.exam_id,
        len(deleted_ids),
    )
    return ApiResponse(
        code=0,
        data=DeleteAbnormalResponse(deleted_ids=deleted_ids, count=len(deleted_ids)),
    )
