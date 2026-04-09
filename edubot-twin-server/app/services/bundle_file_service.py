"""
BundleFileService — 统一文件包操作服务

适用于 ExperimentFileBundle（文件包）和 ExperimentEnvBundle（环境包）的文件操作。
统一处理：上传、列目录、读文件内容、保存内容、删除、新建目录、重命名、移动、
复制、解压、压缩、下载路径解析、路径安全校验、保护路径约束（如 startup.sh 不可删）、
冲突检测。
"""
import logging
import mimetypes
import os
import shutil
import tarfile
import zipfile
from pathlib import Path
from typing import Literal, Optional

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


class FileAlreadyExistsError(BundleFileError):
    """目标已存在"""
    def __init__(self, path: str):
        super().__init__("FILE_ALREADY_EXISTS", f"目标已存在: {path}", 409)


class InvalidOperationError(BundleFileError):
    """非法操作（参数错误 / 业务约束不满足）"""
    def __init__(self, message: str, code: str = "INVALID_OPERATION"):
        super().__init__(code, message, 400)


class UnsupportedArchiveError(BundleFileError):
    """不支持的压缩格式"""
    def __init__(self, message: str):
        super().__init__("UNSUPPORTED_ARCHIVE", message, 400)


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

    def save_uploaded_file(
        self,
        filename: str,
        file_data: bytes,
        target_dir: Optional[str] = None,
    ) -> Path:
        """
        保存上传的文件到指定子目录。压缩包不自动解压，直接保存。

        :param filename: 原始文件名
        :param file_data: 文件二进制内容
        :param target_dir: 目标相对目录（None 或 '.' 表示根目录）
        :returns: 保存后的绝对路径
        :raises FileSizeExceededError: 文件超过 200MB
        :raises PathTraversalError: 文件名或目录包含路径越界字符
        """
        if len(file_data) > MAX_UPLOAD_SIZE_BYTES:
            raise FileSizeExceededError(len(file_data))

        # 仅允许文件名（不允许带目录层级）
        safe_name = Path(filename).name
        if not safe_name:
            raise PathTraversalError(filename)

        # 解析目标目录
        if target_dir and target_dir != ".":
            dir_path = self._safe_path(target_dir)
            dir_path.mkdir(parents=True, exist_ok=True)
        else:
            dir_path = self.storage_root
            dir_path.mkdir(parents=True, exist_ok=True)

        target = dir_path / safe_name
        # 保证上传路径仍在 storage_root 内
        try:
            target.resolve().relative_to(self.storage_root)
        except ValueError:
            raise PathTraversalError(filename)

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

    # ─── 新建目录 ────────────────────────────────────────────────────────────────

    def mkdir(self, relative_path: str) -> Path:
        """
        在 storage_root 下创建目录（支持多级）。

        :param relative_path: 目录相对路径
        :raises FileAlreadyExistsError: 目录已存在
        :raises PathTraversalError: 路径越界
        """
        if not relative_path:
            raise InvalidOperationError("目录路径不能为空")
        target = self._safe_path(relative_path)
        if target.exists():
            raise FileAlreadyExistsError(relative_path)
        target.mkdir(parents=True, exist_ok=False)
        logger.info(f"目录已创建: {target}")
        return target

    # ─── 重命名 ──────────────────────────────────────────────────────────────────

    def rename(self, relative_path: str, new_name: str) -> Path:
        """
        重命名文件或目录。

        :param relative_path: 原相对路径
        :param new_name: 新名称（不含路径分隔符）
        :raises ProtectedPathError: 源路径受保护（如 startup.sh）
        :raises FileNotFoundError: 源不存在
        :raises FileAlreadyExistsError: 目标已存在
        :raises InvalidOperationError: new_name 含非法字符
        """
        if not new_name or "/" in new_name or "\\" in new_name:
            raise InvalidOperationError("新名称不能为空且不能包含路径分隔符")

        if self._is_protected(relative_path):
            raise ProtectedPathError(relative_path)

        source = self._safe_path(relative_path)
        if not source.exists():
            raise FileNotFoundError(relative_path)
        if source.resolve() == self.storage_root:
            raise InvalidOperationError("不允许重命名根目录")

        target = source.with_name(new_name)
        if target.exists():
            raise FileAlreadyExistsError(new_name)
        source.rename(target)
        logger.info(f"重命名: {source} -> {target}")
        return target

    # ─── 移动 ────────────────────────────────────────────────────────────────────

    def move(self, source_paths: list[str], target_dir: str) -> tuple[list[str], list[dict]]:
        """
        将多个文件/目录移动到目标目录。

        :param source_paths: 源相对路径列表
        :param target_dir: 目标目录相对路径（'.' 表示根）
        :returns: (success_rel_paths, failed_items)
        """
        if target_dir and target_dir != ".":
            dst_dir = self._safe_path(target_dir)
        else:
            dst_dir = self.storage_root

        if not dst_dir.exists() or not dst_dir.is_dir():
            raise InvalidOperationError(f"目标目录不存在或不是目录: {target_dir}")

        success: list[str] = []
        failed: list[dict] = []
        for path in source_paths:
            try:
                if self._is_protected(path):
                    failed.append({"path": path, "reason": "受保护文件不可移动"})
                    continue
                src = self._safe_path(path)
                if not src.exists():
                    failed.append({"path": path, "reason": "源不存在"})
                    continue
                # 禁止将目录移动到自身子目录
                if dst_dir.resolve() == src.resolve() or str(dst_dir.resolve()).startswith(
                    str(src.resolve()) + os.sep
                ):
                    failed.append({"path": path, "reason": "不能移动到自身或子目录"})
                    continue
                dst = dst_dir / src.name
                if dst.resolve() == src.resolve():
                    success.append(str(dst.relative_to(self.storage_root).as_posix()))
                    continue
                if dst.exists():
                    failed.append({"path": path, "reason": "目标目录已存在同名文件"})
                    continue
                shutil.move(str(src), str(dst))
                success.append(str(dst.relative_to(self.storage_root).as_posix()))
            except BundleFileError as e:
                failed.append({"path": path, "reason": e.message})
            except OSError as e:
                failed.append({"path": path, "reason": str(e)})
        return success, failed

    # ─── 复制 ────────────────────────────────────────────────────────────────────

    def copy(self, source_paths: list[str], target_dir: str) -> tuple[list[str], list[dict]]:
        """
        将多个文件/目录复制到目标目录（同名自动加 _copyN 后缀）。

        :param source_paths: 源相对路径列表
        :param target_dir: 目标目录相对路径（'.' 表示根）
        :returns: (success_rel_paths, failed_items)
        """
        if target_dir and target_dir != ".":
            dst_dir = self._safe_path(target_dir)
        else:
            dst_dir = self.storage_root

        if not dst_dir.exists() or not dst_dir.is_dir():
            raise InvalidOperationError(f"目标目录不存在或不是目录: {target_dir}")

        success: list[str] = []
        failed: list[dict] = []
        for path in source_paths:
            try:
                src = self._safe_path(path)
                if not src.exists():
                    failed.append({"path": path, "reason": "源不存在"})
                    continue
                # 目录复制到自己的子目录会无限递归
                if src.is_dir() and str(dst_dir.resolve()).startswith(
                    str(src.resolve()) + os.sep
                ):
                    failed.append({"path": path, "reason": "不能复制到自身的子目录"})
                    continue
                dst = dst_dir / src.name
                if dst.exists():
                    counter = 1
                    stem = src.stem
                    suffix = src.suffix
                    while dst.exists():
                        dst = dst_dir / f"{stem}_copy{counter}{suffix}"
                        counter += 1
                if src.is_dir():
                    shutil.copytree(str(src), str(dst))
                else:
                    shutil.copy2(str(src), str(dst))
                success.append(str(dst.relative_to(self.storage_root).as_posix()))
            except BundleFileError as e:
                failed.append({"path": path, "reason": e.message})
            except OSError as e:
                failed.append({"path": path, "reason": str(e)})
        return success, failed

    # ─── 解压 ────────────────────────────────────────────────────────────────────

    def extract(self, relative_path: str, target_dir: Optional[str] = None) -> Path:
        """
        解压压缩文件到指定目录（默认解压到压缩文件所在目录）。
        支持 .zip / .tar / .tar.gz / .tgz / .tar.bz2 / .tar.xz。

        :returns: 解压目标目录绝对路径
        """
        archive = self._safe_path(relative_path)
        if not archive.exists():
            raise FileNotFoundError(relative_path)
        if not archive.is_file():
            raise InvalidOperationError(f"路径不是文件: {relative_path}")

        name_lower = archive.name.lower()
        is_zip = name_lower.endswith(".zip")
        is_tar = (
            name_lower.endswith(".tar")
            or name_lower.endswith(".tar.gz")
            or name_lower.endswith(".tgz")
            or name_lower.endswith(".tar.bz2")
            or name_lower.endswith(".tar.xz")
        )
        if not is_zip and not is_tar:
            raise UnsupportedArchiveError(
                "仅支持 .zip / .tar / .tar.gz / .tgz / .tar.bz2 / .tar.xz"
            )

        if target_dir:
            dst = self._safe_path(target_dir)
        else:
            dst = archive.parent
        dst.mkdir(parents=True, exist_ok=True)
        dst_resolved = dst.resolve()

        try:
            if is_zip:
                with zipfile.ZipFile(archive, "r") as zf:
                    for member in zf.namelist():
                        member_path = (dst / member).resolve()
                        try:
                            member_path.relative_to(dst_resolved)
                        except ValueError:
                            raise InvalidOperationError(f"压缩包含危险路径: {member}")
                    zf.extractall(dst)
            else:
                with tarfile.open(archive, "r:*") as tf:
                    for member in tf.getmembers():
                        member_path = (dst / member.name).resolve()
                        try:
                            member_path.relative_to(dst_resolved)
                        except ValueError:
                            raise InvalidOperationError(f"压缩包含危险路径: {member.name}")
                    tf.extractall(dst)
        except (zipfile.BadZipFile, tarfile.TarError) as e:
            raise InvalidOperationError(f"解压失败：文件可能已损坏: {e}")
        logger.info(f"解压完成: {archive} -> {dst}")
        return dst

    # ─── 压缩 ────────────────────────────────────────────────────────────────────

    def compress(
        self,
        paths: list[str],
        archive_name: str,
        format: Literal["zip", "tar.gz"] = "zip",
        target_dir: Optional[str] = None,
    ) -> Path:
        """
        将多个文件/目录压缩为 zip 或 tar.gz 归档。

        :param paths: 源相对路径列表
        :param archive_name: 输出压缩包文件名（含扩展名）
        :param format: 压缩格式
        :param target_dir: 输出目录（默认第一个源路径的父目录）
        :returns: 压缩包绝对路径
        """
        if not paths:
            raise InvalidOperationError("至少需要一个源路径")
        if "/" in archive_name or "\\" in archive_name:
            raise InvalidOperationError("压缩包名称不能包含路径分隔符")

        sources: list[Path] = []
        for p in paths:
            src = self._safe_path(p)
            if not src.exists():
                raise FileNotFoundError(p)
            sources.append(src)

        if target_dir:
            out_dir = self._safe_path(target_dir)
        else:
            out_dir = sources[0].parent
        out_dir.mkdir(parents=True, exist_ok=True)

        out_path = out_dir / archive_name
        # 保证输出路径仍在 storage_root 内
        try:
            out_path.resolve().relative_to(self.storage_root)
        except ValueError:
            raise PathTraversalError(archive_name)

        if out_path.exists():
            raise FileAlreadyExistsError(archive_name)

        try:
            if format == "zip":
                with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                    for src in sources:
                        if src.is_file():
                            zf.write(src, src.name)
                        elif src.is_dir():
                            for file in src.rglob("*"):
                                if file.is_file():
                                    zf.write(
                                        file,
                                        src.name + "/" + str(file.relative_to(src)),
                                    )
            else:  # tar.gz
                with tarfile.open(out_path, "w:gz") as tf:
                    for src in sources:
                        tf.add(src, arcname=src.name)
        except OSError as e:
            raise InvalidOperationError(f"压缩失败: {e}")

        logger.info(f"压缩完成: {out_path}")
        return out_path

    # ─── 下载路径解析 ────────────────────────────────────────────────────────────

    def resolve_for_download(self, relative_path: str) -> Path:
        """
        解析下载目标的绝对路径（由 endpoint 负责流式返回）。
        """
        target = self._safe_path(relative_path)
        if not target.exists():
            raise FileNotFoundError(relative_path)
        return target

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
