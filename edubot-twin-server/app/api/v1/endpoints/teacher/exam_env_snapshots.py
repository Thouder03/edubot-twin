"""
教师端考试环境快照 API（第11期）

端点前缀：/api/v1/teachers/exam-env-snapshots
files 子协议与 env_bundles.py 保持一致，仅存储根目录不同。
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.common.bundle_files_router import build_bundle_files_router
from app.core.security import get_current_teacher
from app.core.snapshot_copier import SnapshotCopyError, copy_snapshot
from app.crud import exam_env_snapshot as crud_snapshot
from app.crud import experiment as crud_experiment
from app.db.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.exam import (
    ExamEnvSnapshotCopyRequest,
    ExamEnvSnapshotCreateRequest,
    ExamEnvSnapshotListItem,
    ExamEnvSnapshotListResponse,
    ExamEnvSnapshotResponse,
    ExamEnvSnapshotUpdateRequest,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _to_response(s) -> ExamEnvSnapshotResponse:
    return ExamEnvSnapshotResponse(
        id=s.id, name=s.name, source_env_bundle_id=s.source_env_bundle_id,
        storage_root=s.storage_root, container_target_dir=s.container_target_dir,
        file_count=s.file_count, total_size_bytes=s.total_size_bytes,
        created_by=s.created_by, created_at=s.created_at, updated_at=s.updated_at,
    )


def _to_list_item(s) -> ExamEnvSnapshotListItem:
    return ExamEnvSnapshotListItem(
        id=s.id, name=s.name, container_target_dir=s.container_target_dir,
        file_count=s.file_count, total_size_bytes=s.total_size_bytes, created_at=s.created_at,
    )


async def _get_or_404(db, snapshot_id: int, teacher_id: int):
    s = await crud_snapshot.get_env_snapshot(db, snapshot_id)
    if not s:
        raise HTTPException(status_code=404, detail="考试环境快照不存在")
    if s.created_by != teacher_id:
        raise HTTPException(status_code=403, detail="无权访问")
    return s


# ─── CRUD ────────────────────────────────────────────────────────────────────

@router.get("", response_model=ApiResponse[ExamEnvSnapshotListResponse], summary="环境快照列表")
async def list_snapshots(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    items, total = await crud_snapshot.list_env_snapshots(
        db, created_by=teacher_id, page=page, page_size=page_size, keyword=keyword,
    )
    return ApiResponse(data=ExamEnvSnapshotListResponse(
        total=total, items=[_to_list_item(s) for s in items],
    ))


@router.post(
    "",
    response_model=ApiResponse[ExamEnvSnapshotResponse],
    status_code=status.HTTP_201_CREATED,
    summary="创建空快照",
)
async def create_snapshot(
    data: ExamEnvSnapshotCreateRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    try:
        s = await crud_snapshot.create_env_snapshot(
            db, name=data.name, container_target_dir=data.container_target_dir,
            created_by=teacher_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return ApiResponse(data=_to_response(s))


@router.post("/copy", response_model=ApiResponse[ExamEnvSnapshotResponse], summary="从实验环境复制")
async def copy_from_env_bundle(
    data: ExamEnvSnapshotCopyRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """从实验环境包复制出考试环境快照（物理文件复制）"""
    # 校验源存在
    source = await crud_experiment.get_env_bundle(db, data.source_env_bundle_id)
    if not source:
        raise HTTPException(status_code=404, detail="SOURCE_BUNDLE_NOT_FOUND")

    # 创建 DB 记录
    try:
        snapshot = await crud_snapshot.create_env_snapshot(
            db, name=data.name,
            container_target_dir=source.container_target_dir,
            created_by=teacher_id,
            source_env_bundle_id=source.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    # 物理复制
    try:
        file_count, total_size = copy_snapshot(source.storage_root, snapshot.storage_root)
    except SnapshotCopyError as e:
        # 回滚 DB 记录
        await db.delete(snapshot)
        await db.commit()
        raise HTTPException(status_code=500, detail="COPY_FAILED_DISK")

    # 更新统计
    await crud_snapshot.update_env_snapshot_stats(
        db, snapshot=snapshot, file_count=file_count, total_size_bytes=total_size,
    )
    return ApiResponse(data=_to_response(snapshot))


@router.get("/{snapshot_id}", response_model=ApiResponse[ExamEnvSnapshotResponse], summary="快照详情")
async def get_snapshot(
    snapshot_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    s = await _get_or_404(db, snapshot_id, teacher_id)
    return ApiResponse(data=_to_response(s))


@router.patch("/{snapshot_id}", response_model=ApiResponse[ExamEnvSnapshotResponse], summary="更新快照")
async def update_snapshot(
    snapshot_id: int,
    data: ExamEnvSnapshotUpdateRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    s = await _get_or_404(db, snapshot_id, teacher_id)
    try:
        s = await crud_snapshot.update_env_snapshot(
            db, snapshot=s, name=data.name, container_target_dir=data.container_target_dir,
        )
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
        await crud_snapshot.delete_env_snapshot(db, snapshot=s)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return ApiResponse(data=None, message="已删除")


# ─── Files 子协议（复用 common/bundle_files_router 工厂）─────────────────────

async def _resolve_env_snapshot(db: AsyncSession, bundle_id: int, teacher_id: int):
    return await _get_or_404(db, bundle_id, teacher_id)


async def _update_env_snapshot_stats_adapter(
    db: AsyncSession, bundle, file_count: int, total_size_bytes: int, file_manifest: list[dict]
):
    # env 快照无需 manifest
    await crud_snapshot.update_env_snapshot_stats(
        db, snapshot=bundle, file_count=file_count, total_size_bytes=total_size_bytes,
    )


_files_router = build_bundle_files_router(
    resolver=_resolve_env_snapshot,
    stats_updater=_update_env_snapshot_stats_adapter,
)
router.include_router(_files_router, prefix="/{bundle_id}")
