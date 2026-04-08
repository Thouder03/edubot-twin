"""
学生仿真页容器文件代理（Sidecar 版，student_limited scope）

将所有 /api/v1/students/container-files/* 请求
透明转发至学生容器内 mini_file_server（端口 8010），
注入 X-Access-Scope: student_limited，由 Sidecar 执行路径策略：
  - 允许读取：/home、/root
  - 允许写入：/home/student

认证：普通学生 JWT（非 Shadow）
"""
import logging
from typing import AsyncIterator

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container_manager import get_container_ip
from app.core.system_entrypoint import SIDECAR_PORT
from app.core.security import get_current_student_id
from app.crud import container as crud_container
from app.db.database import get_db

router = APIRouter()
logger = logging.getLogger(__name__)

_HOP_BY_HOP_HEADERS = frozenset({
    "host", "connection", "transfer-encoding", "te",
    "trailer", "upgrade", "keep-alive", "proxy-authenticate",
    "proxy-authorization", "authorization",
})


async def _get_student_container_ip(db: AsyncSession, student_id: int) -> str:
    """获取学生容器 IP，容器不存在或未运行时抛 HTTPException。"""
    container = await crud_container.get_container_by_student(db, student_id)
    if not container or not container.container_id:
        raise HTTPException(status_code=404, detail="未找到仿真容器，请先启动仿真")
    ip = await get_container_ip(container.container_id)
    if not ip:
        raise HTTPException(status_code=503, detail="容器网络未就绪，请等待容器完全启动")
    return ip


def _build_forward_headers(request: Request) -> dict[str, str]:
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in _HOP_BY_HOP_HEADERS
    }
    headers["X-Access-Scope"] = "student_limited"
    return headers


async def _stream_response(response: httpx.Response, client: httpx.AsyncClient) -> AsyncIterator[bytes]:
    try:
        async for chunk in response.aiter_bytes(chunk_size=65536):
            yield chunk
    finally:
        await response.aclose()
        await client.aclose()


@router.api_route("/{action:path}", methods=["GET", "POST", "DELETE", "PUT", "PATCH"])
async def proxy_to_container(
    request: Request,
    action: str,
    student_id: int = Depends(get_current_student_id),
    db: AsyncSession = Depends(get_db),
):
    """
    透明代理：将学生文件操作请求转发至其容器内 Sidecar（8010 端口）。
    scope 固定为 student_limited，路径策略由 Sidecar 强制校验。
    """
    container_ip = await _get_student_container_ip(db, student_id)
    target_url = f"http://{container_ip}:{SIDECAR_PORT}/files/{action}"

    headers = _build_forward_headers(request)
    params = dict(request.query_params)

    logger.info(
        "[student_container_proxy] forward start action=%s method=%s target=%s params=%s",
        action,
        request.method,
        target_url,
        params,
    )

    client = httpx.AsyncClient(timeout=60.0)
    try:
        req = client.build_request(
            method=request.method,
            url=target_url,
            headers=headers,
            params=params,
            content=request.stream(),
        )
        response = await client.send(req, stream=True)

        logger.info(
            "[student_container_proxy] forward response action=%s status=%s content_type=%s",
            action,
            response.status_code,
            response.headers.get("content-type"),
        )
        if response.status_code == 404:
            logger.warning(
                "[student_container_proxy] upstream 404 action=%s target=%s (possible route mismatch)",
                action,
                target_url,
            )

        forward_headers = {
            k: v for k, v in response.headers.items()
            if k.lower() not in _HOP_BY_HOP_HEADERS
        }

        return StreamingResponse(
            _stream_response(response, client),
            status_code=response.status_code,
            headers=forward_headers,
            media_type=response.headers.get("content-type"),
        )
    except httpx.ConnectError:
        await client.aclose()
        raise HTTPException(status_code=503, detail="Sidecar 服务未就绪，请等待容器完全启动")
    except httpx.TimeoutException:
        await client.aclose()
        raise HTTPException(status_code=504, detail="Sidecar 响应超时")
    except Exception as e:
        await client.aclose()
        logger.warning("[student_container_proxy] 转发失败 action=%s: %s", action, e)
        raise HTTPException(status_code=502, detail=f"代理转发失败: {e}")
