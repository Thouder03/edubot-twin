"""
教师端仿真容器全局默认配置 API

路由前缀（在 teacher/__init__.py 中注册）：/api/v1/teachers/containers/config
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.schemas.container_config import ContainerDefaultConfigRead, ContainerDefaultConfigUpdate
from app.schemas.common import ApiResponse
from app.crud import container_config as crud_config
from app.core.security import get_current_teacher

router = APIRouter()


@router.get(
    "",
    response_model=ApiResponse[ContainerDefaultConfigRead],
    summary="获取仿真容器全局默认资源配置",
)
async def get_container_default_config(
    db: AsyncSession = Depends(get_db),
    _: int = Depends(get_current_teacher),
):
    cfg = await crud_config.get_default_config(db)
    return ApiResponse(data=ContainerDefaultConfigRead.model_validate(cfg))


@router.put(
    "",
    response_model=ApiResponse[ContainerDefaultConfigRead],
    summary="更新仿真容器全局默认资源配置",
)
async def update_container_default_config(
    data: ContainerDefaultConfigUpdate,
    db: AsyncSession = Depends(get_db),
    _: int = Depends(get_current_teacher),
):
    cfg = await crud_config.upsert_default_config(db, data)
    return ApiResponse(data=ContainerDefaultConfigRead.model_validate(cfg))
