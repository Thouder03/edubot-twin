from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.container_config import ContainerDefaultConfig
from app.schemas.container_config import ContainerDefaultConfigUpdate

_DEFAULT_ID = 1
_DEFAULTS = {"cpu_limit": 2.0, "memory_limit_mb": 1024, "shm_size_mb": 512}


async def get_default_config(db: AsyncSession) -> ContainerDefaultConfig:
    """获取全局默认配置，不存在则自动插入默认值（幂等）。"""
    result = await db.execute(
        select(ContainerDefaultConfig).where(ContainerDefaultConfig.id == _DEFAULT_ID)
    )
    cfg = result.scalar_one_or_none()
    if cfg is None:
        cfg = ContainerDefaultConfig(id=_DEFAULT_ID, **_DEFAULTS)
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
    return cfg


async def upsert_default_config(
    db: AsyncSession, data: ContainerDefaultConfigUpdate
) -> ContainerDefaultConfig:
    """更新全局默认配置中非 None 的字段。"""
    cfg = await get_default_config(db)
    updates = data.model_dump(exclude_none=True)
    for field, value in updates.items():
        setattr(cfg, field, value)
    cfg.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(cfg)
    return cfg
