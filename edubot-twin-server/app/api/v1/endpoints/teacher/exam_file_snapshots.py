"""
教师端考试文件快照 API（第11期）

端点前缀：/api/v1/teachers/exam-file-snapshots
结构与 exam_env_snapshots.py 完全对称。
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.common.bundle_files_router import build_bundle_files_router
from app.services.bundle_file_service import BundleFileService
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

router = APIRouter()
logger = logging.getLogger(__name__)


def _to_response(s) -> ExamFileSnapshotResponse:
    return ExamFileSnapshotResponse(
        id=s.id, name=s.name, source_file_bundle_id=s.source_file_bundle_id,
        storage_root=s.storage_root, file_count=s.file_count,
        total_size_bytes=s.total_size_bytes, file_manifest=s.file_manifest,
        created_by=s.created_by, created_at=s.created_at, updated_at=s.updated_at,
    )


def _get_service(snapshot) -> BundleFileService:
    """为快照创建 BundleFileService 实例以扫描生成 manifest"""
    return BundleFileService(storage_root=snapshot.storage_root)


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


# ─── Files 子协议（复用 common/bundle_files_router 工厂）─────────────────────

async def _resolve_file_snapshot(db: AsyncSession, bundle_id: int, teacher_id: int):
    return await _get_or_404(db, bundle_id, teacher_id)


async def _update_file_snapshot_stats_adapter(
    db: AsyncSession, bundle, file_count: int, total_size_bytes: int, file_manifest: list[dict]
):
    await crud_snapshot.update_file_snapshot_stats(
        db,
        snapshot=bundle,
        file_count=file_count,
        total_size_bytes=total_size_bytes,
        file_manifest=file_manifest,
    )


_files_router = build_bundle_files_router(
    resolver=_resolve_file_snapshot,
    stats_updater=_update_file_snapshot_stats_adapter,
)
router.include_router(_files_router, prefix="/{bundle_id}")
