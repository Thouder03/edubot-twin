"""
学生文件管理 API

提供学生工作区内的文件增删改查能力：
- POST  /files/upload   文件上传（multipart/form-data）
- GET   /files/list     列出文件和目录
- GET   /files/read     读取文件内容
- POST  /files/save     保存文件内容
- DELETE /files/delete  删除文件或目录
- POST  /files/mkdir    创建目录

安全机制：
- 路径穿越防护（validate_path）
- 单文件 10MB 限制
- 学生工作区总配额 100MB
"""

import os
import io
import shutil
import tempfile
import zipfile
import tarfile
from pathlib import Path
from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.schemas.common import ApiResponse

from app.core.security import get_current_student_id

router = APIRouter()

# ─── 常量 ───────────────────────────────────────────────────────────────────

STUDENTS_DATA_DIR = Path("data/students").resolve()
MAX_FILE_SIZE = 10 * 1024 * 1024       # 10 MB
MAX_TOTAL_SIZE = 100 * 1024 * 1024     # 100 MB


# ─── 工具函数 ───────────────────────────────────────────────────────────────

def get_workspace(student_id: int) -> Path:
    """返回学生工作区根目录"""
    return STUDENTS_DATA_DIR / str(student_id) / "workspace"


def validate_path(workspace: Path, user_path: str) -> Path:
    """
    安全路径验证，防止路径穿越攻击。

    Args:
        workspace: 工作区根目录的绝对路径
        user_path: 用户传入的相对路径

    Returns:
        合法的绝对路径

    Raises:
        HTTPException(400): 路径不合法
        HTTPException(403): 路径超出工作区
    """
    if not user_path:
        return workspace

    # 禁止绝对路径
    if user_path.startswith("/"):
        raise HTTPException(status_code=400, detail="不允许使用绝对路径")

    # 禁止 .. 符号
    if ".." in user_path.split("/"):
        raise HTTPException(status_code=400, detail="路径不能包含 ..")

    # 解析为绝对路径
    full_path = (workspace / user_path).resolve()

    # 验证是否在工作区内
    try:
        full_path.relative_to(workspace.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="路径超出工作区范围")

    return full_path


def get_dir_size(path: Path) -> int:
    """递归计算目录总大小（字节）"""
    total = 0
    if path.exists():
        for entry in path.rglob("*"):
            if entry.is_file():
                try:
                    total += entry.stat().st_size
                except OSError:
                    pass
    return total


def check_disk_quota(student_id: int, new_file_size: int = 0) -> None:
    """
    检查学生磁盘配额。

    Raises:
        HTTPException(413): 存储空间不足
    """
    workspace = get_workspace(student_id)
    current_size = get_dir_size(workspace)
    if current_size + new_file_size > MAX_TOTAL_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"存储空间不足（已用 {current_size // 1024 // 1024}MB / 100MB 总配额）"
        )


def detect_encoding(content: bytes) -> str:
    """简单编码检测：先尝试 UTF-8，失败则 GBK"""
    try:
        content.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "gbk"


# ─── Pydantic 请求/响应模型 ─────────────────────────────────────────────────

class FileSaveRequest(BaseModel):
    path: str
    content: str
    encoding: str = "utf-8"


class MkdirRequest(BaseModel):
    path: str

class FileRenameRequest(BaseModel):
    path: str
    new_name: str

class FileMoveRequest(BaseModel):
    source_paths: list[str]
    target_dir: str

class FileCopyRequest(BaseModel):
    source_paths: list[str]
    target_dir: str

class BatchDeleteRequest(BaseModel):
    paths: list[str]

class ExtractRequest(BaseModel):
    path: str           # 压缩文件的相对路径
    target_dir: Optional[str] = None  # 解压目标目录，默认为压缩文件所在目录

class CompressRequest(BaseModel):
    paths: list[str]                     # 要压缩的文件/目录相对路径列表
    archive_name: str                    # 输出压缩包文件名（含扩展名）
    format: Literal['zip', 'tar.gz'] = 'zip'  # 压缩格式
    target_dir: Optional[str] = None     # 输出目录，默认为第一个路径的父目录

# 支持的压缩格式
SUPPORTED_ARCHIVES = {".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz"}

