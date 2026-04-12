"""
教师端考试定义 API（第11期）

端点前缀：/api/v1/teachers/exams
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_teacher
from app.crud import exam as crud_exam
from app.db.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.exam import (
    ExamCreateRequest,
    ExamListItem,
    ExamListResponse,
    ExamResponse,
    ExamUpdateRequest,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _to_exam_response(exam) -> ExamResponse:
    return ExamResponse(
        id=exam.id,
        name=exam.name,
        code=exam.code,
        description=exam.description,
        exam_mode=exam.exam_mode.value,
        status=exam.status.value,
        env_snapshot_id=exam.env_snapshot_id,
        file_snapshot_id=exam.file_snapshot_id,
        eval_script_id=exam.eval_script_id,
        runtime_policy_json=exam.runtime_policy_json,
        panel_policy_json=exam.panel_policy_json,
        scoring_policy_json=exam.scoring_policy_json,
        sidecar_policy_json=exam.sidecar_policy_json,
        teacher_comment_template=exam.teacher_comment_template,
        created_by=exam.created_by,
        created_at=exam.created_at,
        updated_at=exam.updated_at,
        published_at=exam.published_at,
    )


def _to_exam_list_item(exam) -> ExamListItem:
    return ExamListItem(
        id=exam.id,
        name=exam.name,
        code=exam.code,
        exam_mode=exam.exam_mode.value,
        status=exam.status.value,
        env_snapshot_id=exam.env_snapshot_id,
        file_snapshot_id=exam.file_snapshot_id,
        eval_script_id=exam.eval_script_id,
        created_at=exam.created_at,
        published_at=exam.published_at,
    )


async def _get_exam_or_404(db, exam_id: int, teacher_id: int):
    """获取考试并校验归属权"""
    exam = await crud_exam.get_exam(db, exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="考试不存在")
    if exam.created_by != teacher_id:
        raise HTTPException(status_code=403, detail="无权访问该考试")
    return exam


# ─── 考试 CRUD ────────────────────────────────────────────────────────────────

@router.get("", response_model=ApiResponse[ExamListResponse], summary="考试列表")
async def list_exams(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = Query(default=None),
    exam_status: Optional[str] = Query(default=None, alias="status"),
    exam_mode: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """分页查询考试列表"""
    exams, total = await crud_exam.list_exams(
        db, created_by=teacher_id, page=page, page_size=page_size,
        keyword=keyword, status=exam_status, exam_mode=exam_mode,
    )
    items = [_to_exam_list_item(e) for e in exams]
    return ApiResponse(data=ExamListResponse(total=total, items=items))


@router.post(
    "",
    response_model=ApiResponse[ExamResponse],
    status_code=status.HTTP_201_CREATED,
    summary="创建考试",
)
async def create_exam(
    data: ExamCreateRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """创建考试（草稿状态）"""
    try:
        exam = await crud_exam.create_exam(
            db,
            name=data.name,
            code=data.code,
            exam_mode=data.exam_mode,
            description=data.description,
            created_by=teacher_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return ApiResponse(data=_to_exam_response(exam))


@router.get("/{exam_id}", response_model=ApiResponse[ExamResponse], summary="考试详情")
async def get_exam(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    exam = await _get_exam_or_404(db, exam_id, teacher_id)
    return ApiResponse(data=_to_exam_response(exam))


@router.patch("/{exam_id}", response_model=ApiResponse[ExamResponse], summary="更新考试")
async def update_exam(
    exam_id: int,
    data: ExamUpdateRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """
    按字段级更新考试。

    若考试已发布，冻结字段（exam_mode / env_snapshot_id / file_snapshot_id / eval_script_id / sidecar_policy）
    的更新请求将返回 409。
    """
    exam = await _get_exam_or_404(db, exam_id, teacher_id)
    update_data = data.model_dump(exclude_unset=True)
    try:
        exam = await crud_exam.update_exam(db, exam=exam, update_data=update_data)
    except ValueError as e:
        error_str = str(e)
        raise HTTPException(status_code=409, detail=error_str)
    return ApiResponse(data=_to_exam_response(exam))


@router.delete("/{exam_id}", response_model=ApiResponse, summary="删除考试")
async def delete_exam(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """删除考试（第11期仅允许删除 archived 状态）"""
    exam = await _get_exam_or_404(db, exam_id, teacher_id)
    try:
        await crud_exam.delete_exam(db, exam=exam)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return ApiResponse(data=None, message="已删除")


# ─── 发布 / 归档 / 重新发布 ──────────────────────────────────────────────────

@router.post("/{exam_id}/publish", response_model=ApiResponse[ExamResponse], summary="发布考试")
async def publish_exam(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """发布考试（draft → published）"""
    exam = await _get_exam_or_404(db, exam_id, teacher_id)
    try:
        exam = await crud_exam.publish_exam(db, exam=exam)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return ApiResponse(data=_to_exam_response(exam))


@router.post("/{exam_id}/archive", response_model=ApiResponse[ExamResponse], summary="归档考试")
async def archive_exam(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """归档考试（published → archived）"""
    exam = await _get_exam_or_404(db, exam_id, teacher_id)
    try:
        exam = await crud_exam.archive_exam(db, exam=exam)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return ApiResponse(data=_to_exam_response(exam))


@router.post("/{exam_id}/republish", response_model=ApiResponse[ExamResponse], summary="重新发布考试")
async def republish_exam(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """重新发布考试（archived → published）"""
    exam = await _get_exam_or_404(db, exam_id, teacher_id)
    try:
        exam = await crud_exam.republish_exam(db, exam=exam)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return ApiResponse(data=_to_exam_response(exam))
