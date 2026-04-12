"""
教师端考试文件快照 API（第11期）

端点前缀：/api/v1/teachers/exam-file-snapshots
结构与 exam_env_snapshots.py 完全对称。
"""
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_teacher
from app.core.snapshot_copier import SnapshotCopyError, copy_snapshot
from app.crud import exam_file_snapshot as crud_snapshot
from app.crud import experiment as crud_experiment
from app.db.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.exam import (
    ExamFileSnapshotCopyRequest,
    ExamFileSnapshotCreateRequest,
    ExamFileSnapshotListItem,
    ExamFileSnapshotListResponse,
    ExamFileSnapshotResponse,
    ExamFileSnapshotUpdateRequest,
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


def _get_service(snapshot) -> BundleFileService:
    return BundleFileService(storage_root=snapshot.storage_root)


def _handle_error(e: BundleFileError):
    raise HTTPException(status_code=e.status_code, detail=e.code)


def _to_response(s) -> ExamFileSnapshotResponse:
    return ExamFileSnapshotResponse(
        id=s.id, name=s.name, source_file_bundle_id=s.source_file_bundle_id,
        storage_root=s.storage_root, file_count=s.file_count,
        total_size_bytes=s.total_size_bytes, file_manifest=s.file_manifest,
        created_by=s.created_by, created_at=s.created_at, updated_at=s.updated_at,
    )


def _to_list_item(s) -> ExamFileSnapshotListItem:
    return ExamFileSnapshotListItem(
        id=s.id, name=s.name, file_count=s.file_count,
        total_size_bytes=s.total_size_bytes, created_at=s.created_at,
    )


async def _get_or_404(db, snapshot_id: int, teacher_id: int):
    s = await crud_snapshot.get_file_snapshot(db, snapshot_id)
    if not s:
        raise HTTPException(status_code=404, detail="考试文件快照不存在")
    if s.created_by != teacher_id:
        raise HTTPException(status_code=403, detail="无权访问")
    return s


# ─── CRUD ────────────────────────────────────────────────────────────────────

@router.get("", response_model=ApiResponse[ExamFileSnapshotListResponse], summary="文件快照列表")
async def list_snapshots(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    items, total = await crud_snapshot.list_file_snapshots(
        db, created_by=teacher_id, page=page, page_size=page_size, keyword=keyword,
    )
    return ApiResponse(data=ExamFileSnapshotListResponse(
        total=total, items=[_to_list_item(s) for s in items],
    ))


@router.post(
    "",
    response_model=ApiResponse[ExamFileSnapshotResponse],
    status_code=status.HTTP_201_CREATED,
    summary="创建空文件快照",
)
async def create_snapshot(
    data: ExamFileSnapshotCreateRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    try:
        s = await crud_snapshot.create_file_snapshot(db, name=data.name, created_by=teacher_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return ApiResponse(data=_to_response(s))


@router.post("/copy", response_model=ApiResponse[ExamFileSnapshotResponse], summary="从实验文件复制")
async def copy_from_file_bundle(
    data: ExamFileSnapshotCopyRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """从实验文件包复制出考试文件快照"""
    source = await crud_experiment.get_bundle(db, data.source_file_bundle_id)
    if not source:
        raise HTTPException(status_code=404, detail="SOURCE_BUNDLE_NOT_FOUND")

    try:
        snapshot = await crud_snapshot.create_file_snapshot(
            db, name=data.name, created_by=teacher_id,
            source_file_bundle_id=source.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    try:
        file_count, total_size = copy_snapshot(source.storage_root, snapshot.storage_root)
    except SnapshotCopyError:
        await db.delete(snapshot)
        await db.commit()
        raise HTTPException(status_code=500, detail="COPY_FAILED_DISK")

    # 重建 manifest
    svc = _get_service(snapshot)
    _, _, manifest = svc.scan_directory()
    await crud_snapshot.update_file_snapshot_stats(
        db, snapshot=snapshot, file_count=file_count,
        total_size_bytes=total_size, file_manifest=manifest,
    )
    return ApiResponse(data=_to_response(snapshot))


@router.get("/{snapshot_id}", response_model=ApiResponse[ExamFileSnapshotResponse], summary="快照详情")
async def get_snapshot(
    snapshot_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    s = await _get_or_404(db, snapshot_id, teacher_id)
    return ApiResponse(data=_to_response(s))


@router.patch("/{snapshot_id}", response_model=ApiResponse[ExamFileSnapshotResponse], summary="更新快照")
async def update_snapshot(
    snapshot_id: int,
    data: ExamFileSnapshotUpdateRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    s = await _get_or_404(db, snapshot_id, teacher_id)
    try:
        s = await crud_snapshot.update_file_snapshot(db, snapshot=s, name=data.name)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return ApiResponse(data=_to_response(s))


@router.delete("/{snapshot_id}", response_model=ApiResponse, summary="删除快照")
async def delete_snapshot(
    snapshot_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    s = await _get_or_404(db, snapshot_id, teacher_id)
    try:
        await crud_snapshot.delete_file_snapshot(db, snapshot=s)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return ApiResponse(data=None, message="已删除")


# ─── Files 子协议 ─────────────────────────────────────────────────────────────

@router.get("/{snapshot_id}/files", response_model=ApiResponse[FileListResponse], summary="列目录")
async def list_files(
    snapshot_id: int,
    path: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    s = await _get_or_404(db, snapshot_id, teacher_id)
    svc = _get_service(s)
    try:
        items = svc.list_files(path or "")
    except PathTraversalError as e:
        _handle_error(e)
    return ApiResponse(data=FileListResponse(items=[FileListItem(**item) for item in items]))


@router.post("/{snapshot_id}/files/upload", response_model=ApiResponse[FileUploadResponse], summary="上传文件")
async def upload_file(
    snapshot_id: int,
    file: UploadFile = File(...),
    path: Optional[str] = Form(default=None),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    s = await _get_or_404(db, snapshot_id, teacher_id)
    svc = _get_service(s)
    file_data = await file.read()
    try:
        svc.save_uploaded_file(file.filename or "upload", file_data, target_dir=path)
    except (FileSizeExceededError, PathTraversalError) as e:
        _handle_error(e)
    fc, ts, manifest = svc.scan_directory()
    await crud_snapshot.update_file_snapshot_stats(
        db, snapshot=s, file_count=fc, total_size_bytes=ts, file_manifest=manifest,
    )
    return ApiResponse(data=FileUploadResponse(file_count=fc, total_size_bytes=ts))


@router.get("/{snapshot_id}/files/read", response_model=ApiResponse[FileReadResponse], summary="读文件")
async def read_file(
    snapshot_id: int,
    path: str = Query(...),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    s = await _get_or_404(db, snapshot_id, teacher_id)
    svc = _get_service(s)
    try:
        content, encoding = svc.read_file(path)
        abs_path = svc._safe_path(path)
        mtime = abs_path.stat().st_mtime if abs_path.exists() else None
    except (BundleFileNotFoundError, PathTraversalError) as e:
        _handle_error(e)
    return ApiResponse(data=FileReadResponse(content=content, encoding=encoding, modified_at=mtime))


@router.post("/{snapshot_id}/files/save", response_model=ApiResponse[dict], summary="保存文件")
async def save_file(
    snapshot_id: int,
    data: FileSaveRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    s = await _get_or_404(db, snapshot_id, teacher_id)
    svc = _get_service(s)
    try:
        new_mtime = svc.save_file(data.path, data.content, data.modified_at)
    except (FileConflictError, PathTraversalError) as e:
        _handle_error(e)
    return ApiResponse(data={"modified_at": new_mtime})


@router.delete("/{snapshot_id}/files/delete", status_code=status.HTTP_204_NO_CONTENT, summary="删除文件")
async def delete_file(
    snapshot_id: int,
    path: str = Query(...),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    s = await _get_or_404(db, snapshot_id, teacher_id)
    svc = _get_service(s)
    try:
        svc.delete_file(path)
    except BundleFileError as e:
        _handle_error(e)
    fc, ts, manifest = svc.scan_directory()
    await crud_snapshot.update_file_snapshot_stats(
        db, snapshot=s, file_count=fc, total_size_bytes=ts, file_manifest=manifest,
    )
