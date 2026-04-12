"""
测评脚本包 CRUD（第11期）

包含：创建 / 获取 / 列表 / 更新 / 删除 / 统计更新 / 入口校验
"""
from datetime import datetime
from pathlib import Path
from typing import Optional
import logging

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exam import Exam, ExamEvalScript, ExamEvalScriptValidateStatus

logger = logging.getLogger(__name__)

# 测评脚本包存储基路径
EXAM_EVAL_SCRIPTS_BASE_DIR = Path("data/exam_eval_scripts").resolve()


async def create_eval_script(
    db: AsyncSession,
    *,
    name: str,
    description: Optional[str] = None,
    entry_point: str = "evaluate.sh",
    created_by: int,
) -> ExamEvalScript:
    """创建测评脚本包"""
    script = ExamEvalScript(
        name=name,
        description=description,
        storage_root="",  # 临时占位
        entry_point=entry_point,
        created_by=created_by,
    )
    db.add(script)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError("NAME_DUPLICATED") from e
    await db.refresh(script)

    # 基于 ID 确定 storage_root
    storage_root = str(EXAM_EVAL_SCRIPTS_BASE_DIR / str(script.id))
    script.storage_root = storage_root
    Path(storage_root).mkdir(parents=True, exist_ok=True)
    await db.commit()
    await db.refresh(script)
    return script


async def get_eval_script(db: AsyncSession, script_id: int) -> Optional[ExamEvalScript]:
    """通过 ID 获取"""
    result = await db.execute(
        select(ExamEvalScript).where(ExamEvalScript.id == script_id)
    )
    return result.scalar_one_or_none()


async def list_eval_scripts(
    db: AsyncSession,
    *,
    created_by: int,
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
) -> tuple[list[ExamEvalScript], int]:
    """分页查询"""
    query = select(ExamEvalScript).where(ExamEvalScript.created_by == created_by)
    count_query = select(func.count()).select_from(ExamEvalScript).where(
        ExamEvalScript.created_by == created_by
    )
    if keyword:
        like = f"%{keyword}%"
        query = query.where(ExamEvalScript.name.like(like))
        count_query = count_query.where(ExamEvalScript.name.like(like))

    total = (await db.execute(count_query)).scalar_one()
    rows = (
        await db.execute(
            query.order_by(ExamEvalScript.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return list(rows), int(total)


async def update_eval_script(
    db: AsyncSession,
    *,
    script: ExamEvalScript,
    name: Optional[str] = None,
    description: Optional[str] = None,
    entry_point: Optional[str] = None,
) -> ExamEvalScript:
    """更新脚本包基础信息"""
    if name is not None:
        script.name = name
    if description is not None:
        script.description = description
    if entry_point is not None:
        script.entry_point = entry_point
    script.updated_at = datetime.utcnow()

    # 更新 entry_point 时重新校验
    if entry_point is not None:
        _validate_entry_point(script)

    await db.commit()
    await db.refresh(script)
    return script


async def delete_eval_script(db: AsyncSession, *, script: ExamEvalScript) -> None:
    """删除脚本包（被考试引用时不可删除）"""
    result = await db.execute(
        select(Exam).where(Exam.eval_script_id == script.id).limit(1)
    )
    if result.scalar_one_or_none():
        raise ValueError("SNAPSHOT_IN_USE")

    await db.delete(script)
    await db.commit()


async def update_eval_script_stats(
    db: AsyncSession,
    *,
    script: ExamEvalScript,
    file_count: int,
    total_size_bytes: int,
) -> ExamEvalScript:
    """更新文件统计并重新校验入口"""
    script.file_count = file_count
    script.total_size_bytes = total_size_bytes
    _validate_entry_point(script)
    script.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(script)
    return script


def _validate_entry_point(script: ExamEvalScript) -> None:
    """
    校验入口文件存在性（SDD §6.4: validate_status）

    仅做最基本的"入口文件存在性"检查，不做脚本语法校验。
    """
    entry_path = Path(script.storage_root) / script.entry_point
    if entry_path.exists() and entry_path.is_file():
        script.validate_status = ExamEvalScriptValidateStatus.VALID
    else:
        script.validate_status = ExamEvalScriptValidateStatus.INVALID if script.file_count > 0 else ExamEvalScriptValidateStatus.PENDING
