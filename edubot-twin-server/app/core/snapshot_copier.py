"""
快照复制工具函数（第11期 S11）

封装 shutil.copytree + 事务回滚逻辑：
- 复制成功 → 返回 (file_count, total_size_bytes)
- 复制失败 → 清理不完整目录 + 抛出异常供上层回滚 DB 记录
"""
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


class SnapshotCopyError(Exception):
    """快照复制失败异常"""
    def __init__(self, source: str, target: str, reason: str):
        self.source = source
        self.target = target
        self.reason = reason
        super().__init__(f"快照复制失败: {source} → {target}: {reason}")


def copy_snapshot(
    source_dir: str,
    target_dir: str,
) -> tuple[int, int]:
    """
    物理复制目录到目标位置。

    :param source_dir: 源目录绝对路径
    :param target_dir: 目标目录绝对路径（必须不存在）
    :returns: (file_count, total_size_bytes)
    :raises SnapshotCopyError: 复制失败时（目标目录已清理）
    """
    source_path = Path(source_dir)
    target_path = Path(target_dir)

    if not source_path.exists():
        raise SnapshotCopyError(source_dir, target_dir, "源目录不存在")

    if not source_path.is_dir():
        raise SnapshotCopyError(source_dir, target_dir, "源路径不是目录")

    try:
        # 确保父目录存在
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(str(source_path), str(target_path))
    except Exception as e:
        logger.error(
            "[snapshot_copy_failed] source=%s target=%s error=%s",
            source_dir, target_dir, str(e),
        )
        # 清理不完整的目标目录
        if target_path.exists():
            try:
                shutil.rmtree(str(target_path))
                logger.info("[snapshot_copy_cleanup] target=%s removed", target_dir)
            except Exception as cleanup_err:
                logger.error(
                    "[snapshot_copy_cleanup_failed] target=%s error=%s",
                    target_dir, str(cleanup_err),
                )
        raise SnapshotCopyError(source_dir, target_dir, str(e)) from e

    # 统计文件数和总大小
    file_count = 0
    total_size = 0
    for file_path in target_path.rglob("*"):
        if file_path.is_file():
            file_count += 1
            total_size += file_path.stat().st_size

    logger.info(
        "[snapshot_copy_done] source=%s target=%s files=%d size=%d",
        source_dir, target_dir, file_count, total_size,
    )
    return file_count, total_size
