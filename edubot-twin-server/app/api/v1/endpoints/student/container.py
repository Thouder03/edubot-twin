"""
学生端容器 API（第三期：JWT 鉴权改造）

路由前缀：/api/v1/students/container
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.schemas.container import ContainerCreate, ContainerResponse, ContainerStatusResponse
from app.crud import container as crud_container
from app.core.port_allocator import PortExhaustedError
from app.core.security import get_current_student_id
from app.models.container import ContainerStatus
from app.schemas.common import ApiResponse
from typing import Optional

router = APIRouter()


@router.get(
    "/mine",
    response_model=ApiResponse[Optional[ContainerStatusResponse]],
    summary="获取当前学生的容器信息",
)
async def get_my_container(
    student_id: int = Depends(get_current_student_id),
    db: AsyncSession = Depends(get_db),
):
    """从 JWT Token 自动解析 student_id，返回该学生的容器状态。"""
    container = await crud_container.get_container_by_student(db, student_id)
    if not container:
        return ApiResponse(code=0, data=None, message="尚未分配容器")
    return ApiResponse(code=0, data=ContainerStatusResponse.from_orm_with_host(container))


@router.post(
    "/request",
    response_model=ApiResponse[ContainerResponse],
    status_code=status.HTTP_200_OK,
    summary="请求分配容器（无则创建）",
)
async def request_container(
    student_id: int = Depends(get_current_student_id),
    db: AsyncSession = Depends(get_db),
):
    """
    学生请求分配一个仿真容器。

    - 若已有容器（任意状态）→ 直接返回现有容器信息
    - 若无容器 → 自动创建新容器并启动 Docker 实例
    """
    existing = await crud_container.get_container_by_student(db, student_id)
    if existing:
        return ApiResponse(code=0, data=ContainerResponse.model_validate(existing))

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

    return ApiResponse(code=0, data=ContainerResponse.model_validate(container))


@router.post(
    "/start",
    response_model=ApiResponse[Optional[ContainerStatusResponse]],
    summary="启动学生的已停止容器",
)
async def start_my_container(
    student_id: int = Depends(get_current_student_id),
    db: AsyncSession = Depends(get_db),
):
    """启动已停止的容器（status=stopped → running）。"""
    container = await crud_container.get_container_by_student(db, student_id)
    if not container:
        return ApiResponse(code=0, data=None, message="尚未分配容器")
    if container.status == ContainerStatus.RUNNING:
        return ApiResponse(code=0, data=ContainerStatusResponse.from_orm_with_host(container))
    if container.status not in (ContainerStatus.STOPPED,):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"容器状态 {container.status} 不可启动",
        )

    container = await crud_container.start_container(db, container)
    return ApiResponse(code=0, data=ContainerStatusResponse.from_orm_with_host(container))


@router.post(
    "/destroy-and-recreate",
    response_model=ApiResponse[ContainerResponse],
    summary="销毁当前容器并创建新容器",
)
async def destroy_and_recreate(
    student_id: int = Depends(get_current_student_id),
    db: AsyncSession = Depends(get_db),
):
    """
    原子操作：销毁旧容器（若存在）→ 创建新容器。

    避免前端分两步调用导致的竞态条件。
    """
    existing = await crud_container.get_container_by_student(db, student_id)
    if existing:
        await crud_container.delete_container(db, existing)

    try:
        container = await crud_container.create_container(
            db, ContainerCreate(student_id=student_id)
        )
    except PortExhaustedError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )

    return ApiResponse(code=0, data=ContainerResponse.model_validate(container))
