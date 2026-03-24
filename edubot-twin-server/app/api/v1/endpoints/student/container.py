"""
学生端容器 API

路由前缀：/api/v1/students/container
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.schemas.container import ContainerResponse, ContainerStatusResponse
from app.crud import container as crud_container
from app.core.port_allocator import PortExhaustedError

router = APIRouter()


@router.get(
    "/mine",
    response_model=ContainerStatusResponse,
    summary="获取当前学生的容器信息",
)
async def get_my_container(
    student_id: int = Query(..., description="学生 ID（临时，后续改为 JWT 解析）"),
    db: AsyncSession = Depends(get_db),
):
    """
    获取当前学生分配的容器状态。

    临时实现：通过 query param 传入 student_id。
    TODO: 后续接入 JWT 鉴权后改为从 token 解析。
    """
    container = await crud_container.get_container_by_student(db, student_id)
    if not container:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"学生 ID={student_id} 尚未分配容器，请联系教师",
        )
    return ContainerStatusResponse.from_orm_with_host(container)


@router.post(
    "/request",
    response_model=ContainerResponse,
    status_code=status.HTTP_200_OK,
    summary="请求分配容器",
)
async def request_container(
    student_id: int = Query(..., description="学生 ID（临时，后续改为 JWT 解析）"),
    db: AsyncSession = Depends(get_db),
):
    """
    学生请求分配一个仿真容器。

    - 若已有容器（任意状态）→ 直接返回现有容器信息
    - 若无容器 → 自动创建新容器（Mock 模式，status=RUNNING）
    """
    from app.schemas.container import ContainerCreate

    existing = await crud_container.get_container_by_student(db, student_id)
    if existing:
        return ContainerResponse.model_validate(existing)

    # 自动创建
    try:
        container = await crud_container.create_container(
            db,
            ContainerCreate(student_id=student_id),
        )
    except PortExhaustedError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )

    return ContainerResponse.model_validate(container)
