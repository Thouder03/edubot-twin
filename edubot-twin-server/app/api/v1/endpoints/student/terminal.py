"""
学生端容器终端 API（第六期）

路由前缀：/api/v1/students/terminal
"""
import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from fastapi.websockets import WebSocketState

from app.core.security import verify_token
from app.db.database import AsyncSessionLocal
from app.crud import container as crud_container

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def terminal_ws(
    websocket: WebSocket,
    token: str = Query(..., description="JWT Token（WebSocket 无法自定义 Header）"),
):
    """
    容器终端 WebSocket。

    鉴权：token 放在 query string 中（WebSocket 规范限制）。
    建连后，双向透传学生容器的 docker exec 会话。
    """
    # ── 1. 验证 Token ──────────────────────────────────────────────
    payload = verify_token(token)
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    student_id = payload.get("user_id")
    if not student_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # ── 2. 查找容器 ──────────────────────────────────────────────
    async with AsyncSessionLocal() as db:
        container = await crud_container.get_container_by_student(db, student_id)

    if not container or not container.container_id:
        await websocket.accept()
        await websocket.send_text("\r\n[错误] 未找到可用容器，请先启动仿真容器。\r\n")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    if container.status != "running":
        await websocket.accept()
        await websocket.send_text(
            f"\r\n[错误] 容器当前状态为 {container.status}，请等待容器运行后再打开终端。\r\n"
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    container_id = container.container_id

    # ── 3. 接受 WebSocket 连接 ────────────────────────────────────
    await websocket.accept()
    logger.info(f"[Terminal] 学生 {student_id} 连接容器 {container_id[:12]} 的终端")

    # ── 4. 启动 docker exec ──────────────────────────────────────
    import shlex
    safe_container_id = shlex.quote(container_id)
    proc: asyncio.subprocess.Process | None = None
    try:
        proc = await asyncio.create_subprocess_exec(
            "script", "-qc", f"docker exec -it -e TERM=xterm {safe_container_id} /bin/bash", "/dev/null",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except FileNotFoundError:
        await websocket.send_text("\r\n[错误] 服务器未安装 Docker CLI，无法打开终端。\r\n")
        await websocket.close()
        return
    except Exception as e:
        logger.error(f"[Terminal] docker exec 启动失败: {e}")
        await websocket.send_text(f"\r\n[错误] 启动终端失败: {e}\r\n")
        await websocket.close()
        return

    # ── 5. 双向透传 ──────────────────────────────────────────────
    async def read_from_docker():
        """从 docker stdout 读数据 → 发到 WebSocket"""
        try:
            while True:
                if proc.stdout is None:
                    break
                data = await proc.stdout.read(4096)
                if not data:
                    break
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_bytes(data)
        except Exception as e:
            logger.warning(f"[Terminal] read_from_docker 异常: {e}")

    async def write_to_docker():
        """从 WebSocket 收数据 → 写到 docker stdin"""
        try:
            while True:
                data = await websocket.receive()
                if data["type"] == "websocket.disconnect":
                    break
                raw = data.get("bytes") or (data.get("text") or "").encode()
                if raw and proc.stdin and not proc.stdin.is_closing():
                    proc.stdin.write(raw)
                    await proc.stdin.drain()
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.warning(f"[Terminal] write_to_docker 异常: {e}")

    # 并发运行双向透传
    read_task = asyncio.create_task(read_from_docker())
    write_task = asyncio.create_task(write_to_docker())

    done, pending = await asyncio.wait(
        [read_task, write_task],
        return_when=asyncio.FIRST_COMPLETED,
    )

    # 清理
    for task in pending:
        task.cancel()

    if proc.returncode is None:
        try:
            proc.kill()
        except ProcessLookupError:
            pass

    logger.info(f"[Terminal] 学生 {student_id} 的终端会话已结束")

    if websocket.client_state == WebSocketState.CONNECTED:
        try:
            await websocket.send_text("\r\n[会话已结束]\r\n")
            await websocket.close()
        except Exception:
            pass
