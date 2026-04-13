"""
学生 workspace 代码快照工具（第12期 S3）

与第11期教师资源冻结复制（exam_env_snapshot/exam_file_snapshot）不同：
本工具仅面向学生实时 workspace 的只读副本，供 Sidecar 挂载使用。

安全约束（SDD §9）：
- 单 attempt 快照上限 100MB
- 快照目录权限 700（只有后端进程可读）
"""

import logging
import os
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 快照存储根目录
SUBMISSIONS_ROOT = Path("/data/exam_submissions")

# 单快照大小上限（字节）
MAX_SNAPSHOT_BYTES = 100 * 1024 * 1024  # 100MB


class SnapshotError(Exception):
    """代码快照失败"""
    def __init__(self, message: str, error_code: str = "SNAPSHOT_FAILED"):
        super().__init__(message)
        self.error_code = error_code


def _get_submission_path(attempt_id: int) -> Path:
    """返回 attempt 对应的快照目录路径"""
    return SUBMISSIONS_ROOT / str(attempt_id)


def _get_artifacts_path(attempt_id: int) -> Path:
    """返回 attempt 对应的 artifacts 目录路径"""
    artifacts_root = Path("/data/exam_artifacts")
    return artifacts_root / str(attempt_id)


def _calculate_dir_size(path: Path) -> int:
    """递归计算目录总大小（字节）"""
    total = 0
    for entry in os.scandir(path):
        if entry.is_file(follow_symlinks=False):
            total += entry.stat().st_size
        elif entry.is_dir(follow_symlinks=False):
            total += _calculate_dir_size(Path(entry.path))
    return total


def _find_workspace_path(student_id: int) -> Optional[Path]:
    """
    定位学生 workspace 目录。

    约定路径（与 container_manager.py 一致）：
    data/students/{student_id}/workspace
    """
    workspace = Path("data/students") / str(student_id) / "workspace"
    workspace = workspace.resolve()
    if workspace.exists() and workspace.is_dir():
        return workspace
    return None


class SnapshotResult:
    """快照操作结果"""
    def __init__(
        self,
        snapshot_path: str,
        artifacts_path: str,
        file_count: int,
        total_bytes: int,
    ):
        self.snapshot_path = snapshot_path
        self.artifacts_path = artifacts_path
        self.file_count = file_count
        self.total_bytes = total_bytes


def create_code_snapshot(attempt_id: int, student_id: int) -> SnapshotResult:
    """
    复制学生 workspace 到快照目录。

    同步执行（由调用方包装到 asyncio executor 中），
    避免大文件 I/O 阻塞事件循环。

    Args:
        attempt_id: 考试尝试 ID（用于目录名）
        student_id: 学生 ID（用于定位 workspace）

    Returns:
        SnapshotResult

    Raises:
        SnapshotError: 快照失败（源目录不存在/大小超限/IO 错误）
    """
    workspace = _find_workspace_path(student_id)
    if workspace is None:
        raise SnapshotError(
            f"学生 {student_id} 的 workspace 目录不存在",
            error_code="SNAPSHOT_FAILED",
        )

    # 预检大小
    try:
        total_bytes = _calculate_dir_size(workspace)
    except OSError as e:
        raise SnapshotError(f"计算 workspace 大小失败: {e}") from e

    if total_bytes > MAX_SNAPSHOT_BYTES:
        raise SnapshotError(
            f"workspace 超过快照上限（{total_bytes} > {MAX_SNAPSHOT_BYTES} bytes）",
            error_code="SNAPSHOT_FAILED",
        )

    # 创建目标目录
    target = _get_submission_path(attempt_id)
    try:
        target.mkdir(parents=True, exist_ok=True)
        target.chmod(0o700)
    except OSError as e:
        raise SnapshotError(f"创建快照目录失败: {e}") from e

    # 复制目录
    target_content = target / "workspace"
    try:
        shutil.copytree(
            str(workspace),
            str(target_content),
            dirs_exist_ok=False,
            ignore=shutil.ignore_patterns("*.pyc", "__pycache__", ".git"),
        )
    except OSError as e:
        # 清理不完整的快照
        try:
            shutil.rmtree(str(target), ignore_errors=True)
        except Exception:
            pass
        raise SnapshotError(f"workspace 复制失败: {e}") from e

    # 统计文件数
    file_count = sum(1 for _ in target_content.rglob("*") if _.is_file())

    # 创建 artifacts 目录
    artifacts = _get_artifacts_path(attempt_id)
    try:
        artifacts.mkdir(parents=True, exist_ok=True)
        artifacts.chmod(0o700)
    except OSError as e:
        logger.warning(f"创建 artifacts 目录失败（非致命）: {e}")

    logger.info(
        f"[快照] attempt={attempt_id} 学生={student_id} "
        f"文件数={file_count} 大小={total_bytes}B "
        f"快照路径={target_content}"
    )

    return SnapshotResult(
        snapshot_path=str(target_content),
        artifacts_path=str(artifacts),
        file_count=file_count,
        total_bytes=total_bytes,
    )


def cleanup_snapshot(attempt_id: int) -> None:
    """
    清理快照目录（不清理 artifacts，artifacts 需长期保留）。
    仅在测试/错误清理时使用，正常流程保留快照供审计。
    """
    target = _get_submission_path(attempt_id)
    if target.exists():
        try:
            shutil.rmtree(str(target))
            logger.info(f"[快照清理] attempt={attempt_id} 快照目录已删除")
        except OSError as e:
            logger.warning(f"[快照清理] attempt={attempt_id} 失败: {e}")
