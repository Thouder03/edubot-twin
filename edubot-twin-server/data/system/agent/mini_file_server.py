"""
mini_file_server.py — 容器内轻量文件服务 (Sidecar)

运行于容器内，监听 0.0.0.0:8010。
宿主机通过 Docker bridge 网络连接，在代理层完成鉴权后透明转发。

支持的路由与 student/files.py 接口契约完全一致（相同请求/响应格式）：
  POST   /files/upload
  GET    /files/list
  GET    /files/read
  POST   /files/save
  DELETE /files/delete
  POST   /files/mkdir
  POST   /files/rename
  POST   /files/move
  POST   /files/copy
  DELETE /files/batch-delete
  POST   /files/extract
  POST   /files/compress
  GET    /files/download
  POST   /files/download-multiple

权限策略通过 X-Access-Scope 请求头控制（由宿主机代理层注入）：
  shadow_root    — 可读写全路径（危险路径删除保护）
  student_limited — 仅 /home /root 可读，/home/student 可写
"""

import io
import os
import shutil
import zipfile
import tarfile
from pathlib import Path
from typing import Optional, List
from typing_extensions import Literal   # 需要 pip install typing-extensions

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

app = FastAPI(title="EduBot Mini File Server", docs_url=None, redoc_url=None)

# ─── 策略常量 ───────────────────────────────────────────────────────────────

# 危险删除保护（所有 scope 均适用）
BLOCKED_DELETE_PATHS = {
    "/", "/bin", "/sbin", "/usr", "/lib", "/lib64",
    "/etc", "/proc", "/sys", "/dev", "/boot", "/opt/ros",
}

# student_limited scope 允许读取的目录前缀
STUDENT_READ_PREFIXES = ("/home", "/root")
# student_limited scope 允许写入的目录前缀
STUDENT_WRITE_PREFIX = "/home/student"


# ─── 策略校验工具 ────────────────────────────────────────────────────────────

def get_access_scope(request: Request) -> str:
    """从请求头读取 access scope，默认 shadow_root（兼容旧调用方）。"""
    return request.headers.get("X-Access-Scope", "shadow_root")


def resolve_path(raw_path: str) -> Path:
    """
    将传入路径解析为绝对路径。
    支持绝对路径（容器文件系统）和相对路径（相对于 /）。
    防止 .. 穿越。
    """
    if not raw_path or raw_path in (".", "/"):
        return Path("/")

    # 禁止 .. 以防穿越
    parts = raw_path.replace("\\", "/").split("/")
    if ".." in parts:
        raise HTTPException(status_code=400, detail="路径不能包含 ..")

    if raw_path.startswith("/"):
        return Path(raw_path).resolve()
    else:
        return (Path("/") / raw_path).resolve()


def check_read_allowed(path: Path, scope: str) -> None:
    """校验路径是否允许读取。"""
    if scope == "shadow_root":
        return  # 全路径可读
    # student_limited
    path_str = str(path)
    if any(path_str == prefix or path_str.startswith(prefix + "/")
           for prefix in STUDENT_READ_PREFIXES):
        return
    raise HTTPException(
        status_code=403,
        detail=f"student_limited scope 不允许读取路径: {path_str}"
    )


def check_write_allowed(path: Path, scope: str) -> None:
    """校验路径是否允许写入。"""
    if scope == "shadow_root":
        return  # 全路径可写
    # student_limited: 仅 /home/student 可写
    path_str = str(path)
    if path_str == STUDENT_WRITE_PREFIX or path_str.startswith(STUDENT_WRITE_PREFIX + "/"):
        return
    raise HTTPException(
        status_code=403,
        detail=f"student_limited scope 不允许写入路径: {path_str}"
    )


def check_delete_allowed(path: Path, scope: str) -> None:
    """校验路径是否允许删除（写权限 + 危险路径保护）。"""
    check_write_allowed(path, scope)
    normalized = str(path).rstrip("/") or "/"
    if normalized in BLOCKED_DELETE_PATHS:
        raise HTTPException(status_code=403, detail=f"禁止删除系统路径: {normalized}")


# ─── 工具函数 ───────────────────────────────────────────────────────────────

def detect_encoding(content: bytes) -> str:
    try:
        content.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "gbk"


def api_ok(data: dict, message: str = "ok") -> dict:
    return {"code": 0, "message": message, "data": data}


