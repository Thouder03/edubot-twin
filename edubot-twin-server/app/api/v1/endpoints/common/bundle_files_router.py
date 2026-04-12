"""
通用 Bundle 文件操作路由工厂（第11期补全）

为所有「基于目录存储的资源包」统一实现 12 个文件操作端点：
  list / upload / read / save / delete / mkdir / rename / move / copy / extract / compress / download

使用方式：
  创建一个「资源解析器」回调（根据 id 拿到 bundle 模型并校验归属），
  以及一个「统计更新器」回调（写回 file_count / total_size_bytes）；
  工厂即返回一个挂载好 12 个端点的 APIRouter，直接 include_router 到父路由即可。

设计原则：
  - 不耦合任何具体资源模型（Experiment / Exam / …）
  - 所有文件操作委托给 BundleFileService（单一真相源）
  - 支持 protected_paths（如 startup.sh）
  - 可选的 post_mutation 钩子：每次变更后触发（如 eval_script 的 validate_status 自动重算）
"""
from __future__ import annotations

import io
import zipfile
from typing import Awaitable, Callable, Optional, Protocol

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_teacher
from app.db.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.experiment import (
    BundleCompressRequest,
    BundleCopyRequest,
    BundleExtractRequest,
    BundleMkdirRequest,
    BundleMoveRequest,
    BundleOpResponse,
    BundleRenameRequest,
    FileListItem,
    FileListResponse,
    FileReadResponse,
    FileSaveRequest,
    FileUploadResponse,
)
from app.services.bundle_file_service import (
    BundleFileError,
    BundleFileService,
    FileConflictError,
    FileSizeExceededError,
    PathTraversalError,
    ProtectedPathError,
)
from app.services.bundle_file_service import FileNotFoundError as BundleFileNotFoundError


# ─── 类型协议 ─────────────────────────────────────────────────────────────────


class _BundleLike(Protocol):
    """Bundle 模型协议：需具备 storage_root 字符串属性"""

    id: int
    storage_root: str


BundleResolver = Callable[[AsyncSession, int, int], Awaitable[_BundleLike]]
"""(db, bundle_id, teacher_id) → bundle 模型（失败应 raise HTTPException）"""

StatsUpdater = Callable[[AsyncSession, _BundleLike, int, int, list[dict]], Awaitable[None]]
"""(db, bundle, file_count, total_size_bytes, file_manifest) → None。
manifest 为 [{relative_path, chmod_mode}]，不需要的资源可忽略此参数。"""


# ─── 工具 ─────────────────────────────────────────────────────────────────────


def _handle(e: BundleFileError) -> None:
    raise HTTPException(status_code=e.status_code, detail=e.code)


def _relpath(target, root) -> str:
    return str(target.relative_to(root).as_posix())


# ─── 工厂主体 ─────────────────────────────────────────────────────────────────


