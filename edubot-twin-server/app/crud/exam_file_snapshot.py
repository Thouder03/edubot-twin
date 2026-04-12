"""
考试文件快照 CRUD（第11期）

包含：创建 / 获取 / 列表 / 更新 / 删除 / 从实验文件包复制 / 统计更新
"""
from datetime import datetime
from pathlib import Path
from typing import Optional
import logging

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exam import Exam, ExamFileSnapshot

logger = logging.getLogger(__name__)

# 考试文件快照存储基路径
EXAM_FILE_SNAPSHOTS_BASE_DIR = Path("data/exam_file_snapshots").resolve()


async def create_file_snapshot(
    db: AsyncSession,
    *,
    name: str,
    created_by: int,
    source_file_bundle_id: Optional[int] = None,
) -> ExamFileSnapshot:
    """创建考试文件快照"""
    snapshot = ExamFileSnapshot(
        name=name,
        storage_root="",  # 临时占位
        source_file_bundle_id=source_file_bundle_id,
        created_by=created_by,
    )
    db.add(snapshot)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError("NAME_DUPLICATED") from e
    await db.refresh(snapshot)

    # 基于 ID 确定 storage_root
    storage_root = str(EXAM_FILE_SNAPSHOTS_BASE_DIR / str(snapshot.id))
    snapshot.storage_root = storage_root
    Path(storage_root).mkdir(parents=True, exist_ok=True)
    await db.commit()
    await db.refresh(snapshot)
    return snapshot


async def get_file_snapshot(db: AsyncSession, snapshot_id: int) -> Optional[ExamFileSnapshot]:
    """通过 ID 获取快照"""
    result = await db.execute(
        select(ExamFileSnapshot).where(ExamFileSnapshot.id == snapshot_id)
    )
    return result.scalar_one_or_none()


async def list_file_snapshots(
    db: AsyncSession,
    *,
    created_by: int,
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
) -> tuple[list[ExamFileSnapshot], int]:
    """分页查询"""
    query = select(ExamFileSnapshot).where(ExamFileSnapshot.created_by == created_by)
    count_query = select(func.count()).select_from(ExamFileSnapshot).where(
        ExamFileSnapshot.created_by == created_by
    )
    if keyword:
        like = f"%{keyword}%"
        query = query.where(ExamFileSnapshot.name.like(like))
        count_query = count_query.where(ExamFileSnapshot.name.like(like))

    total = (await db.execute(count_query)).scalar_one()
    rows = (
        await db.execute(
            query.order_by(ExamFileSnapshot.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return list(rows), int(total)


async def update_file_snapshot(
    db: AsyncSession,
    *,
    snapshot: ExamFileSnapshot,
    name: Optional[str] = None,
) -> ExamFileSnapshot:
    """更新快照基础信息"""
    # 检查是否被已发布考试引用
    result = await db.execute(
        select(Exam).where(
            Exam.file_snapshot_id == snapshot.id,
            Exam.status == "published",
        ).limit(1)
    )
    if result.scalar_one_or_none():
        raise ValueError("SNAPSHOT_IN_USE")

    if name is not None:
        snapshot.name = name
    snapshot.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(snapshot)
    return snapshot


async def delete_file_snapshot(db: AsyncSession, *, snapshot: ExamFileSnapshot) -> None:
    """删除快照（被任何考试引用时不可删除）"""
    result = await db.execute(
        select(Exam).where(Exam.file_snapshot_id == snapshot.id).limit(1)
    )
    if result.scalar_one_or_none():
        raise ValueError("SNAPSHOT_IN_USE")

    await db.delete(snapshot)
    await db.commit()


async def update_file_snapshot_stats(
    db: AsyncSession,
    *,
    snapshot: ExamFileSnapshot,
    file_count: int,
    total_size_bytes: int,
    file_manifest: list,
) -> ExamFileSnapshot:
    """更新文件统计和 manifest"""
    snapshot.file_count = file_count
    snapshot.total_size_bytes = total_size_bytes
    snapshot.file_manifest = file_manifest
    snapshot.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(snapshot)
    return snapshot
