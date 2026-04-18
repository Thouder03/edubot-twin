"""
教师端文件包管理 API（10-S1-6 新增）

端点前缀：/api/v1/teachers/file-bundles
"""
import io
import os
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, File, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_teacher
from app.crud import experiment as crud_experiment
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
    FileBundleCreate,
    FileBundleListItem,
    FileBundleListResponse,
    FileBundleRenameRequest,
    FileBundleRenameResponse,
    FileBundleResponse,
    FileListItem,
    FileListResponse,
    FileReadResponse,
    FileSaveRequest,
    FileUploadResponse,
)
from app.services.bundle_file_service import (
    BundleFileService,
    BundleFileError,
    ProtectedPathError,
    FileSizeExceededError,
    FileNotFoundError as BundleFileNotFoundError,
    PathTraversalError,
    FileConflictError,
)

from app.core import path_policy

router = APIRouter()


def _get_service(bundle) -> BundleFileService:
    """为文件包创建 BundleFileService 实例（无受保护路径限制）"""
    return BundleFileService(storage_root=bundle.storage_root)


def _handle_bundle_error(e: BundleFileError):
    """将 BundleFileError 转换为 HTTPException"""
    raise HTTPException(status_code=e.status_code, detail=e.code)


# ─── 文件包 CRUD ───────────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=ApiResponse[FileBundleResponse],
    status_code=status.HTTP_201_CREATED,
    summary="创建文件包",
)
async def create_file_bundle(
    data: FileBundleCreate,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """
    创建文件包（10-S1-6）。
    自动在 /data/file_bundles/{id}/ 下创建存储目录。
    """
    # 先创建记录获取 ID，再基于 ID 设置 storage_root
    try:
        bundle = await crud_experiment.create_bundle(
            db,
            name=data.name,
            storage_root="",  # 临时占位，稍后更新
            created_by=teacher_id,
        )
    except ValueError as e:
        if str(e) == "FILE_BUNDLE_NAME_DUPLICATE":
            raise HTTPException(status_code=409, detail="FILE_BUNDLE_NAME_DUPLICATE")
        raise

    # 基于 ID 确定 storage_root 并更新
    storage_root = str(path_policy.FILE_BUNDLES_BASE_DIR / str(bundle.id))
    Path(storage_root).mkdir(parents=True, exist_ok=True)
    bundle.storage_root = storage_root
    await db.commit()
    await db.refresh(bundle)

    return ApiResponse(data=_to_bundle_response(bundle))


@router.get("", response_model=ApiResponse[FileBundleListResponse], summary="文件包列表")
async def list_file_bundles(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """分页查询当前教师的文件包列表"""
    bundles, total = await crud_experiment.list_bundles(
        db, created_by=teacher_id, page=page, page_size=page_size, keyword=keyword
    )
    items = [
        FileBundleListItem(
            bundle_id=b.id,
            name=b.name,
            file_count=b.file_count,
            total_size_bytes=b.total_size_bytes,
            validate_status=b.validate_status.value,
            created_at=b.created_at,
        )
        for b in bundles
    ]
    return ApiResponse(data=FileBundleListResponse(total=total, list=items))


@router.get("/{bundle_id}", response_model=ApiResponse[FileBundleResponse], summary="文件包详情")
async def get_file_bundle(
    bundle_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    bundle = await _get_bundle_or_404(db, bundle_id, teacher_id)
    return ApiResponse(data=_to_bundle_response(bundle))


@router.patch("/{bundle_id}", response_model=ApiResponse[FileBundleRenameResponse], summary="重命名文件包")
async def rename_file_bundle(
    bundle_id: int,
    data: FileBundleRenameRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """重命名文件包，返回受影响版本列表"""
    bundle = await _get_bundle_or_404(db, bundle_id, teacher_id)
    bundle, affected = await crud_experiment.rename_bundle(db, bundle=bundle, new_name=data.name)
    return ApiResponse(data=FileBundleRenameResponse(
        bundle_id=bundle.id,
        name=bundle.name,
        affected_versions=affected,
    ))


@router.delete("/{bundle_id}",  response_model=ApiResponse, summary="删除文件包")
async def delete_file_bundle(
    bundle_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """删除文件包（被版本引用时返回 409）"""
    bundle = await _get_bundle_or_404(db, bundle_id, teacher_id)
    try:
        await crud_experiment.delete_bundle(db, bundle=bundle)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return ApiResponse(data=None, message="已删除")


# ─── 文件包文件操作 ──────────────────────────────────────────────────────────────

@router.post("/{bundle_id}/files/upload", response_model=ApiResponse[FileUploadResponse], summary="上传文件")
async def upload_file_to_bundle(
    bundle_id: int,
    file: UploadFile = File(...),
    path: Optional[str] = Form(default=None),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """
    上传文件到文件包（10-S1-6）。
    压缩包不自动解压，直接保存到文件系统；教师可在文件树中手动解压。
    上传成功后自动重建 file_manifest 并更新统计信息。
    """
    bundle = await _get_bundle_or_404(db, bundle_id, teacher_id)
    svc = _get_service(bundle)

    file_data = await file.read()
    try:
        svc.save_uploaded_file(file.filename or "upload", file_data, target_dir=path)
    except FileSizeExceededError as e:
        _handle_bundle_error(e)
    except PathTraversalError as e:
        _handle_bundle_error(e)

    # 重建统计信息
    file_count, total_size, manifest = svc.scan_directory()
    await crud_experiment.update_bundle_stats(
        db, bundle=bundle,
        file_count=file_count,
        total_size_bytes=total_size,
        file_manifest=manifest,
    )
    return ApiResponse(data=FileUploadResponse(file_count=file_count, total_size_bytes=total_size))


@router.get("/{bundle_id}/files", response_model=ApiResponse[FileListResponse], summary="列目录")
async def list_bundle_files(
    bundle_id: int,
    path: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """列出文件包指定目录下的文件"""
    bundle = await _get_bundle_or_404(db, bundle_id, teacher_id)
    svc = _get_service(bundle)
    try:
        items = svc.list_files(path or "")
    except PathTraversalError as e:
        _handle_bundle_error(e)
    return ApiResponse(data=FileListResponse(
        items=[FileListItem(**item) for item in items]
    ))


@router.get("/{bundle_id}/files/read", response_model=ApiResponse[FileReadResponse], summary="读文件内容")
async def read_bundle_file(
    bundle_id: int,
    path: str = Query(...),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """读取文件包中指定文件的文本内容"""
    bundle = await _get_bundle_or_404(db, bundle_id, teacher_id)
    svc = _get_service(bundle)
    try:
        content, encoding = svc.read_file(path)
        abs_path = svc._safe_path(path)
        mtime = abs_path.stat().st_mtime if abs_path.exists() else None
    except BundleFileNotFoundError as e:
        _handle_bundle_error(e)
    except PathTraversalError as e:
        _handle_bundle_error(e)
    return ApiResponse(data=FileReadResponse(content=content, encoding=encoding, modified_at=mtime))


@router.post("/{bundle_id}/files/save", response_model=ApiResponse[dict], summary="保存文件内容")
async def save_bundle_file(
    bundle_id: int,
    data: FileSaveRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """保存文件包中指定文件的内容（含冲突检测）"""
    bundle = await _get_bundle_or_404(db, bundle_id, teacher_id)
    svc = _get_service(bundle)
    try:
        new_mtime = svc.save_file(data.path, data.content, data.modified_at)
    except FileConflictError as e:
        _handle_bundle_error(e)
    except PathTraversalError as e:
        _handle_bundle_error(e)

    # 保存后重新统计以更新 file_count
    file_count, total_size, manifest = svc.scan_directory()
    await crud_experiment.update_bundle_stats(
        db, bundle=bundle,
        file_count=file_count,
        total_size_bytes=total_size,
        file_manifest=manifest,
    )
    return ApiResponse(data={"modified_at": new_mtime})


@router.delete("/{bundle_id}/files/delete", response_model=ApiResponse , summary="删除文件")
async def delete_bundle_file(
    bundle_id: int,
    path: str = Query(...),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """删除文件包中指定文件"""
    bundle = await _get_bundle_or_404(db, bundle_id, teacher_id)
    svc = _get_service(bundle)
    try:
        svc.delete_file(path)
    except BundleFileNotFoundError as e:
        _handle_bundle_error(e)
    except PathTraversalError as e:
        _handle_bundle_error(e)

    # 更新统计
    file_count, total_size, manifest = svc.scan_directory()
    await crud_experiment.update_bundle_stats(
        db, bundle=bundle,
        file_count=file_count,
        total_size_bytes=total_size,
        file_manifest=manifest,
    )
    return ApiResponse(data=None, message="已删除")


async def _refresh_stats(db: AsyncSession, bundle, svc: BundleFileService) -> None:
    """重新扫描目录并写入 file_count / total_size / file_manifest。"""
    file_count, total_size, manifest = svc.scan_directory()
    await crud_experiment.update_bundle_stats(
        db, bundle=bundle,
        file_count=file_count,
        total_size_bytes=total_size,
        file_manifest=manifest,
    )


@router.post("/{bundle_id}/files/mkdir", response_model=ApiResponse[dict], summary="新建目录")
async def mkdir_bundle(
    bundle_id: int,
    data: BundleMkdirRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    bundle = await _get_bundle_or_404(db, bundle_id, teacher_id)
    svc = _get_service(bundle)
    try:
        target = svc.mkdir(data.path)
    except BundleFileError as e:
        _handle_bundle_error(e)
    return ApiResponse(data={"path": str(target.relative_to(svc.storage_root).as_posix())})


@router.post("/{bundle_id}/files/rename", response_model=ApiResponse[dict], summary="重命名文件/目录")
async def rename_bundle_file(
    bundle_id: int,
    data: BundleRenameRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    bundle = await _get_bundle_or_404(db, bundle_id, teacher_id)
    svc = _get_service(bundle)
    try:
        target = svc.rename(data.path, data.new_name)
    except BundleFileError as e:
        _handle_bundle_error(e)
    await _refresh_stats(db, bundle, svc)
    return ApiResponse(data={"new_path": str(target.relative_to(svc.storage_root).as_posix())})


@router.post("/{bundle_id}/files/move", response_model=ApiResponse[BundleOpResponse], summary="移动文件/目录")
async def move_bundle_files(
    bundle_id: int,
    data: BundleMoveRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    bundle = await _get_bundle_or_404(db, bundle_id, teacher_id)
    svc = _get_service(bundle)
    try:
        success, failed = svc.move(data.source_paths, data.target_dir)
    except BundleFileError as e:
        _handle_bundle_error(e)
    if not success and failed:
        raise HTTPException(status_code=400, detail=failed[0]["reason"])
    await _refresh_stats(db, bundle, svc)
    return ApiResponse(data=BundleOpResponse(success=success, failed=failed))


@router.post("/{bundle_id}/files/copy", response_model=ApiResponse[BundleOpResponse], summary="复制文件/目录")
async def copy_bundle_files(
    bundle_id: int,
    data: BundleCopyRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    bundle = await _get_bundle_or_404(db, bundle_id, teacher_id)
    svc = _get_service(bundle)
    try:
        success, failed = svc.copy(data.source_paths, data.target_dir)
    except BundleFileError as e:
        _handle_bundle_error(e)
    if not success and failed:
        raise HTTPException(status_code=400, detail=failed[0]["reason"])
    await _refresh_stats(db, bundle, svc)
    return ApiResponse(data=BundleOpResponse(success=success, failed=failed))


@router.post("/{bundle_id}/files/extract", response_model=ApiResponse[dict], summary="解压文件")
async def extract_bundle_archive(
    bundle_id: int,
    data: BundleExtractRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    bundle = await _get_bundle_or_404(db, bundle_id, teacher_id)
    svc = _get_service(bundle)
    try:
        out_dir = svc.extract(data.path, data.target_dir)
    except BundleFileError as e:
        _handle_bundle_error(e)
    await _refresh_stats(db, bundle, svc)
    return ApiResponse(data={"target_dir": str(out_dir.relative_to(svc.storage_root).as_posix() or ".")})


@router.post("/{bundle_id}/files/compress", response_model=ApiResponse[dict], summary="压缩文件")
async def compress_bundle_files(
    bundle_id: int,
    data: BundleCompressRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    bundle = await _get_bundle_or_404(db, bundle_id, teacher_id)
    svc = _get_service(bundle)
    try:
        out_path = svc.compress(
            paths=data.paths,
            archive_name=data.archive_name,
            format=data.format,
            target_dir=data.target_dir,
        )
    except BundleFileError as e:
        _handle_bundle_error(e)
    await _refresh_stats(db, bundle, svc)
    return ApiResponse(data={"archive_path": str(out_path.relative_to(svc.storage_root).as_posix())})


@router.get("/{bundle_id}/files/download", summary="下载文件或目录")
async def download_bundle_file(
    bundle_id: int,
    path: str = Query(..., description="文件或目录相对路径"),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """单文件流式返回；目录即时打包为 zip 流式返回。"""
    bundle = await _get_bundle_or_404(db, bundle_id, teacher_id)
    svc = _get_service(bundle)
    try:
        target = svc.resolve_for_download(path)
    except BundleFileError as e:
        _handle_bundle_error(e)

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

    # 目录打包为 zip
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


# ─── 辅助函数 ──────────────────────────────────────────────────────────────────

async def _get_bundle_or_404(db, bundle_id: int, teacher_id: int):
    """获取文件包并校验归属权"""
    bundle = await crud_experiment.get_bundle(db, bundle_id)
    if not bundle:
        raise HTTPException(status_code=404, detail="文件包不存在")
    if bundle.created_by != teacher_id:
        raise HTTPException(status_code=403, detail="无权访问该文件包")
    return bundle


def _to_bundle_response(bundle) -> FileBundleResponse:
    return FileBundleResponse(
        bundle_id=bundle.id,
        name=bundle.name,
        storage_root=bundle.storage_root,
        file_count=bundle.file_count,
        total_size_bytes=bundle.total_size_bytes,
        file_manifest=bundle.file_manifest,
        validate_status=bundle.validate_status.value,
        created_at=bundle.created_at,
        created_by=bundle.created_by,
    )