def build_bundle_files_router(
    *,
    resolver: BundleResolver,
    stats_updater: StatsUpdater,
    protected_paths: Optional[set[str]] = None,
    sort_top_files: Optional[tuple[str, ...]] = None,
) -> APIRouter:
    """
    构建一个挂载 12 个文件操作端点的子路由。

    使用方式：
        sub = build_bundle_files_router(resolver=..., stats_updater=...)
        parent = APIRouter()
        parent.include_router(sub, prefix="/{bundle_id}")

    :param resolver: 根据 id 取回 bundle 并鉴权
    :param stats_updater: 统计刷新回调（upload/delete/move/copy/extract/compress/rename 之后调用）
    :param protected_paths: 受保护的相对路径集合（如 {'startup.sh'}）
    :param sort_top_files: 根目录列表时置顶的文件名（如 ('startup.sh',)）
    :returns: 可以 include_router 到父路由的 APIRouter（端点路径均为 /files[/...]）
    """
    router = APIRouter()
    protected: set[str] = protected_paths or set()
    top_files: tuple[str, ...] = sort_top_files or ()

    def _get_service(bundle: _BundleLike) -> BundleFileService:
        return BundleFileService(storage_root=bundle.storage_root, protected_paths=protected)

    async def _refresh_stats(
        db: AsyncSession, bundle: _BundleLike, svc: BundleFileService
    ) -> tuple[int, int]:
        fc, ts, manifest = svc.scan_directory()
        await stats_updater(db, bundle, fc, ts, manifest)
        return fc, ts

    # ─── 1. 列目录 ─────────────────────────────────────────────────────────────

    @router.get("/files", response_model=ApiResponse[FileListResponse], summary="列目录")
    async def list_files(
        bundle_id: int,
        path: Optional[str] = Query(default=None),
        db: AsyncSession = Depends(get_db),
        teacher_id: int = Depends(get_current_teacher),
    ):
        bundle = await resolver(db, bundle_id, teacher_id)
        svc = _get_service(bundle)
        try:
            items = svc.list_files(path or "")
        except PathTraversalError as e:
            _handle(e)

        # 置顶文件（如 startup.sh）仅在根目录列表时生效
        if not path and top_files:
            top = [i for i in items if i["name"] in top_files]
            others = [i for i in items if i["name"] not in top_files]
            items = top + others

        return ApiResponse(data=FileListResponse(items=[FileListItem(**i) for i in items]))

    # ─── 2. 上传文件 ───────────────────────────────────────────────────────────

    @router.post(
        "/files/upload",
        response_model=ApiResponse[FileUploadResponse],
        summary="上传文件",
    )
    async def upload_file(
        bundle_id: int,
        file: UploadFile = File(...),
        path: Optional[str] = Form(default=None),
        db: AsyncSession = Depends(get_db),
        teacher_id: int = Depends(get_current_teacher),
    ):
        bundle = await resolver(db, bundle_id, teacher_id)
        svc = _get_service(bundle)
        file_data = await file.read()
        try:
            svc.save_uploaded_file(file.filename or "upload", file_data, target_dir=path)
        except (FileSizeExceededError, PathTraversalError) as e:
            _handle(e)
        fc, ts = await _refresh_stats(db, bundle, svc)
        return ApiResponse(data=FileUploadResponse(file_count=fc, total_size_bytes=ts))

    # ─── 3. 读文件 ─────────────────────────────────────────────────────────────

    @router.get("/files/read", response_model=ApiResponse[FileReadResponse], summary="读文件")
    async def read_file(
        bundle_id: int,
        path: str = Query(...),
        db: AsyncSession = Depends(get_db),
        teacher_id: int = Depends(get_current_teacher),
    ):
        bundle = await resolver(db, bundle_id, teacher_id)
        svc = _get_service(bundle)
        try:
            content, encoding = svc.read_file(path)
            abs_path = svc._safe_path(path)
            mtime = abs_path.stat().st_mtime if abs_path.exists() else None
        except (BundleFileNotFoundError, PathTraversalError) as e:
            _handle(e)
        return ApiResponse(
            data=FileReadResponse(content=content, encoding=encoding, modified_at=mtime)
        )

    # ─── 4. 保存文件 ───────────────────────────────────────────────────────────

    @router.post("/files/save", response_model=ApiResponse[dict], summary="保存文件")
    async def save_file(
        bundle_id: int,
        data: FileSaveRequest,
        db: AsyncSession = Depends(get_db),
        teacher_id: int = Depends(get_current_teacher),
    ):
        bundle = await resolver(db, bundle_id, teacher_id)
        svc = _get_service(bundle)
        try:
            new_mtime = svc.save_file(data.path, data.content, data.modified_at)
        except (FileConflictError, PathTraversalError, ProtectedPathError) as e:
            _handle(e)
        # save 操作可能改变文件大小，refresh 一次
        await _refresh_stats(db, bundle, svc)
        return ApiResponse(data={"modified_at": new_mtime})

    # ─── 5. 删除文件 ───────────────────────────────────────────────────────────

    @router.delete(
        "/files/delete", status_code=status.HTTP_204_NO_CONTENT, summary="删除文件/目录"
    )
    async def delete_file(
        bundle_id: int,
        path: str = Query(...),
        db: AsyncSession = Depends(get_db),
        teacher_id: int = Depends(get_current_teacher),
    ):
        bundle = await resolver(db, bundle_id, teacher_id)
        svc = _get_service(bundle)
        try:
            svc.delete_file(path)
        except BundleFileError as e:
            _handle(e)
        await _refresh_stats(db, bundle, svc)

    # ─── 6. 新建目录 ───────────────────────────────────────────────────────────

    @router.post("/files/mkdir", response_model=ApiResponse[dict], summary="新建目录")
    async def mkdir_dir(
        bundle_id: int,
        data: BundleMkdirRequest,
        db: AsyncSession = Depends(get_db),
        teacher_id: int = Depends(get_current_teacher),
    ):
        bundle = await resolver(db, bundle_id, teacher_id)
        svc = _get_service(bundle)
        try:
            target = svc.mkdir(data.path)
        except BundleFileError as e:
            _handle(e)
        return ApiResponse(data={"path": _relpath(target, svc.storage_root)})

    # ─── 7. 重命名 ─────────────────────────────────────────────────────────────

    @router.post("/files/rename", response_model=ApiResponse[dict], summary="重命名文件/目录")
    async def rename_entry(
        bundle_id: int,
        data: BundleRenameRequest,
        db: AsyncSession = Depends(get_db),
        teacher_id: int = Depends(get_current_teacher),
    ):
        bundle = await resolver(db, bundle_id, teacher_id)
        svc = _get_service(bundle)
        try:
            target = svc.rename(data.path, data.new_name)
        except BundleFileError as e:
            _handle(e)
        await _refresh_stats(db, bundle, svc)
        return ApiResponse(data={"new_path": _relpath(target, svc.storage_root)})

    # ─── 8. 移动 ───────────────────────────────────────────────────────────────

    @router.post(
        "/files/move", response_model=ApiResponse[BundleOpResponse], summary="移动文件/目录"
    )
    async def move_entries(
        bundle_id: int,
        data: BundleMoveRequest,
        db: AsyncSession = Depends(get_db),
        teacher_id: int = Depends(get_current_teacher),
    ):
        bundle = await resolver(db, bundle_id, teacher_id)
        svc = _get_service(bundle)
        try:
            success, failed = svc.move(data.source_paths, data.target_dir)
        except BundleFileError as e:
            _handle(e)
        if not success and failed:
            raise HTTPException(status_code=400, detail=failed[0]["reason"])
        await _refresh_stats(db, bundle, svc)
        return ApiResponse(data=BundleOpResponse(success=success, failed=failed))

    # ─── 9. 复制 ───────────────────────────────────────────────────────────────

    @router.post(
        "/files/copy", response_model=ApiResponse[BundleOpResponse], summary="复制文件/目录"
    )
    async def copy_entries(
        bundle_id: int,
        data: BundleCopyRequest,
        db: AsyncSession = Depends(get_db),
        teacher_id: int = Depends(get_current_teacher),
    ):
        bundle = await resolver(db, bundle_id, teacher_id)
        svc = _get_service(bundle)
        try:
            success, failed = svc.copy(data.source_paths, data.target_dir)
        except BundleFileError as e:
            _handle(e)
        if not success and failed:
            raise HTTPException(status_code=400, detail=failed[0]["reason"])
        await _refresh_stats(db, bundle, svc)
        return ApiResponse(data=BundleOpResponse(success=success, failed=failed))

    # ─── 10. 解压 ──────────────────────────────────────────────────────────────

    @router.post("/files/extract", response_model=ApiResponse[dict], summary="解压文件")
    async def extract_archive(
        bundle_id: int,
        data: BundleExtractRequest,
        db: AsyncSession = Depends(get_db),
        teacher_id: int = Depends(get_current_teacher),
    ):
        bundle = await resolver(db, bundle_id, teacher_id)
        svc = _get_service(bundle)
        try:
            out_dir = svc.extract(data.path, data.target_dir)
        except BundleFileError as e:
            _handle(e)
        await _refresh_stats(db, bundle, svc)
        return ApiResponse(
            data={"target_dir": _relpath(out_dir, svc.storage_root) or "."}
        )

    # ─── 11. 压缩 ──────────────────────────────────────────────────────────────

    @router.post("/files/compress", response_model=ApiResponse[dict], summary="压缩文件")
    async def compress_entries(
        bundle_id: int,
        data: BundleCompressRequest,
        db: AsyncSession = Depends(get_db),
        teacher_id: int = Depends(get_current_teacher),
    ):
        bundle = await resolver(db, bundle_id, teacher_id)
        svc = _get_service(bundle)
        try:
            out_path = svc.compress(
                paths=data.paths,
                archive_name=data.archive_name,
                format=data.format,
                target_dir=data.target_dir,
            )
        except BundleFileError as e:
            _handle(e)
        await _refresh_stats(db, bundle, svc)
        return ApiResponse(data={"archive_path": _relpath(out_path, svc.storage_root)})

    # ─── 12. 下载 ──────────────────────────────────────────────────────────────

    @router.get("/files/download", summary="下载文件或目录")
    async def download_entry(
        bundle_id: int,
        path: str = Query(..., description="文件或目录相对路径"),
        db: AsyncSession = Depends(get_db),
        teacher_id: int = Depends(get_current_teacher),
    ):
        bundle = await resolver(db, bundle_id, teacher_id)
        svc = _get_service(bundle)
        try:
            target = svc.resolve_for_download(path)
        except BundleFileError as e:
            _handle(e)

        if target.is_file():
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
                },
            )

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
            headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
        )

    return router
