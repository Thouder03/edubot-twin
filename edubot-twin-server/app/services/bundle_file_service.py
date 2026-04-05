"""
BundleFileService — 统一文件包操作服务

适用于 ExperimentFileBundle（文件包）和 ExperimentEnvBundle（环境包）的文件操作。
统一处理：上传、列目录、读文件内容、保存内容、删除、路径安全校验、
保护路径约束（如 startup.sh 不可删）、冲突检测。
"""
import logging
import mimetypes
import os
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 允许的最大上传文件大小：200MB
MAX_UPLOAD_SIZE_BYTES = 200 * 1024 * 1024


class BundleFileError(Exception):
    """文件操作基础异常"""
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class PathTraversalError(BundleFileError):
    """路径穿越攻击"""
    def __init__(self, path: str):
        super().__init__("PATH_TRAVERSAL", f"路径不安全: {path}", 400)


class ProtectedPathError(BundleFileError):
    """受保护文件不可删除"""
    def __init__(self, path: str):
        super().__init__("STARTUP_SCRIPT_PROTECTED", f"该文件受保护，不可删除: {path}", 403)


class FileSizeExceededError(BundleFileError):
    """文件超过大小限制"""
    def __init__(self, size: int):
        super().__init__("UPLOAD_SIZE_EXCEEDED", f"上传文件超过 200MB 限制: {size} bytes", 413)


class FileNotFoundError(BundleFileError):
    """文件不存在"""
    def __init__(self, path: str):
        super().__init__("FILE_NOT_FOUND", f"文件不存在: {path}", 404)


class FileConflictError(BundleFileError):
    """保存时文件已被其他操作更新"""
    def __init__(self, path: str):
        super().__init__("FILE_SAVE_CONFLICT", f"文件已被其他操作更新，请刷新后重试: {path}", 409)


