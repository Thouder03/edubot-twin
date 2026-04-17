"""
学生 workspace 代码快照工具（第12期 S3 / 第14期 submission_paths 扩展）

与第11期教师资源冻结复制（exam_env_snapshot/exam_file_snapshot）不同：
本工具仅面向学生实时 workspace 的只读副本，供 Sidecar 挂载使用。

安全约束（SDD §9）：
- 单 attempt 快照上限 100MB
- 快照目录权限 750（所有者全权，同组可读）

submission_paths 字段（第14期新增）：
- 由 sidecar_policy_json.submission_paths 驱动
- 非空时只复制指定相对路径（文件/目录），留空则复制整个 workspace
"""

import logging
import os
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 快照存储根目录（与 crud/ 下各资源目录保持一致，使用相对路径 resolve）
SUBMISSIONS_ROOT = Path("data/exam_submissions").resolve()

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


def get_artifacts_path(attempt_id: int) -> Path:
    """返回 attempt 对应的 artifacts 目录路径"""
    artifacts_root = Path("data/exam_artifacts").resolve()
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


def _copy_one(src: Path, dst: Path, ignore) -> None:
    """复制单个文件或目录到目标路径（内部辅助）"""
    try:
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dst))
        elif src.is_dir():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(str(src), str(dst), dirs_exist_ok=True, ignore=ignore)
    except OSError as e:
        logger.warning(f"[快照] 复制 {src} 失败: {e}")


def _copy_selected_paths(
    workspace: Path,
    target_content: Path,
    submission_paths: list[str],
) -> None:
    """
    按 submission_paths 选择性复制 workspace 中的指定路径到 target_content。

    支持：
    - 精确路径（文件或目录）："catkin_ws/src/my_pkg"
    - 通配符（单层）："catkin_ws/src/*"
    - 通配符（递归）："catkin_ws/src/**/*.py"
    - 路径不存在 / glob 无匹配：跳过并记录 warning
    """
    target_content.mkdir(parents=True, exist_ok=True)
    _IGNORE = shutil.ignore_patterns("*.pyc", "__pycache__", ".git")

    for pattern in submission_paths:
        # 去除首尾空白和斜杠，保证 glob / Path 运算正确
        pattern = pattern.strip().strip("/").strip("\\")
        if not pattern:
            continue

        if "*" in pattern:
            # glob 模式：支持 * 和 ** 通配符
            matched = sorted(workspace.glob(pattern))
            if not matched:
                logger.warning(f"[快照] submission_paths glob 无匹配: {pattern}")
                continue
            for src in matched:
                # 只保留最后的文件/目录名，直接落在 target_content 根目录下
                # 避免把 "catkin_ws/src/*" 展开后仍嵌套在 catkin_ws/src/ 里
                _copy_one(src, target_content / src.name, _IGNORE)
        else:
            src = workspace / pattern
            if not src.exists():
                # 直接路径不存在时，在 workspace 内递归搜索同名文件/目录
                candidates = sorted(workspace.rglob(pattern))
                if not candidates:
                    logger.warning(f"[快照] submission_paths 中路径不存在且递归搜索无匹配，跳过: {pattern}")
                    continue
                if len(candidates) > 1:
                    logger.warning(
                        f"[快照] submission_paths '{pattern}' 递归搜索到 {len(candidates)} 个匹配，"
                        f"全部复制: {[str(c.relative_to(workspace)) for c in candidates]}"
                    )
                for src in candidates:
                    _copy_one(src, target_content / src.name, _IGNORE)
                continue
            # 只保留最后的文件/目录名，直接落在 target_content 根目录下
            # 例：submission_paths=["catkin_ws/src"] → target_content/src/
            #     而非 target_content/catkin_ws/src/（会把子文件埋得过深）
            _copy_one(src, target_content / src.name, _IGNORE)


def create_code_snapshot(
    attempt_id: int,
    student_id: int,
    submission_paths: Optional[list[str]] = None,
) -> SnapshotResult:
    """
    复制学生 workspace 到快照目录。

    同步执行（由调用方包装到 asyncio executor 中），
    避免大文件 I/O 阻塞事件循环。

    Args:
        attempt_id: 考试尝试 ID（用于目录名）
        student_id: 学生 ID（用于定位 workspace）
        submission_paths: 仅复制这些相对路径（文件/目录）；
                          为 None 或空列表时复制整个 workspace（默认行为）

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
        target.chmod(0o750)
    except OSError as e:
        raise SnapshotError(f"创建快照目录失败: {e}") from e

    target_content = target / "workspace"

    effective_paths = [p for p in (submission_paths or []) if p.strip()]

    try:
        if effective_paths:
            # 按指定路径选择性复制
            _copy_selected_paths(workspace, target_content, effective_paths)
        else:
            # 全量复制（默认行为）
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
    artifacts = get_artifacts_path(attempt_id)
    try:
        artifacts.mkdir(parents=True, exist_ok=True)
        artifacts.chmod(0o750)
    except OSError as e:
        logger.warning(f"创建 artifacts 目录失败（非致命）: {e}")

    mode = f"选择路径 {effective_paths}" if effective_paths else "全量"
    logger.info(
        f"[快照] attempt={attempt_id} 学生={student_id} "
        f"模式={mode} 文件数={file_count} 大小={total_bytes}B "
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
