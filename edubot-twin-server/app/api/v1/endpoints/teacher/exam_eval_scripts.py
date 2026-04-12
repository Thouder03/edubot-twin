"""
教师端测评脚本包 API（第11期）

端点前缀：/api/v1/teachers/exam-eval-scripts
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.common.bundle_files_router import build_bundle_files_router
from app.core.security import get_current_teacher
from app.crud import exam_eval_script as crud_script
from app.db.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.exam import (
    ExamEvalScriptCreateRequest,
    ExamEvalScriptListItem,
    ExamEvalScriptListResponse,
    ExamEvalScriptResponse,
    ExamEvalScriptUpdateRequest,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _to_response(s) -> ExamEvalScriptResponse:
    return ExamEvalScriptResponse(
        id=s.id, name=s.name, description=s.description,
        storage_root=s.storage_root, entry_point=s.entry_point,
        file_count=s.file_count, total_size_bytes=s.total_size_bytes,
        validate_status=s.validate_status.value,
        created_by=s.created_by, created_at=s.created_at, updated_at=s.updated_at,
    )


def _to_list_item(s) -> ExamEvalScriptListItem:
    return ExamEvalScriptListItem(
        id=s.id, name=s.name, description=s.description,
        entry_point=s.entry_point, file_count=s.file_count,
        total_size_bytes=s.total_size_bytes, validate_status=s.validate_status.value,
        created_at=s.created_at,
    )


async def _get_or_404(db, script_id: int, teacher_id: int):
    s = await crud_script.get_eval_script(db, script_id)
    if not s:
        raise HTTPException(status_code=404, detail="测评脚本不存在")
    if s.created_by != teacher_id:
        raise HTTPException(status_code=403, detail="无权访问")
    return s


# ─── CRUD ────────────────────────────────────────────────────────────────────

@router.get("", response_model=ApiResponse[ExamEvalScriptListResponse], summary="脚本包列表")
async def list_scripts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    items, total = await crud_script.list_eval_scripts(
        db, created_by=teacher_id, page=page, page_size=page_size, keyword=keyword,
    )
    return ApiResponse(data=ExamEvalScriptListResponse(
        total=total, items=[_to_list_item(s) for s in items],
    ))


@router.post(
    "",
    response_model=ApiResponse[ExamEvalScriptResponse],
    status_code=status.HTTP_201_CREATED,
    summary="创建脚本包",
)
async def create_script(
    data: ExamEvalScriptCreateRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    try:
        s = await crud_script.create_eval_script(
            db, name=data.name, description=data.description,
            entry_point=data.entry_point, created_by=teacher_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return ApiResponse(data=_to_response(s))


@router.get("/{script_id}", response_model=ApiResponse[ExamEvalScriptResponse], summary="脚本包详情")
async def get_script(
    script_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    s = await _get_or_404(db, script_id, teacher_id)
    return ApiResponse(data=_to_response(s))


@router.patch("/{script_id}", response_model=ApiResponse[ExamEvalScriptResponse], summary="更新脚本包")
async def update_script(
    script_id: int,
    data: ExamEvalScriptUpdateRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    s = await _get_or_404(db, script_id, teacher_id)
    s = await crud_script.update_eval_script(
        db, script=s, name=data.name, description=data.description,
        entry_point=data.entry_point,
    )
    return ApiResponse(data=_to_response(s))


@router.delete("/{script_id}", response_model=ApiResponse, summary="删除脚本包")
async def delete_script(
    script_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    s = await _get_or_404(db, script_id, teacher_id)
    try:
        await crud_script.delete_eval_script(db, script=s)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return ApiResponse(data=None, message="已删除")


# ─── Files 子协议（复用 common/bundle_files_router 工厂）─────────────────────

async def _resolve_eval_script(db: AsyncSession, bundle_id: int, teacher_id: int):
    return await _get_or_404(db, bundle_id, teacher_id)


async def _update_eval_script_stats_adapter(
    db: AsyncSession, bundle, file_count: int, total_size_bytes: int, file_manifest: list[dict]
):
    # eval script 无需 manifest，但 update_eval_script_stats 内部会根据
    # storage_root 下 entry_point 是否存在自动重新计算 validate_status。
    await crud_script.update_eval_script_stats(
        db, script=bundle, file_count=file_count, total_size_bytes=total_size_bytes,
    )


_files_router = build_bundle_files_router(
    resolver=_resolve_eval_script,
    stats_updater=_update_eval_script_stats_adapter,
)
router.include_router(_files_router, prefix="/{bundle_id}")