class BundleFileService:
    """
    统一文件包操作服务

    :param storage_root: 文件存储根目录（如 /data/file_bundles/1 或 /data/env_bundles/2）
    :param protected_paths: 受保护的文件路径集合（相对路径，如 {"startup.sh"}），这些文件不可删除
    """

    def __init__(self, storage_root: str, protected_paths: Optional[set[str]] = None):
        self.storage_root = Path(storage_root).resolve()
        self.protected_paths = protected_paths or set()

    def _safe_path(self, relative_path: str) -> Path:
        """
        解析相对路径为绝对路径，校验路径不越出 storage_root。

        :param relative_path: 用户提供的相对路径（如 'src/nav.py' 或 'startup.sh'）
        :raises PathTraversalError: 路径越界时抛出
        """
        if ".." in relative_path or relative_path.startswith("/"):
            raise PathTraversalError(relative_path)
        target = (self.storage_root / relative_path).resolve()
        # 确保目标在 storage_root 内
        try:
            target.relative_to(self.storage_root)
        except ValueError:
            raise PathTraversalError(relative_path)
        return target

    def _is_protected(self, relative_path: str) -> bool:
        """检查文件是否受保护（规范化路径后比对）"""
        normalized = Path(relative_path).as_posix()
        return normalized in self.protected_paths

    # ─── 列目录 ─────────────────────────────────────────────────────────────────

    def list_files(self, path: str = "") -> list[dict]:
        """
        列出指定目录下的文件和子目录

        :param path: 相对路径（空字符串表示根目录）
        :returns: [{name, type, size?, modified_at}]
        """
        if path:
            directory = self._safe_path(path)
        else:
            directory = self.storage_root

        if not directory.exists():
            return []

        items = []
        for entry in sorted(directory.iterdir(), key=lambda x: (x.is_file(), x.name)):
            stat = entry.stat()
            item: dict = {
                "name": entry.name,
                "type": "file" if entry.is_file() else "dir",
                "modified_at": stat.st_mtime,
            }
            if entry.is_file():
                item["size"] = stat.st_size
            items.append(item)
        return items

    # ─── 读文件内容 ──────────────────────────────────────────────────────────────

    def read_file(self, relative_path: str) -> tuple[str, str]:
        """
        读取文件文本内容

        :param relative_path: 文件相对路径
        :returns: (content, encoding)
        :raises FileNotFoundError: 文件不存在
        """
        target = self._safe_path(relative_path)
        if not target.exists() or not target.is_file():
            raise FileNotFoundError(relative_path)
        try:
            content = target.read_text(encoding="utf-8")
            encoding = "utf-8"
        except UnicodeDecodeError:
            content = target.read_text(encoding="latin-1")
            encoding = "latin-1"
        return content, encoding

    # ─── 保存文件内容 ────────────────────────────────────────────────────────────

    def save_file(self, relative_path: str, content: str, modified_at: Optional[float] = None) -> float:
        """
        保存文件内容（可选冲突检测）

        :param relative_path: 文件相对路径
        :param content: 文件内容
        :param modified_at: 客户端持有的文件修改时间戳（用于冲突检测，None 则跳过）
        :returns: 保存后的新 mtime
        :raises FileConflictError: 检测到第三方已更新时
        :raises PathTraversalError: 路径越界
        """
        target = self._safe_path(relative_path)

        # 冲突检测：如果文件已存在且 mtime 不匹配，说明有并发写入
        if modified_at is not None and target.exists():
            current_mtime = target.stat().st_mtime
            if abs(current_mtime - modified_at) > 1.0:  # 容忍1秒误差
                raise FileConflictError(relative_path)

        # 确保父目录存在
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target.stat().st_mtime

    # ─── 上传文件 ────────────────────────────────────────────────────────────────

    def save_uploaded_file(self, filename: str, file_data: bytes) -> Path:
        """
        保存上传的文件到 storage_root。压缩包不自动解压，直接保存。

        :param filename: 原始文件名
        :param file_data: 文件二进制内容
        :returns: 保存后的绝对路径
        :raises FileSizeExceededError: 文件超过 200MB
        :raises PathTraversalError: 文件名包含路径越界字符
        """
        if len(file_data) > MAX_UPLOAD_SIZE_BYTES:
            raise FileSizeExceededError(len(file_data))

        # 仅允许文件名（不允许带目录层级）
        safe_name = Path(filename).name
        if not safe_name or safe_name != filename.lstrip("/"):
            # 如果带了路径，取最后一个部分
            safe_name = Path(filename).name

        target = self.storage_root / safe_name
        self.storage_root.mkdir(parents=True, exist_ok=True)
        target.write_bytes(file_data)
        logger.info(f"文件已保存: {target} ({len(file_data)} bytes)")
        return target

    # ─── 删除文件 ────────────────────────────────────────────────────────────────

    def delete_file(self, relative_path: str) -> None:
        """
        删除文件或目录

        :param relative_path: 相对路径
        :raises ProtectedPathError: 尝试删除受保护文件（如 startup.sh）
        :raises FileNotFoundError: 文件不存在
        """
        if self._is_protected(relative_path):
            raise ProtectedPathError(relative_path)

        target = self._safe_path(relative_path)
        if not target.exists():
            raise FileNotFoundError(relative_path)

        if target.is_file():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target)
        logger.info(f"文件已删除: {target}")

    # ─── 目录统计 ────────────────────────────────────────────────────────────────

    def scan_directory(self) -> tuple[int, int, list[dict]]:
        """
        扫描 storage_root，统计文件数量、总大小，并重建 file_manifest。

        :returns: (file_count, total_size_bytes, file_manifest)
                  file_manifest 格式: [{relative_path, chmod_mode}]
        """
        file_count = 0
        total_size = 0
        manifest = []

        if not self.storage_root.exists():
            return 0, 0, []

        for file_path in sorted(self.storage_root.rglob("*")):
            if file_path.is_file():
                file_count += 1
                size = file_path.stat().st_size
                total_size += size
                relative = file_path.relative_to(self.storage_root).as_posix()
                manifest.append({
                    "relative_path": relative,
                    "chmod_mode": "0644",
                })

        return file_count, total_size, manifest

    def get_file_info_list(self, path: str = "") -> list[dict]:
        """列目录，返回包含完整路径信息的列表（用于 API 响应）"""
        return self.list_files(path)
