"""
Dry Run 专用工具 API

提供仅对 Shadow 学生（Dry Run 模式）可用的诊断工具：
- GET /docker-logs       — 获取容器最近 N 行日志
- GET /failure-review    — 获取容器状态与任务失败信息

认证：Shadow 学生 JWT（is_shadow=True），由前端通过 sessionStorage 持有。
"""
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user_id, verify_token
from app.crud import container as crud_container
from app.crud.shadow_student import is_shadow_user
from app.crud.simulation_task import get_active_task_by_student
from app.db.database import get_db
from app.schemas.common import ApiResponse

router = APIRouter()
logger = logging.getLogger(__name__)


async def _get_shadow_container(db: AsyncSession, user_id: int):
    """验证当前用户为 Shadow 学生并返回其容器，否则抛 HTTPException。"""
    if not await is_shadow_user(db, user_id):
        raise HTTPException(status_code=403, detail="仅 Dry Run 模式可用")
    container = await crud_container.get_container_by_user(db, user_id)
    if not container or not container.container_id:
        raise HTTPException(status_code=404, detail="未找到 Dry Run 容器")
    return container


@router.get(
    "/docker-logs",
    response_model=ApiResponse[dict],
    summary="获取 Dry Run 容器最近 N 行日志",
)
async def get_docker_logs(
    lines: int = Query(default=500, ge=1, le=2000, description="获取最近 N 行日志"),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    获取当前 Shadow 学生容器的 docker logs 输出。
    仅限 Dry Run 模式（is_shadow=True 的用户）调用。
    """
    container = await _get_shadow_container(db, user_id)

    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "logs", "--tail", str(lines), container.container_id,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        logs = stdout.decode("utf-8", errors="replace")
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="获取日志超时")
    except Exception as e:
        logger.warning("[dry_run_tools] docker logs 失败: %s", e)
        raise HTTPException(status_code=500, detail=f"获取日志失败: {e}")

    return ApiResponse(data={"logs": logs, "lines_requested": lines})


@router.get(
    "/failure-review",
    response_model=ApiResponse[dict],
    summary="获取 Dry Run 容器状态与失败信息",
)
async def get_failure_review(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    获取当前 Shadow 学生容器的诊断信息：
    - 容器 status、error_message
    - 最近一次 SimulationTask 的各阶段状态
    """
    container = await _get_shadow_container(db, user_id)

    task = await get_active_task_by_student(db, user_id)

    return ApiResponse(data={
        "container": {
            "container_id": container.container_id,
            "status": container.status.value,
            "error_message": container.error_message,
            "gzbridge_port": container.gzbridge_port,
            "rosbridge_port": container.rosbridge_port,
        },
        "task": {
            "task_id": task.task_id if task else None,
            "status": task.status.value if task else None,
            "current_stage": task.current_stage.value if task else None,
            "stage_statuses": task.stage_statuses if task else [],
            "error_code": task.error_code if task else None,
            "error_message": task.error_message if task else None,
            "elapsed_ms": task.elapsed_ms if task else None,
        } if task else None,
    })