# ─── API 端点 ───────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    target_path: Optional[str] = Form(default="."),
    student_id: int = Depends(get_current_student_id),
):
    """
    上传文件到工作区

    - target_path: 相对于 workspace 的目标目录，默认为根目录
    """
    workspace = get_workspace(student_id)

    # 读取文件内容并检查大小
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="文件过大（单文件上限 10MB）")

    # 检查磁盘配额
    check_disk_quota(student_id, len(content))

    # 解析目标目录
    if target_path in (".", "", None):
        target_dir = workspace
    else:
        target_dir = validate_path(workspace, target_path)

    # 创建目标目录（如不存在）
    target_dir.mkdir(parents=True, exist_ok=True)

    # 写入文件
    file_path = target_dir / file.filename
    try:
        file_path.write_bytes(content)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"写入失败: {e}")

    # 计算相对路径
    relative_path = str(file_path.relative_to(workspace))

    return ApiResponse(
        code=0,
        message="上传成功",
        data={
            "filename": file.filename,
            "path": relative_path,
            "size": len(content),
        }
    )


@router.get("/list")
async def list_files(
    path: str = Query(default=".", description="相对路径，默认为工作区根目录"),
    student_id: int = Depends(get_current_student_id),
):
    """
    列出指定目录下的文件和子目录
    """
    workspace = get_workspace(student_id)

    # 工作区不存在时返回空
    if not workspace.exists():
        return ApiResponse(code=0, data={"files": [], "directories": [], "path": path})

    target_dir = validate_path(workspace, path)

    if not target_dir.exists():
        raise HTTPException(status_code=404, detail="目录不存在")
    if not target_dir.is_dir():
        raise HTTPException(status_code=400, detail="路径不是目录")

    files = []
    directories = []

    try:
        for entry in sorted(target_dir.iterdir(), key=lambda e: (e.is_file(), e.name)):
            rel_path = str(entry.relative_to(workspace))
            if entry.is_file():
                stat = entry.stat()
                files.append({
                    "name": entry.name,
                    "path": rel_path,
                    "size": stat.st_size,
                    "modified": int(stat.st_mtime * 1000),  # ms timestamp
                    "extension": entry.suffix.lower(),
                })
            elif entry.is_dir():
                # 统计子文件数量（仅第一层）
                try:
                    file_count = sum(1 for _ in entry.iterdir() if _.is_file())
                except PermissionError:
                    file_count = 0
                directories.append({
                    "name": entry.name,
                    "path": rel_path,
                    "file_count": file_count,
                })
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=f"无权访问: {e}")

    return ApiResponse(
        code=0,
        data={
            "path": path,
            "files": files,
            "directories": directories,
        }
    )


@router.get("/read")
async def read_file(
    path: str = Query(..., description="文件相对路径"),
    student_id: int = Depends(get_current_student_id),
):
    """
    读取文件内容
    """
    workspace = get_workspace(student_id)
    file_path = validate_path(workspace, path)

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    if not file_path.is_file():
        raise HTTPException(status_code=400, detail="路径不是文件")

    try:
        raw = file_path.read_bytes()
        encoding = detect_encoding(raw)
        content = raw.decode(encoding, errors="replace")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"读取失败: {e}")

    return ApiResponse(
        code=0,
        data={
            "content": content,
            "encoding": encoding,
            "name": file_path.name,
            "path": path,
            "size": len(raw),
        }
    )


@router.post("/save")
async def save_file(
    request: FileSaveRequest,
    student_id: int = Depends(get_current_student_id),
):
    """
    保存文件内容
    """
    workspace = get_workspace(student_id)
    file_path = validate_path(workspace, request.path)

    # 确保父目录存在
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # 检查文件大小
    content_bytes = request.content.encode(request.encoding, errors="replace")
    original_size = file_path.stat().st_size if file_path.exists() else 0
    check_disk_quota(student_id, len(content_bytes) - original_size)

    try:
        file_path.write_bytes(content_bytes)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"保存失败: {e}")

    return ApiResponse(
        code=0,
        message="保存成功",
        data={"path": request.path, "size": len(content_bytes)}
    )


@router.delete("/delete")
async def delete_file(
    path: str = Query(..., description="文件或目录的相对路径"),
    student_id: int = Depends(get_current_student_id),
):
    """
    删除文件或目录
    """
    workspace = get_workspace(student_id)
    target = validate_path(workspace, path)

    if not target.exists():
        raise HTTPException(status_code=404, detail="文件或目录不存在")

    # 禁止删除工作区根目录本身
    if target.resolve() == workspace.resolve():
        raise HTTPException(status_code=400, detail="不允许删除工作区根目录")

    try:
        if target.is_file():
            target.unlink()
        else:
            shutil.rmtree(target)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")

    return ApiResponse(code=0, message="删除成功", data={"path": path})


