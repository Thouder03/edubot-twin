"""
容器内文件操作 API（ROOT 模式，仅 Shadow 学生/Dry Run 可用）

通过 docker exec 在容器内执行文件操作，可访问容器全部文件系统。

端点前缀：/api/v1/teachers/dry-run-tools/files
认证：Shadow 学生 JWT（is_shadow=True）
"""
import asyncio
import logging
import shlex
import stat
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user_id
from app.crud import container as crud_container
from app.crud.shadow_student import is_shadow_user
from app.db.database import get_db
from app.schemas.common import ApiResponse

router = APIRouter()
logger = logging.getLogger(__name__)

# 禁止操作的危险路径（防止删除系统关键目录）
BLOCKED_DELETE_PATHS = {"/", "/bin", "/sbin", "/usr", "/lib", "/lib64", "/etc", "/proc", "/sys", "/dev", "/boot"}


async def _get_shadow_container_id(db: AsyncSession, user_id: int) -> str:
    """验证为 Shadow 学生并返回容器 ID，否则抛 HTTPException。"""
    if not await is_shadow_user(db, user_id):
        raise HTTPException(status_code=403, detail="仅 Dry Run 模式可用")
    container = await crud_container.get_container_by_user(db, user_id)
    if not container or not container.container_id:
        raise HTTPException(status_code=404, detail="未找到 Dry Run 容器")
    return container.container_id


async def _docker_exec(container_id: str, cmd: list[str], stdin: Optional[bytes] = None, timeout: float = 10.0) -> tuple[str, int]:
    """在容器内执行命令，返回 (stdout+stderr, returncode)。"""
    full_cmd = ["docker", "exec"]
    if stdin is not None:
        full_cmd.append("-i")
    full_cmd.append(container_id)
    full_cmd.extend(cmd)

    try:
        proc = await asyncio.create_subprocess_exec(
            *full_cmd,
            stdin=asyncio.subprocess.PIPE if stdin is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(
            proc.communicate(input=stdin),
            timeout=timeout,
        )
        return stdout.decode("utf-8", errors="replace"), proc.returncode or 0
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="操作超时")
    except Exception as e:
        logger.warning("[container_files] docker exec 失败: %s", e)
        raise HTTPException(status_code=500, detail=f"操作失败: {e}")


@router.get("/list", response_model=ApiResponse[dict], summary="列出容器内目录")
async def list_files(
    path: str = Query(default="/", description="容器内路径"),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    container_id = await _get_shadow_container_id(db, user_id)
    safe_path = shlex.quote(path)
    output, rc = await _docker_exec(container_id, ["ls", "-la", "--time-style=+%s", safe_path])
    if rc != 0:
        raise HTTPException(status_code=400, detail=output.strip())

    items = []
    for line in output.splitlines():
        parts = line.split(None, 8)
        if len(parts) < 9 or line.startswith("total"):
            continue
        perms, _, _, _, size_str, _, _, mtime_str, name = parts
        is_dir = perms.startswith("d")
        items.append({
            "name": name,
            "is_dir": is_dir,
            "size": int(size_str) if size_str.isdigit() else 0,
            "modified_at": int(mtime_str) if mtime_str.isdigit() else 0,
            "permissions": perms,
        })

    return ApiResponse(data={"path": path, "items": items})


@router.get("/read", response_model=ApiResponse[dict], summary="读取容器内文件内容")
async def read_file(
    path: str = Query(..., description="容器内文件路径"),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    container_id = await _get_shadow_container_id(db, user_id)
    safe_path = shlex.quote(path)

    # 先检查文件大小
    size_out, _ = await _docker_exec(container_id, ["stat", "-c", "%s", safe_path])
    size = int(size_out.strip()) if size_out.strip().isdigit() else 0
    if size > 1 * 1024 * 1024:  # 1MB 限制
        raise HTTPException(status_code=413, detail="文件过大（超过 1MB）")

    content, rc = await _docker_exec(container_id, ["cat", safe_path])
    if rc != 0:
        raise HTTPException(status_code=400, detail=content.strip())

    return ApiResponse(data={"path": path, "content": content})


class FileWriteRequest(BaseModel):
    path: str
    content: str


@router.post("/write", response_model=ApiResponse[dict], summary="写入容器内文件")
async def write_file(
    data: FileWriteRequest,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    container_id = await _get_shadow_container_id(db, user_id)
    safe_path = shlex.quote(data.path)
    content_bytes = data.content.encode("utf-8")

    _, rc = await _docker_exec(
        container_id,
        ["sh", "-c", f"cat > {safe_path}"],
        stdin=content_bytes,
    )
    if rc != 0:
        raise HTTPException(status_code=400, detail="写入失败")

    return ApiResponse(data={"path": data.path, "ok": True})


class MkdirRequest(BaseModel):
    path: str


@router.post("/mkdir", response_model=ApiResponse[dict], summary="在容器内创建目录")
async def mkdir(
    data: MkdirRequest,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    container_id = await _get_shadow_container_id(db, user_id)
    safe_path = shlex.quote(data.path)
    _, rc = await _docker_exec(container_id, ["mkdir", "-p", safe_path])
    if rc != 0:
        raise HTTPException(status_code=400, detail="创建目录失败")
    return ApiResponse(data={"path": data.path, "ok": True})


@router.delete("/delete", response_model=ApiResponse[dict], summary="删除容器内文件或目录")
async def delete_file(
    path: str = Query(..., description="容器内路径"),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    # 阻止删除系统关键路径
    normalized = path.rstrip("/") or "/"
    if normalized in BLOCKED_DELETE_PATHS:
        raise HTTPException(status_code=403, detail=f"禁止删除系统路径: {path}")

    container_id = await _get_shadow_container_id(db, user_id)
    safe_path = shlex.quote(path)
    _, rc = await _docker_exec(container_id, ["rm", "-rf", safe_path])
    if rc != 0:
        raise HTTPException(status_code=400, detail="删除失败")

    return ApiResponse(data={"path": path, "ok": True})
