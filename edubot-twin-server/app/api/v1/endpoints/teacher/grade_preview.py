"""
教师端成绩预览 API（第16期）

路由（在 teacher/__init__.py 中以无 prefix 方式挂载）：
  GET /teachers/grade-preview  → 分页列表，支持 exam_id / student_id 筛选
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.final_score_calculator import get_scoring_mode
from app.core.security import get_current_teacher
from app.crud import exam_attempt as crud_attempt
from app.db.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.exam_attempt import AttemptStudentInfo
from app.schemas.grade_preview import GradePreviewItem, GradePreviewListResponse

router = APIRouter()
logger = logging.getLogger(__name__)


def _is_objective_only_attempt(attempt) -> bool:
    scoring_policy = attempt.attempt_scoring_policy_json or {}
    return get_scoring_mode(scoring_policy) == "objective_only"


def _build_grade_preview_item(row) -> GradePreviewItem:
    """将 CRUD 查询行（attempt, exam_name, student_username, student_real_name）转换为 Schema"""
    attempt, exam_name, student_username, student_real_name = row

    # result_json 去掉 artifacts / metrics 键后作为展示数据；metrics 单独提取
    result_json_display: Optional[dict] = None
    metrics: Optional[dict] = None
    if attempt.result_json:
        result_json_display = {
            k: v for k, v in attempt.result_json.items()
            if k not in ("artifacts", "metrics")
        }
        raw_metrics = attempt.result_json.get("metrics")
        if isinstance(raw_metrics, dict):
            metrics = raw_metrics

    final_score = attempt.objective_score if _is_objective_only_attempt(attempt) else attempt.final_score
    review_status = None if _is_objective_only_attempt(attempt) else attempt.review_status.value

    return GradePreviewItem(
        attempt_id=attempt.id,
        exam_id=attempt.exam_id,
        exam_name=exam_name,
        student=AttemptStudentInfo(
            student_id=attempt.student_id,
            username=student_username,
            real_name=student_real_name,
        ),
        status=attempt.status.value,
        objective_score=attempt.objective_score,
        manual_score=attempt.manual_score,
        final_score=final_score,
        **{"pass": attempt.pass_},
        summary=attempt.summary,
        teacher_comment=attempt.teacher_comment,
        review_status=review_status,
        result_json_display=result_json_display,
        metrics=metrics,
        custom_fields=attempt.custom_fields_json,
        started_at=attempt.started_at,
        ended_at=attempt.ended_at,
        duration_ms=attempt.duration_ms,
        created_at=attempt.created_at,
    )


@router.get(
    "/grade-preview",
    response_model=ApiResponse[GradePreviewListResponse],
    summary="教师成绩预览列表（含 result_json）",
)
async def get_grade_preview(
    exam_id: Optional[int] = Query(default=None, description="按考试筛选"),
    student_id: Optional[int] = Query(default=None, description="按学生 ID 筛选"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    best_only: bool = Query(default=False, description="只显示每学生每考试客观分最高的一条"),
    _teacher_id: int = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db),
):
    rows, total = await crud_attempt.list_grade_preview_attempts(
        db,
        exam_id=exam_id,
        student_id=student_id,
        page=page,
        page_size=page_size,
        best_only=best_only,
    )
    items = [_build_grade_preview_item(r) for r in rows]
    return ApiResponse(
        code=0,
        data=GradePreviewListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        ),
    )
