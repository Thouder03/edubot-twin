"""
Dry Run 容器文件系统透明代理（Sidecar 版）

将所有 /api/v1/teachers/dry-run-tools/container-files/* 请求
透明转发至容器内 mini_file_server（端口 8010），注入 X-Access-Scope: shadow_root。

替代原 docker exec 方案（container_files.py），支持：
- 大文件上传 / 下载流式传输
- 全部文件操作（list/read/save/upload/delete/mkdir/rename/move/copy/...）
- 无内存峰值的流式转发

认证：Shadow 学生 JWT（is_shadow=True）
"""
import logging
from typing import AsyncIterator

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container_manager import get_container_ip
from app.core.system_entrypoint import SIDECAR_PORT
from app.core.security import get_current_user_id
from app.crud import container as crud_container
from app.crud.shadow_student import is_shadow_user
from app.db.database import get_db

router = APIRouter()
logger = logging.getLogger(__name__)

# 不应转发给 Sidecar 的宿主机请求头
_HOP_BY_HOP_HEADERS = frozenset({
    "host", "connection", "transfer-encoding", "te",
    "trailer", "upgrade", "keep-alive", "proxy-authenticate",
    "proxy-authorization", "authorization",
})


async def _get_shadow_container_ip(db: AsyncSession, user_id: int) -> str:
    """验证为 Shadow 学生并返回容器 IP，否则抛 HTTPException。"""
    if not await is_shadow_user(db, user_id):
        raise HTTPException(status_code=403, detail="仅 Dry Run 模式可用")
    container = await crud_container.get_container_by_user(db, user_id)
    if not container or not container.container_id:
        raise HTTPException(status_code=404, detail="未找到 Dry Run 容器")
    ip = await get_container_ip(container.container_id)
    if not ip:
        raise HTTPException(status_code=503, detail="容器网络未就绪，无法连接 Sidecar")
    return ip


def _build_forward_headers(request: Request) -> dict[str, str]:
    """构建转发头（过滤 hop-by-hop，注入 scope）。"""
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in _HOP_BY_HOP_HEADERS
    }
    headers["X-Access-Scope"] = "shadow_root"
    return headers


async def _stream_response(response: httpx.Response) -> AsyncIterator[bytes]:
    async for chunk in response.aiter_bytes(chunk_size=65536):
        yield chunk


@router.api_route("/{action:path}", methods=["GET", "POST", "DELETE", "PUT", "PATCH"])
async def proxy_to_container(
    request: Request,
    action: str,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    透明代理：将所有文件操作请求转发至容器内 Sidecar（8010 端口）。
    action 对应 mini_file_server 的子路径（如 list/read/upload 等）。
    """
    container_ip = await _get_shadow_container_ip(db, user_id)
    target_url = f"http://{container_ip}:{SIDECAR_PORT}/files/{action}"

    headers = _build_forward_headers(request)
    params = dict(request.query_params)

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            req = client.build_request(
                method=request.method,
                url=target_url,
                headers=headers,
                params=params,
                content=request.stream(),
            )
            response = await client.send(req, stream=True)

        # 过滤转发响应头
        forward_headers = {
            k: v for k, v in response.headers.items()
            if k.lower() not in _HOP_BY_HOP_HEADERS
        }

        return StreamingResponse(
            _stream_response(response),
            status_code=response.status_code,
            headers=forward_headers,
            media_type=response.headers.get("content-type"),
        )
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Sidecar 服务未就绪，请等待容器完全启动")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Sidecar 响应超时")
    except Exception as e:
        logger.warning("[container_proxy] 转发失败 action=%s: %s", action, e)
        raise HTTPException(status_code=502, detail=f"代理转发失败: {e}")
