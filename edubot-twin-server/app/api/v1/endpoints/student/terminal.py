"""
学生端容器终端 API（第六期）

路由前缀：/api/v1/students/terminal
"""
import asyncio
import logging
from collections import defaultdict, deque
from typing import Deque

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from fastapi.websockets import WebSocketState

from app.core.security import verify_token
from app.db.database import AsyncSessionLocal
from app.crud import container as crud_container

logger = logging.getLogger(__name__)

router = APIRouter()

# 连接频控：同一 student 在窗口期内最多允许 N 次连接尝试
RATE_LIMIT_WINDOW_SECONDS = 60
MAX_CONNECTION_ATTEMPTS = 8
_connection_attempts: dict[int, Deque[float]] = defaultdict(deque)


def _is_rate_limited(student_id: int, now: float) -> tuple[bool, int]:
    attempts = _connection_attempts[student_id]
    window_start = now - RATE_LIMIT_WINDOW_SECONDS

    while attempts and attempts[0] < window_start:
        attempts.popleft()

    attempts.append(now)
    current_count = len(attempts)
    return current_count > MAX_CONNECTION_ATTEMPTS, current_count


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
    client = f"{websocket.client.host}:{websocket.client.port}" if websocket.client else "unknown"

    # ── 1. 验证 Token / 角色 / 频控 ─────────────────────────────────
    payload = verify_token(token)
    if not payload:
        logger.warning(f"[Terminal] 拒绝连接: token 无效, client={client}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    student_id = payload.get("user_id")
    role = payload.get("role")
    if not student_id or role != "student":
        logger.warning(
            f"[Terminal] 拒绝连接: 非学生或缺少 user_id, role={role}, user_id={student_id}, client={client}"
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    now = asyncio.get_running_loop().time()
    limited, current_count = _is_rate_limited(student_id, now)
    if limited:
        logger.warning(
            f"[Terminal] 连接频控触发: student={student_id}, attempts={current_count}/"
            f"{MAX_CONNECTION_ATTEMPTS}, window={RATE_LIMIT_WINDOW_SECONDS}s, client={client}"
        )
        await websocket.accept()
        await websocket.send_text(
            "\r\n[错误] 连接过于频繁，请稍后重试。\r\n"
            f"（限制：{RATE_LIMIT_WINDOW_SECONDS} 秒内最多 {MAX_CONNECTION_ATTEMPTS} 次）\r\n"
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # ── 2. 查找容器 ──────────────────────────────────────────────
    async with AsyncSessionLocal() as db:
        container = await crud_container.get_container_by_user(db, student_id)

    if not container or not container.container_id:
        logger.warning(f"[Terminal] 拒绝连接: 未找到学生容器, student={student_id}, client={client}")
        await websocket.accept()
        await websocket.send_text("\r\n[错误] 未找到可用容器，请先启动仿真容器。\r\n")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    if container.status != "running":
        logger.warning(
            f"[Terminal] 拒绝连接: 容器未运行, student={student_id}, status={container.status}, client={client}"
        )
        await websocket.accept()
        await websocket.send_text(
            f"\r\n[错误] 容器当前状态为 {container.status}，请等待容器运行后再打开终端。\r\n"
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    container_id = container.container_id

    # ── 3. 接受 WebSocket 连接 ────────────────────────────────────
    await websocket.accept()
    session_start = asyncio.get_running_loop().time()
    logger.info(
        f"[Terminal] 会话开始: student={student_id}, container={container_id[:12]}, client={client}"
    )

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
        logger.error(
            f"[Terminal] docker exec 启动失败: Docker CLI 不存在, student={student_id}, "
            f"container={container_id[:12]}, client={client}"
        )
        await websocket.send_text("\r\n[错误] 服务器未安装 Docker CLI，无法打开终端。\r\n")
        await websocket.close()
        return
    except Exception as e:
        logger.error(
            f"[Terminal] docker exec 启动失败: student={student_id}, container={container_id[:12]}, "
            f"client={client}, error={e}"
        )
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

    _, pending = await asyncio.wait(
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

    duration = asyncio.get_running_loop().time() - session_start
    logger.info(
        f"[Terminal] 会话结束: student={student_id}, container={container_id[:12]}, "
        f"client={client}, duration={duration:.2f}s"
    )

    if websocket.client_state == WebSocketState.CONNECTED:
        try:
            await websocket.send_text("\r\n[会话已结束]\r\n")
            await websocket.close()
        except Exception:
            pass