# ─── Pydantic 模型 ──────────────────────────────────────────────────────────

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
    source_paths: List[str]
    target_dir: str

class FileCopyRequest(BaseModel):
    source_paths: List[str]
    target_dir: str

class BatchDeleteRequest(BaseModel):
    paths: List[str]

class ExtractRequest(BaseModel):
    path: str
    target_dir: Optional[str] = None

class CompressRequest(BaseModel):
    paths: List[str]
    archive_name: str
    format: Literal["zip", "tar.gz"] = "zip"
    target_dir: Optional[str] = None

class DownloadMultipleRequest(BaseModel):
    paths: List[str]
    archive_name: Optional[str] = None


# ─── API 端点 ───────────────────────────────────────────────────────────────

@app.get("/files/list")
async def list_files(
    request: Request,
    path: str = Query(default="/", description="绝对路径"),
):
    scope = get_access_scope(request)
    target = resolve_path(path)
    check_read_allowed(target, scope)

    if not target.exists():
        raise HTTPException(status_code=404, detail="目录不存在")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="路径不是目录")

    files = []
    directories = []
    try:
        for entry in sorted(target.iterdir(), key=lambda e: (e.is_file(), e.name)):
            entry_path = str(entry)
            if entry.is_file():
                stat = entry.stat()
                files.append({
                    "name": entry.name,
                    "path": entry_path,
                    "size": stat.st_size,
                    "modified": int(stat.st_mtime * 1000),
                    "extension": entry.suffix.lower(),
                })
            elif entry.is_dir():
                # 性能优化：不再返回 file_count，避免目录列表阶段的额外磁盘扫描。
                directories.append({
                    "name": entry.name,
                    "path": entry_path,
                })
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=f"无权访问: {e}")

    return api_ok({"path": path, "files": files, "directories": directories})


@app.get("/files/read")
async def read_file(
    request: Request,
    path: str = Query(...),
):
    scope = get_access_scope(request)
    file_path = resolve_path(path)
    check_read_allowed(file_path, scope)

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

    return api_ok({
        "content": content,
        "encoding": encoding,
        "name": file_path.name,
        "path": path,
        "size": len(raw),
    })


@app.post("/files/save")
async def save_file(request: Request, body: FileSaveRequest):
    scope = get_access_scope(request)
    file_path = resolve_path(body.path)
    check_write_allowed(file_path, scope)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        file_path.write_bytes(body.content.encode(body.encoding, errors="replace"))
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"保存失败: {e}")
    return api_ok({"path": body.path, "size": file_path.stat().st_size}, "保存成功")


@app.post("/files/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    target_path: Optional[str] = Form(default="/"),
):
    scope = get_access_scope(request)
    target_dir = resolve_path(target_path or "/")
    check_write_allowed(target_dir, scope)
    content = await file.read()
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / file.filename
    try:
        dest.write_bytes(content)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"写入失败: {e}")
    return api_ok({"filename": file.filename, "path": str(dest), "size": len(content)}, "上传成功")


@app.delete("/files/delete")
async def delete_file(
    request: Request,
    path: str = Query(...),
):
    scope = get_access_scope(request)
    target = resolve_path(path)
    check_delete_allowed(target, scope)

    if not target.exists():
        raise HTTPException(status_code=404, detail="文件或目录不存在")
    try:
        if target.is_file():
            target.unlink()
        else:
            shutil.rmtree(target)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")
    return api_ok({"path": path}, "删除成功")


@app.post("/files/mkdir")
async def make_directory(request: Request, body: MkdirRequest):
    scope = get_access_scope(request)
    dir_path = resolve_path(body.path)
    check_write_allowed(dir_path, scope)
    if dir_path.exists():
        raise HTTPException(status_code=400, detail="目录已存在")
    try:
        dir_path.mkdir(parents=True, exist_ok=False)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"创建失败: {e}")
    return api_ok({"path": str(dir_path)}, "创建成功")


@app.post("/files/rename")
async def rename_file(request: Request, body: FileRenameRequest):
    scope = get_access_scope(request)
    source = resolve_path(body.path)
    check_write_allowed(source, scope)

    if not source.exists():
        raise HTTPException(status_code=404, detail="源文件或目录不存在")
    if "/" in body.new_name or "\\" in body.new_name:
        raise HTTPException(status_code=400, detail="新名称不能包含路径分隔符")

    target = source.with_name(body.new_name)
    if target.exists():
        raise HTTPException(status_code=400, detail="目标名称已存在")
    try:
        source.rename(target)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"重命名失败: {e}")
    return api_ok({"new_path": str(target)}, "重命名成功")