@router.post("/mkdir")
async def make_directory(
    request: MkdirRequest,
    student_id: int = Depends(get_current_student_id),
):
    """
    创建目录
    """
    workspace = get_workspace(student_id)
    dir_path = validate_path(workspace, request.path)

    if dir_path.exists():
        raise HTTPException(status_code=400, detail="目录已存在")

    try:
        dir_path.mkdir(parents=True, exist_ok=False)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"创建失败: {e}")

    rel_path = str(dir_path.relative_to(workspace))
    return ApiResponse(code=0, message="创建成功", data={"path": rel_path})


@router.post("/rename")
async def rename_file(
    request: FileRenameRequest,
    student_id: int = Depends(get_current_student_id),
):
    """
    重命名文件或目录
    """
    workspace = get_workspace(student_id)
    source = validate_path(workspace, request.path)

    if not source.exists():
        raise HTTPException(status_code=404, detail="源文件或目录不存在")
    if source.resolve() == workspace.resolve():
        raise HTTPException(status_code=400, detail="不允许重命名工作区根目录")

    # 验证新名字没有包含反斜杠或斜杠
    if "/" in request.new_name or "\\" in request.new_name:
        raise HTTPException(status_code=400, detail="新名称不能包含路径分隔符")

    target = source.with_name(request.new_name)
    if target.exists():
        raise HTTPException(status_code=400, detail="目标名称已存在")

    try:
        source.rename(target)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"重命名失败: {e}")

    return ApiResponse(
        code=0,
        message="重命名成功",
        data={"new_path": str(target.relative_to(workspace))}
    )


@router.post("/move")
async def move_files(
    request: FileMoveRequest,
    student_id: int = Depends(get_current_student_id),
):
    """
    移动多个文件/目录到目标目录
    """
    workspace = get_workspace(student_id)
    target_dir = validate_path(workspace, request.target_dir)

    if not target_dir.exists():
        raise HTTPException(status_code=404, detail="目标目录不存在")
    if not target_dir.is_dir():
        raise HTTPException(status_code=400, detail="目标路径不是一个目录")

    success_paths = []
    failed_paths = []

    for path in request.source_paths:
        try:
            source = validate_path(workspace, path)
            if not source.exists():
                failed_paths.append({"path": path, "reason": "不存在"})
                continue
            
            # 防止移动到自身或子目录
            if target_dir.resolve().is_relative_to(source.resolve()):
                failed_paths.append({"path": path, "reason": "不能移动到自身的子目录中"})
                continue

            target = target_dir / source.name

            # 如果源文件和目标文件一样（比如只是在同一个文件夹里拖拽重排），直接视为成功
            if target.resolve() == source.resolve():
                success_paths.append(str(target.relative_to(workspace)))
                continue
            if target.exists():
                failed_paths.append({"path": path, "reason": "目标目录已存在同名文件"})
                continue

            shutil.move(str(source), str(target))
            success_paths.append(str(target.relative_to(workspace)))
        except Exception as e:
            failed_paths.append({"path": path, "reason": str(e)})

    if not success_paths and failed_paths:
        raise HTTPException(status_code=500, detail=f"移动失败: {failed_paths[0]['reason']}")

    return ApiResponse(
        code=0,
        message="移动完成",
        data={"success": success_paths, "failed": failed_paths}
    )


@router.post("/copy")
async def copy_files(
    request: FileCopyRequest,
    student_id: int = Depends(get_current_student_id),
):
    """
    复制多个文件/目录到目标目录
    """
    workspace = get_workspace(student_id)
    target_dir = validate_path(workspace, request.target_dir)

    if not target_dir.exists():
        raise HTTPException(status_code=404, detail="目标目录不存在")
    if not target_dir.is_dir():
        raise HTTPException(status_code=400, detail="目标路径不是目录")

    success_paths = []
    failed_paths = []

    for path in request.source_paths:
        try:
            source = validate_path(workspace, path)
            if not source.exists():
                failed_paths.append({"path": path, "reason": "源不存在"})
                continue
                
            target = target_dir / source.name
            
            # 自动重命名处理如果是同一目录复制
            if target.exists():
                counter = 1
                stem = source.stem
                suffix = source.suffix
                while target.exists():
                    target = target_dir / f"{stem}_copy{counter}{suffix}"
                    counter += 1

            if source.is_dir():
                # 预估大小太复杂，简单处理，后置检查配额暂略，真实生产应先预估大小
                shutil.copytree(str(source), str(target))
            else:
                shutil.copy2(str(source), str(target))

            success_paths.append(str(target.relative_to(workspace)))
        except Exception as e:
            failed_paths.append({"path": path, "reason": str(e)})

    # 在复制完成后做一次总配额检查，如果超标，抛错（虽已复制部分文件，但下次会被阻止）
    check_disk_quota(student_id, 0)

    return ApiResponse(
        code=0,
        message="复制完成",
        data={"success": success_paths, "failed": failed_paths}
    )


