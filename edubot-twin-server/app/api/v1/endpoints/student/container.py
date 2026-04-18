"""
学生端容器 API（第四期：心跳上报 + 生命周期管理）

路由前缀：/api/v1/students/container
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.schemas.container import (
    ContainerCreate, ContainerResponse,
    ContainerStatusResponse, StopOnExitRequest,
)
from app.crud import container as crud_container
from app.core.port_allocator import PortExhaustedError
from app.core.security import get_current_user_id, verify_token
from app.models.container import ContainerStatus
from app.schemas.common import ApiResponse
from typing import Optional

router = APIRouter()
logger = logging.getLogger(__name__)


def _extract_public_host_and_scheme(request: Request) -> tuple[str, str, str]:
    """优先使用反向代理头，回退到当前请求 host/scheme。"""
    forwarded_host = request.headers.get("x-forwarded-host", "")
    host = (forwarded_host.split(",")[0] if forwarded_host else request.headers.get("host", "")).strip()

    # host 里可能带端口（例如 127.0.0.1:3000），这里去掉端口，只保留主机名
    if host.startswith("[") and "]" in host:
        host = host[1 : host.index("]")]
    elif host.count(":") == 1:
        host = host.split(":", 1)[0]

    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    http_proto = (forwarded_proto.split(",")[0] if forwarded_proto else request.url.scheme).strip().lower()
    gz_scheme = "https" if http_proto == "https" else "http"
    ros_scheme = "wss" if http_proto == "https" else "ws"

    return host or "localhost", gz_scheme, ros_scheme


@router.get(
    "/mine",
    response_model=ApiResponse[Optional[ContainerStatusResponse]],
    summary="获取当前用户的容器信息",
)
async def get_my_container(
    request: Request,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """从 JWT Token 自动解析 user_id，返回该用户的容器状态。"""
    container = await crud_container.get_container_by_user(db, user_id)
    if not container:
        return ApiResponse(code=0, data=None, message="尚未分配容器")
    host, gz_scheme, ros_scheme = _extract_public_host_and_scheme(request)
    return ApiResponse(
        code=0,
        data=ContainerStatusResponse.from_orm_with_host(
            container,
            host=host,
            gz_scheme=gz_scheme,
            ros_scheme=ros_scheme,
        ),
    )


@router.post(
    "/request",
    response_model=ApiResponse[ContainerResponse],
    status_code=status.HTTP_200_OK,
    summary="请求分配容器（无则创建）",
)
async def request_container(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    请求分配一个仿真容器。

    - 若已有容器（任意状态）→ 直接返回现有容器信息
    - 若无容器 → 自动创建新容器并启动 Docker 实例
    """
    existing = await crud_container.get_container_by_user(db, user_id)
    if existing:
        return ApiResponse(code=0, data=ContainerResponse.model_validate(existing))

    logger.info("[student.container.request] incoming user_id=%s", user_id)
    try:
        container = await crud_container.create_container(
            db,
            ContainerCreate(user_id=user_id),
        )
        logger.info(
            "[student.container.request] created container_id=%s user_id=%s",
            container.id,
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
    summary="启动已停止的容器",
)
async def start_my_container(
    request: Request,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """启动已停止的容器（status=stopped → running）。"""
    container = await crud_container.get_container_by_user(db, user_id)
    if not container:
        return ApiResponse(code=0, data=None, message="尚未分配容器")
    host, gz_scheme, ros_scheme = _extract_public_host_and_scheme(request)
    if container.status == ContainerStatus.RUNNING:
        return ApiResponse(
            code=0,
            data=ContainerStatusResponse.from_orm_with_host(
                container,
                host=host,
                gz_scheme=gz_scheme,
                ros_scheme=ros_scheme,
            ),
        )
    if container.status not in (ContainerStatus.STOPPED,):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"容器状态 {container.status} 不可启动",
        )

    container = await crud_container.start_container(db, container)
    return ApiResponse(
        code=0,
        data=ContainerStatusResponse.from_orm_with_host(
            container,
            host=host,
            gz_scheme=gz_scheme,
            ros_scheme=ros_scheme,
        ),
    )


@router.post(
    "/destroy-and-recreate",
    response_model=ApiResponse[ContainerResponse],
    summary="销毁当前容器并创建新容器",
)
async def destroy_and_recreate(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    原子操作：销毁旧容器（若存在）→ 创建新容器。

    避免前端分两步调用导致的竞态条件。
    """
    existing = await crud_container.get_container_by_user(db, user_id)
    if existing:
        await crud_container.delete_container(db, existing)

    try:
        container = await crud_container.create_container(
            db, ContainerCreate(user_id=user_id)
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
    request: Request,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    前端定期调用，更新 last_heartbeat_at。

    返回容器当前状态，前端据此判断容器是否仍然存活。
    若容器不存在或已停止，前端可触发重新激活弹窗。
    """
    container = await crud_container.get_container_by_user(db, user_id)
    if not container:
        raise HTTPException(status_code=404, detail="尚未分配容器")

    await crud_container.update_heartbeat(db, container)
    await db.refresh(container)

    host, gz_scheme, ros_scheme = _extract_public_host_and_scheme(request)
    data = ContainerStatusResponse.from_orm_with_host(
        container,
        host=host,
        gz_scheme=gz_scheme,
        ros_scheme=ros_scheme,
    )
    data.current_version_id = container.current_version_id
    return ApiResponse(code=0, data=data)


@router.post(
    "/stop",
    response_model=ApiResponse[ContainerStatusResponse],
    summary="停止我的容器",
)
async def stop_my_container(
    request: Request,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """主动停止自己的容器（退出仿真时调用）。"""
    container = await crud_container.get_container_by_user(db, user_id)
    if not container:
        raise HTTPException(status_code=404, detail="尚未分配容器")
    host, gz_scheme, ros_scheme = _extract_public_host_and_scheme(request)
    if container.status != ContainerStatus.RUNNING:
        return ApiResponse(
            code=0,
            data=ContainerStatusResponse.from_orm_with_host(
                container,
                host=host,
                gz_scheme=gz_scheme,
                ros_scheme=ros_scheme,
            ),
        )

    container = await crud_container.stop_container(db, container)
    return ApiResponse(
        code=0,
        data=ContainerStatusResponse.from_orm_with_host(
            container,
            host=host,
            gz_scheme=gz_scheme,
            ros_scheme=ros_scheme,
        ),
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

    user_id = payload.get("user_id")
    if not user_id:
        return {"ok": False, "reason": "no_user_id"}

    container = await crud_container.get_container_by_user(db, user_id)
    if container and container.status == ContainerStatus.RUNNING:
        await crud_container.stop_container(db, container)

    return {"ok": True}