@app.post("/files/move")
async def move_files(request: Request, body: FileMoveRequest):
    scope = get_access_scope(request)
    target_dir = resolve_path(body.target_dir)
    check_write_allowed(target_dir, scope)

    if not target_dir.exists():
        raise HTTPException(status_code=404, detail="目标目录不存在")

    success_paths, failed_paths = [], []
    for path in body.source_paths:
        try:
            source = resolve_path(path)
            check_write_allowed(source, scope)
            if not source.exists():
                failed_paths.append({"path": path, "reason": "不存在"})
                continue
            try:
                target_dir.resolve().relative_to(source.resolve())
                failed_paths.append({"path": path, "reason": "不能移动到自身子目录"})
                continue
            except ValueError:
                pass
            target = target_dir / source.name
            if target.resolve() == source.resolve():
                success_paths.append(str(target))
                continue
            if target.exists():
                failed_paths.append({"path": path, "reason": "目标已存在同名"})
                continue
            shutil.move(str(source), str(target))
            success_paths.append(str(target))
        except HTTPException as e:
            failed_paths.append({"path": path, "reason": e.detail})
        except Exception as e:
            failed_paths.append({"path": path, "reason": str(e)})

    return api_ok({"success": success_paths, "failed": failed_paths}, "移动完成")


@app.post("/files/copy")
async def copy_files(request: Request, body: FileCopyRequest):
    scope = get_access_scope(request)
    target_dir = resolve_path(body.target_dir)
    check_write_allowed(target_dir, scope)

    if not target_dir.exists():
        raise HTTPException(status_code=404, detail="目标目录不存在")

    success_paths, failed_paths = [], []
    for path in body.source_paths:
        try:
            source = resolve_path(path)
            check_read_allowed(source, scope)
            if not source.exists():
                failed_paths.append({"path": path, "reason": "源不存在"})
                continue
            target = target_dir / source.name
            counter = 1
            while target.exists():
                stem = source.stem
                suffix = source.suffix
                target = target_dir / f"{stem}_copy{counter}{suffix}"
                counter += 1
            if source.is_dir():
                shutil.copytree(str(source), str(target))
            else:
                shutil.copy2(str(source), str(target))
            success_paths.append(str(target))
        except HTTPException as e:
            failed_paths.append({"path": path, "reason": e.detail})
        except Exception as e:
            failed_paths.append({"path": path, "reason": str(e)})

    return api_ok({"success": success_paths, "failed": failed_paths}, "复制完成")


@app.delete("/files/batch-delete")
async def batch_delete_files(request: Request, body: BatchDeleteRequest):
    scope = get_access_scope(request)
    deleted, failed = [], []
    for path in body.paths:
        try:
            target = resolve_path(path)
            check_delete_allowed(target, scope)
            if not target.exists():
                failed.append({"path": path, "reason": "不存在"})
                continue
            if target.is_file():
                target.unlink()
            else:
                shutil.rmtree(target)
            deleted.append(path)
        except HTTPException as e:
            failed.append({"path": path, "reason": e.detail})
        except Exception as e:
            failed.append({"path": path, "reason": str(e)})
    return api_ok({"deleted": deleted, "failed": failed}, "批量删除完成")