@router.delete("/batch-delete")
async def batch_delete_files(
    request: BatchDeleteRequest,
    student_id: int = Depends(get_current_student_id),
):
    """
    批量删除文件或目录
    """
    workspace = get_workspace(student_id)
    
    deleted = []
    failed = []

    for path in request.paths:
        try:
            target = validate_path(workspace, path)
            if not target.exists():
                failed.append({"path": path, "reason": "不存在"})
                continue
            
            if target.resolve() == workspace.resolve():
                failed.append({"path": path, "reason": "不允许删除工作区根目录"})
                continue

            if target.is_file():
                target.unlink()
            else:
                shutil.rmtree(target)
            deleted.append(path)
        except Exception as e:
            failed.append({"path": path, "reason": str(e)})

    return ApiResponse(
        code=0,
        message="批量删除完成",
        data={"deleted": deleted, "failed": failed}
    )


@router.post("/extract")
async def extract_archive(
    request: ExtractRequest,
    student_id: int = Depends(get_current_student_id),
):
    """
    解压缩文件到指定目录（默认解压到压缩文件所在目录）

    支持格式: .zip / .tar / .tar.gz / .tgz / .tar.bz2 / .tar.xz
    """
    workspace = get_workspace(student_id)
    archive_path = validate_path(workspace, request.path)

    if not archive_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    if not archive_path.is_file():
        raise HTTPException(status_code=400, detail="路径不是文件")

    # 检查格式支持
    name_lower = archive_path.name.lower()
    is_zip = name_lower.endswith(".zip")
    is_tar = (
        name_lower.endswith(".tar")
        or name_lower.endswith(".tar.gz")
        or name_lower.endswith(".tgz")
        or name_lower.endswith(".tar.bz2")
        or name_lower.endswith(".tar.xz")
    )
    if not is_zip and not is_tar:
        raise HTTPException(status_code=400, detail="不支持的压缩格式，仅支持 .zip / .tar / .tar.gz / .tgz / .tar.bz2 / .tar.xz")

    # 确定解压目标目录
    if request.target_dir:
        target_dir = validate_path(workspace, request.target_dir)
    else:
        target_dir = archive_path.parent

    target_dir.mkdir(parents=True, exist_ok=True)

    # 安全解压：防止路径穿越（Zip Slip）
    try:
        if is_zip:
            with zipfile.ZipFile(archive_path, "r") as zf:
                for member in zf.namelist():
                    # 检查 Zip Slip
                    member_path = (target_dir / member).resolve()
                    try:
                        member_path.relative_to(target_dir.resolve())
                    except ValueError:
                        raise HTTPException(status_code=400, detail=f"压缩包含危险路径: {member}")
                zf.extractall(target_dir)
        else:  # tar 系
            with tarfile.open(archive_path, "r:*") as tf:
                for member in tf.getmembers():
                    member_path = (target_dir / member.name).resolve()
                    try:
                        member_path.relative_to(target_dir.resolve())
                    except ValueError:
                        raise HTTPException(status_code=400, detail=f"压缩包含危险路径: {member.name}")
                tf.extractall(target_dir)
    except (zipfile.BadZipFile, tarfile.TarError) as e:
        raise HTTPException(status_code=400, detail=f"解压失败：文件可能已损坏: {e}")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"解压失败: {e}")

    # 解压后检查配额
    check_disk_quota(student_id, 0)

    return ApiResponse(
        code=0,
        message="解压成功",
        data={
            "source": request.path,
            "target_dir": str(target_dir.relative_to(workspace))
        }
    )


