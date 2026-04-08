"""
学生端容器终端 API（第六期）

路由前缀：/api/v1/students/terminal
"""
import asyncio
import logging
from collections import defaultdict, deque
from typing import Deque, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from fastapi.websockets import WebSocketState

from app.core.security import verify_token
from app.db.database import AsyncSessionLocal
from app.crud import container as crud_container
from app.crud import student as crud_student

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


async def _ensure_student_dir_permissions(container_id: str) -> None:
    """确保容器内 /home/student 目录可被 student(uid=1000) 正常读写。"""
    cmd = (
        "mkdir -p /home/student/experiment && "
        "chown -R 1000:1000 /home/student && "
        "chmod -R u+rwX,g+rwX /home/student"
    )

    proc = await asyncio.create_subprocess_exec(
        "docker",
        "exec",
        container_id,
        "bash",
        "-lc",
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await proc.communicate()
    output = ((stdout or b"") + (stderr or b"")).decode("utf-8", errors="replace").strip()

    if (proc.returncode or 0) != 0:
        raise RuntimeError(output or "set experiment permissions failed")


@router.websocket("/ws")
async def terminal_ws(
    websocket: WebSocket,
    token: str = Query(..., description="JWT Token（WebSocket 无法自定义 Header）"),
    root: str = Query(default="0", description="root=1 以 root 身份执行（仅 Shadow 学生/Dry Run 可用）"),
):
    """
    容器终端 WebSocket。

    鉴权：token 放在 query string 中（WebSocket 规范限制）。
    建连后，双向透传学生容器的 docker exec 会话。

    root=1：以容器 root 用户（uid=0）执行，仅限 is_shadow=True 的 Shadow 学生（Dry Run 模式）。
    """
    client = f"{websocket.client.host}:{websocket.client.port}" if websocket.client else "unknown"
    use_root = root == "1"

    # ── 1. 验证 Token / 角色 / 频控 ─────────────────────────────────
    payload = verify_token(token)
    if not payload:
        logger.warning(f"[Terminal] 拒绝连接: token 无效, client={client}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    student_id = payload.get("user_id")
    role = payload.get("role")
    is_shadow = bool(payload.get("is_shadow", False))

    if not student_id or role != "student":
        logger.warning(
            f"[Terminal] 拒绝连接: 非学生或缺少 user_id, role={role}, user_id={student_id}, client={client}"
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # root 模式仅限 Shadow 学生（Dry Run）
    if use_root and not is_shadow:
        logger.warning(f"[Terminal] 拒绝 root 模式: 非 Shadow 学生, student={student_id}, client={client}")
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
        student = await crud_student.get_student(db, student_id)

    terminal_username = (
        student.username if student and getattr(student, "username", None) else "student"
    )
    safe_terminal_username = "".join(
        ch for ch in terminal_username if ch.isalnum() or ch in {"-", "_", "."}
    ) or "student"

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

    # ── 3. 终端前置权限修复（避免 /home/student 因历史 owner 导致 Permission denied）
    try:
        await _ensure_student_dir_permissions(container_id)
    except Exception as e:
        logger.error(
            f"[Terminal] 权限预修复失败: student={student_id}, container={container_id[:12]}, "
            f"client={client}, error={e}"
        )
        await websocket.accept()
        await websocket.send_text(
            "\r\n[错误] 初始化实验目录权限失败，请稍后重试或联系管理员。\r\n"
        )
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return

    # ── 4. 接受 WebSocket 连接 ────────────────────────────────────
    await websocket.accept()
    session_start = asyncio.get_running_loop().time()
    logger.info(
        f"[Terminal] 会话开始: student={student_id}, container={container_id[:12]}, client={client}"
    )

    # ── 5. 启动 docker exec ──────────────────────────────────────
    import shlex
    safe_container_id = shlex.quote(container_id)
    proc: Optional[asyncio.subprocess.Process] = None

    if use_root:
        # Root 模式（仅 Shadow 学生/Dry Run）：uid=0，工作目录 /
        exec_user = "0"
        exec_workdir = "/"
        exec_home = "/root"
        exec_ps1_user = "root"
    else:
        # 普通模式：uid=1000（student 用户）
        exec_user = "1000"
        exec_workdir = "/home/student"
        exec_home = "/home/student"
        exec_ps1_user = safe_terminal_username

    try:
        proc = await asyncio.create_subprocess_exec(
            "script",
            "-qc",
            f"docker exec -it -u {exec_user} -w {exec_workdir} "
            f"-e TERM=xterm -e USER={exec_ps1_user} -e LOGNAME={exec_ps1_user} "
            f"-e HOME={exec_home} "
            f"{safe_container_id} /bin/bash -lc \""
            f"source /opt/ros/noetic/setup.bash && "
            f"source /home/ubuntu20/catkin_ws/devel/setup.bash && "
            f"export PS1='{exec_ps1_user}@\\h: \\w\\$ ' && "
            f"exec /bin/bash --noprofile --norc -i"
            f"\"",
            "/dev/null",
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

    # ── 6. 双向透传 ──────────────────────────────────────────────
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
    # 注意：不能简单 FIRST_COMPLETED 后直接杀进程。
    # 在部分场景（如 catkin_make 长输出）read_task 可能先异常/暂时结束，
    # 若此时容器内 shell 仍存活，直接 kill 会导致“执行中途断连”。
    read_task = asyncio.create_task(read_from_docker())
    write_task = asyncio.create_task(write_to_docker())

    while True:
        done, pending = await asyncio.wait(
            [read_task, write_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # 客户端侧断开或写入协程结束：结束会话
        if write_task in done:
            break

        # 输出协程结束：如果进程还活着，重建 read_task 继续透传
        if read_task in done:
            if proc.returncode is None and websocket.client_state == WebSocketState.CONNECTED:
                read_task = asyncio.create_task(read_from_docker())
                continue
            break

    # 清理
    for task in (read_task, write_task):
        if not task.done():
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