@app.post("/files/extract")
async def extract_archive(request: Request, body: ExtractRequest):
    scope = get_access_scope(request)
    archive_path = resolve_path(body.path)
    check_read_allowed(archive_path, scope)

    if not archive_path.exists() or not archive_path.is_file():
        raise HTTPException(status_code=404, detail="压缩文件不存在")

    name_lower = archive_path.name.lower()
    is_zip = name_lower.endswith(".zip")
    is_tar = any(name_lower.endswith(ext) for ext in (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz"))
    if not is_zip and not is_tar:
        raise HTTPException(status_code=400, detail="不支持的压缩格式")

    target_dir = resolve_path(body.target_dir) if body.target_dir else archive_path.parent
    check_write_allowed(target_dir, scope)
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        if is_zip:
            with zipfile.ZipFile(archive_path, "r") as zf:
                for member in zf.namelist():
                    mp = (target_dir / member).resolve()
                    try:
                        mp.relative_to(target_dir.resolve())
                    except ValueError:
                        raise HTTPException(status_code=400, detail=f"压缩包含危险路径: {member}")
                zf.extractall(target_dir)
        else:
            with tarfile.open(archive_path, "r:*") as tf:
                for member in tf.getmembers():
                    mp = (target_dir / member.name).resolve()
                    try:
                        mp.relative_to(target_dir.resolve())
                    except ValueError:
                        raise HTTPException(status_code=400, detail=f"压缩包含危险路径: {member.name}")
                tf.extractall(target_dir)
    except (zipfile.BadZipFile, tarfile.TarError) as e:
        raise HTTPException(status_code=400, detail=f"解压失败: {e}")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"解压失败: {e}")

    return api_ok({"source": body.path, "target_dir": str(target_dir)}, "解压成功")


@app.post("/files/compress")
async def compress_files(request: Request, body: CompressRequest):
    scope = get_access_scope(request)
    if not body.paths:
        raise HTTPException(status_code=400, detail="至少需要一个源路径")

    sources = []
    for path in body.paths:
        src = resolve_path(path)
        check_read_allowed(src, scope)
        if not src.exists():
            raise HTTPException(status_code=404, detail=f"路径不存在: {path}")
        sources.append(src)

    out_dir = resolve_path(body.target_dir) if body.target_dir else sources[0].parent
    check_write_allowed(out_dir, scope)
    out_dir.mkdir(parents=True, exist_ok=True)

    if "/" in body.archive_name or "\\" in body.archive_name:
        raise HTTPException(status_code=400, detail="压缩包名称不能含路径分隔符")

    out_path = out_dir / body.archive_name
    if out_path.exists():
        raise HTTPException(status_code=400, detail=f"目标文件已存在: {body.archive_name}")

    try:
        if body.format == "zip":
            with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for src in sources:
                    if src.is_file():
                        zf.write(src, src.name)
                    elif src.is_dir():
                        for f in src.rglob("*"):
                            if f.is_file():
                                zf.write(f, src.name + "/" + str(f.relative_to(src)))
        else:
            with tarfile.open(out_path, "w:gz") as tf:
                for src in sources:
                    tf.add(src, arcname=src.name)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"压缩失败: {e}")

    return api_ok({"archive_path": str(out_path)}, "压缩成功")


@app.get("/files/download")
async def download_file(
    request: Request,
    path: str = Query(...),
):
    scope = get_access_scope(request)
    target = resolve_path(path)
    check_read_allowed(target, scope)

    if not target.exists():
        raise HTTPException(status_code=404, detail="文件或目录不存在")

    if target.is_file():
        def file_gen():
            with open(target, "rb") as f:
                while chunk := f.read(65536):
                    yield chunk
        return StreamingResponse(
            file_gen(),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{target.name}"',
                "Content-Length": str(target.stat().st_size),
            }
        )
    else:
        zip_name = target.name + ".zip"
        def zip_gen():
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for f in target.rglob("*"):
                    if f.is_file():
                        zf.write(f, target.name + "/" + str(f.relative_to(target)))
            buf.seek(0)
            while chunk := buf.read(65536):
                yield chunk
        return StreamingResponse(
            zip_gen(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{zip_name}"'}
        )


@app.post("/files/download-multiple")
async def download_multiple(request: Request, body: DownloadMultipleRequest):
    scope = get_access_scope(request)
    if not body.paths:
        raise HTTPException(status_code=400, detail="至少需要一个路径")

    sources = []
    for p in body.paths:
        src = resolve_path(p)
        check_read_allowed(src, scope)
        if not src.exists():
            raise HTTPException(status_code=404, detail=f"路径不存在: {p}")
        sources.append(src)

    zip_filename = body.archive_name or "download.zip"
    if not zip_filename.endswith(".zip"):
        zip_filename += ".zip"

    def zip_gen():
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for src in sources:
                if src.is_file():
                    zf.write(src, src.name)
                elif src.is_dir():
                    for f in src.rglob("*"):
                        if f.is_file():
                            zf.write(f, src.name + "/" + str(f.relative_to(src)))
        buf.seek(0)
        while chunk := buf.read(65536):
            yield chunk

    return StreamingResponse(
        zip_gen(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_filename}"'}
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
