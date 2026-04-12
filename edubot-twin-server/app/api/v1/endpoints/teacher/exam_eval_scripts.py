"""
教师端测评脚本包 API（第11期）

端点前缀：/api/v1/teachers/exam-eval-scripts
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.schemas.experiment import (
    FileListItem,
    FileListResponse,
    FileReadResponse,
    FileSaveRequest,
    FileUploadResponse,
)
from app.services.bundle_file_service import (
    BundleFileError,
    BundleFileService,
    FileSizeExceededError,
    FileNotFoundError as BundleFileNotFoundError,
    PathTraversalError,
    FileConflictError,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_service(script) -> BundleFileService:
    return BundleFileService(storage_root=script.storage_root)


def _handle_error(e: BundleFileError):
    raise HTTPException(status_code=e.status_code, detail=e.code)


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


# ─── Files 子协议 ─────────────────────────────────────────────────────────────

@router.get("/{script_id}/files", response_model=ApiResponse[FileListResponse], summary="列目录")
async def list_files(
    script_id: int,
    path: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    s = await _get_or_404(db, script_id, teacher_id)
    svc = _get_service(s)
    try:
        items = svc.list_files(path or "")
    except PathTraversalError as e:
        _handle_error(e)
    return ApiResponse(data=FileListResponse(items=[FileListItem(**item) for item in items]))


@router.post("/{script_id}/files/upload", response_model=ApiResponse[FileUploadResponse], summary="上传文件")
async def upload_file(
    script_id: int,
    file: UploadFile = File(...),
    path: Optional[str] = Form(default=None),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    s = await _get_or_404(db, script_id, teacher_id)
    svc = _get_service(s)
    file_data = await file.read()
    try:
        svc.save_uploaded_file(file.filename or "upload", file_data, target_dir=path)
    except (FileSizeExceededError, PathTraversalError) as e:
        _handle_error(e)
    fc, ts, _ = svc.scan_directory()
    await crud_script.update_eval_script_stats(db, script=s, file_count=fc, total_size_bytes=ts)
    return ApiResponse(data=FileUploadResponse(file_count=fc, total_size_bytes=ts))


@router.get("/{script_id}/files/read", response_model=ApiResponse[FileReadResponse], summary="读文件")
async def read_file(
    script_id: int,
    path: str = Query(...),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    s = await _get_or_404(db, script_id, teacher_id)
    svc = _get_service(s)
    try:
        content, encoding = svc.read_file(path)
        abs_path = svc._safe_path(path)
        mtime = abs_path.stat().st_mtime if abs_path.exists() else None
    except (BundleFileNotFoundError, PathTraversalError) as e:
        _handle_error(e)
    return ApiResponse(data=FileReadResponse(content=content, encoding=encoding, modified_at=mtime))


@router.post("/{script_id}/files/save", response_model=ApiResponse[dict], summary="保存文件")
async def save_file(
    script_id: int,
    data: FileSaveRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    s = await _get_or_404(db, script_id, teacher_id)
    svc = _get_service(s)
    try:
        new_mtime = svc.save_file(data.path, data.content, data.modified_at)
    except (FileConflictError, PathTraversalError) as e:
        _handle_error(e)
    fc, ts, _ = svc.scan_directory()
    await crud_script.update_eval_script_stats(db, script=s, file_count=fc, total_size_bytes=ts)
    return ApiResponse(data={"modified_at": new_mtime})


@router.delete("/{script_id}/files/delete", status_code=status.HTTP_204_NO_CONTENT, summary="删除文件")
async def delete_file(
    script_id: int,
    path: str = Query(...),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    s = await _get_or_404(db, script_id, teacher_id)
    svc = _get_service(s)
    try:
        svc.delete_file(path)
    except BundleFileError as e:
        _handle_error(e)
    fc, ts, _ = svc.scan_directory()
    await crud_script.update_eval_script_stats(db, script=s, file_count=fc, total_size_bytes=ts)