@router.post("/compress")
async def compress_files(
    request: CompressRequest,
    student_id: int = Depends(get_current_student_id),
):
    """
    压缩文件/目录到指定压缩包

    支持格式: zip / tar.gz
    - archive_name: 输出文件名（如 output.zip 或 output.tar.gz）
    - target_dir: 输出目录，默认为第一个源路径的父目录
    """
    if not request.paths:
        raise HTTPException(status_code=400, detail="至少需要一个源路径")

    workspace = get_workspace(student_id)

    # 验证所有源路径
    sources: list[Path] = []
    for path in request.paths:
        src = validate_path(workspace, path)
        if not src.exists():
            raise HTTPException(status_code=404, detail=f"路径不存在: {path}")
        sources.append(src)

    # 确定输出目录
    if request.target_dir:
        out_dir = validate_path(workspace, request.target_dir)
    else:
        out_dir = validate_path(workspace, request.paths[0]).parent

    out_dir.mkdir(parents=True, exist_ok=True)

    # 验证输出文件名安全性
    if "/" in request.archive_name or "\\" in request.archive_name:
        raise HTTPException(status_code=400, detail="压缩包名称不能包含路径分隔符")

    out_path = out_dir / request.archive_name
    if out_path.exists():
        raise HTTPException(status_code=400, detail=f"目标文件已存在: {request.archive_name}")

    try:
        if request.format == "zip":
            with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for src in sources:
                    if src.is_file():
                        zf.write(src, src.name)
                    elif src.is_dir():
                        for file in src.rglob("*"):
                            if file.is_file():
                                zf.write(file, src.name + "/" + str(file.relative_to(src)))
        else:  # tar.gz
            with tarfile.open(out_path, "w:gz") as tf:
                for src in sources:
                    tf.add(src, arcname=src.name)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"压缩失败: {e}")

    check_disk_quota(student_id, 0)

    rel_path = str(out_path.relative_to(workspace))
    return ApiResponse(
        code=0,
        message="压缩成功",
        data={"archive_path": rel_path}
    )


@router.get("/download")
async def download_file(
    path: str = Query(..., description="文件或目录的相对路径"),
    student_id: int = Depends(get_current_student_id),
):
    """
    下载文件或目录

    - 单文件：直接以流式返回文件内容
    - 目录：即时打包成 zip 以流式返回（不写入磁盘）
    """
    workspace = get_workspace(student_id)
    target = validate_path(workspace, path)

    if not target.exists():
        raise HTTPException(status_code=404, detail="文件或目录不存在")

    if target.is_file():
        # 单文件：流式返回
        file_size = target.stat().st_size
        filename = target.name

        def file_generator():
            with open(target, "rb") as f:
                while chunk := f.read(65536):
                    yield chunk

        return StreamingResponse(
            file_generator(),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(file_size),
            }
        )
    else:
        # 目录：内存中打 zip 后流式返回
        zip_name = target.name + ".zip"

        def zip_generator():
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for file in target.rglob("*"):
                    if file.is_file():
                        zf.write(file, target.name + "/" + str(file.relative_to(target)))
            buf.seek(0)
            while chunk := buf.read(65536):
                yield chunk

        return StreamingResponse(
            zip_generator(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{zip_name}"',
            }
        )


class DownloadMultipleRequest(BaseModel):
    paths: list[str]           # 要打包下载的路径列表
    archive_name: Optional[str] = None  # 自定义 zip 文件名，默认 "download.zip"


@router.post("/download-multiple")
async def download_multiple(
    request: DownloadMultipleRequest,
    student_id: int = Depends(get_current_student_id),
):
    """
    批量下载：将多个文件/目录打成一个 zip 包后流式返回（内存操作，不写磁盘）
    """
    if not request.paths:
        raise HTTPException(status_code=400, detail="至少需要一个路径")

    workspace = get_workspace(student_id)

    # 验证所有路径
    sources: list[Path] = []
    for p in request.paths:
        src = validate_path(workspace, p)
        if not src.exists():
            raise HTTPException(status_code=404, detail=f"路径不存在: {p}")
        sources.append(src)

    zip_filename = request.archive_name or "download.zip"
    if not zip_filename.endswith(".zip"):
        zip_filename += ".zip"

    def zip_generator():
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for src in sources:
                if src.is_file():
                    zf.write(src, src.name)
                elif src.is_dir():
                    for file in src.rglob("*"):
                        if file.is_file():
                            zf.write(file, src.name + "/" + str(file.relative_to(src)))
        buf.seek(0)
        while chunk := buf.read(65536):
            yield chunk

    return StreamingResponse(
        zip_generator(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{zip_filename}"',
        }
    )
