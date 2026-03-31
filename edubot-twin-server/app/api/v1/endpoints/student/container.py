"""
学生端容器 API（第四期：心跳上报 + 生命周期管理）

路由前缀：/api/v1/students/container
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.schemas.container import (
    ContainerCreate, ContainerResponse,
    ContainerStatusResponse, StopOnExitRequest,
)
from app.crud import container as crud_container
from app.core.port_allocator import PortExhaustedError
from app.core.security import get_current_student_id, verify_token
from app.models.container import ContainerStatus
from app.schemas.common import ApiResponse
from typing import Optional

router = APIRouter()
logger = logging.getLogger(__name__)


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
    container = await crud_container.get_container_by_user(db, student_id)
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
    existing = await crud_container.get_container_by_user(db, student_id)
    if existing:
        return ApiResponse(code=0, data=ContainerResponse.model_validate(existing))

    logger.info("[student.container.request] incoming student_id=%s", student_id)
    try:
        container = await crud_container.create_container(
            db,
            ContainerCreate(user_id=student_id),
        )
        logger.info(
            "[student.container.request] created container_id=%s student_id=%s user_id=%s",
            container.id,
            getattr(container, "student_id", None),
            getattr(container, "user_id", None),
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
    container = await crud_container.get_container_by_user(db, student_id)
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
    existing = await crud_container.get_container_by_user(db, student_id)
    if existing:
        await crud_container.delete_container(db, existing)

    try:
        container = await crud_container.create_container(
            db, ContainerCreate(user_id=student_id)
        )
    except PortExhaustedError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )

    return ApiResponse(code=0, data=ContainerResponse.model_validate(container))


@router.post(
    "/heartbeat",
    response_model=ApiResponse[ContainerStatusResponse],
    summary="心跳上报",
)
async def heartbeat(
    student_id: int = Depends(get_current_student_id),
    db: AsyncSession = Depends(get_db),
):
    """
    前端定期调用，更新 last_heartbeat_at。

    返回容器当前状态，前端据此判断容器是否仍然存活。
    若容器不存在或已停止，前端可触发重新激活弹窗。
    """
    container = await crud_container.get_container_by_user(db, student_id)
    if not container:
        raise HTTPException(status_code=404, detail="尚未分配容器")

    await crud_container.update_heartbeat(db, container)
    await db.refresh(container)

    return ApiResponse(
        code=0,
        data=ContainerStatusResponse.from_orm_with_host(container)
    )


@router.post(
    "/stop",
    response_model=ApiResponse[ContainerStatusResponse],
    summary="停止我的容器",
)
async def stop_my_container(
    student_id: int = Depends(get_current_student_id),
    db: AsyncSession = Depends(get_db),
):
    """学生主动停止自己的容器（退出仿真时调用）。"""
    container = await crud_container.get_container_by_user(db, student_id)
    if not container:
        raise HTTPException(status_code=404, detail="尚未分配容器")
    if container.status != ContainerStatus.RUNNING:
        return ApiResponse(
            code=0,
            data=ContainerStatusResponse.from_orm_with_host(container)
        )

    container = await crud_container.stop_container(db, container)
    return ApiResponse(
        code=0,
        data=ContainerStatusResponse.from_orm_with_host(container)
    )


@router.post(
    "/stop-on-exit",
    summary="页面退出时停止容器（Token in body）",
)
async def stop_on_exit(
    body: StopOnExitRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    供 navigator.sendBeacon() 调用（无法携带 Authorization Header）。
    Token 放在请求体中验证，静默成功/失败（均返回 200）。
    """
    payload = verify_token(body.token)
    if not payload:
        return {"ok": False, "reason": "invalid_token"}

    student_id = payload.get("user_id")
    if not student_id:
        return {"ok": False, "reason": "no_user_id"}

    container = await crud_container.get_container_by_user(db, student_id)
    if container and container.status == ContainerStatus.RUNNING:
        await crud_container.stop_container(db, container)

    return {"ok": True}
