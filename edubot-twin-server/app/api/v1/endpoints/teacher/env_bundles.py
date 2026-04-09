"""
教师端环境包管理 API（10-S1-4 新增）

端点前缀：/api/v1/teachers/env-bundles
"""
import asyncio
import io
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, File, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container_manager import inspect_container_state, get_container_logs_tail
from app.core.readiness_checker import check_gzweb_ready, check_rosbridge_ready
from app.core.security import create_access_token, get_current_teacher
from app.core.system_entrypoint import create_env_bundle_startup_script
from app.crud import container as crud_container
from app.crud import experiment as crud_experiment
from app.crud.shadow_student import get_or_create_shadow
from app.db.database import AsyncSessionLocal, get_db
from app.schemas.common import ApiResponse
from app.models.container import ContainerStatus
from app.schemas.container import ContainerCreate
from app.schemas.experiment import (
    BundleCompressRequest,
    BundleCopyRequest,
    BundleExtractRequest,
    BundleMkdirRequest,
    BundleMoveRequest,
    BundleOpResponse,
    BundleRenameRequest,
    EnvBundleCreate,
    EnvBundleDryRunByVersionRequest,
    EnvBundleDryRunByVersionResponse,
    EnvBundleListItem,
    EnvBundleListResponse,
    EnvBundleResponse,
    EnvBundleUpdateRequest,
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

# 环境包存储根目录基路径
ENV_BUNDLES_BASE_DIR = Path("data/env_bundles").resolve()

# startup.sh 是受保护文件，禁止删除
PROTECTED_PATHS = {"startup.sh"}

router = APIRouter()


DRY_RUN_READINESS_TIMEOUT_S = 25.0


async def _probe_dry_run_readiness(
    container_db_id: int,
    gz_port: Optional[int],
    ros_port: Optional[int],
) -> None:
    """后台探测 Dry Run 端口就绪，回写容器状态（creating -> running/error）。"""
    if not gz_port and not ros_port:
        async with AsyncSessionLocal() as db:
            container = await crud_container.get_container(db, container_db_id)
            if container:
                container.status = ContainerStatus.ERROR
                container.error_message = "DRY_RUN_PORT_MAPPING_MISSING"
                await db.commit()
        return

    checks: list[tuple[str, asyncio.Future]] = []
    if gz_port:
        checks.append(("GZWEB", check_gzweb_ready(gz_port, timeout_s=DRY_RUN_READINESS_TIMEOUT_S)))
    if ros_port:
        checks.append(("ROSBRIDGE", check_rosbridge_ready(ros_port, timeout_s=DRY_RUN_READINESS_TIMEOUT_S)))

    names = [name for name, _ in checks]
    coroutines = [coro for _, coro in checks]
    results = await asyncio.gather(*coroutines, return_exceptions=True)

    failures: list[str] = []
    for name, result in zip(names, results):
        if isinstance(result, Exception):
            failures.append(f"{name}_CHECK_EXCEPTION: {result}")
            continue
        ok, _elapsed_ms = result
        if not ok:
            failures.append(f"{name}_NOT_READY")

    async with AsyncSessionLocal() as db:
        container = await crud_container.get_container(db, container_db_id)
        if not container:
            return

        if failures:
            detail_parts = list(failures)

            if container.container_id:
                state = await inspect_container_state(container.container_id)
                if state:
                    docker_status = state.get("status")
                    exit_code = state.get("exit_code")
                    state_error = state.get("error")
                    detail_parts.append(f"DOCKER_STATUS={docker_status}")
                    if exit_code is not None:
                        detail_parts.append(f"EXIT_CODE={exit_code}")
                    if state_error:
                        detail_parts.append(f"DOCKER_ERROR={state_error}")

                    if docker_status in {"exited", "dead"}:
                        tail_logs = await get_container_logs_tail(container.container_id, tail=50)
                        if tail_logs and tail_logs.strip():
                            compact_logs = " | ".join(
                                line.strip() for line in tail_logs.splitlines() if line.strip()
                            )
                            if compact_logs:
                                detail_parts.append(f"LOG_TAIL={compact_logs[:500]}")

            container.status = ContainerStatus.ERROR
            container.error_message = "DRY_RUN_READINESS_FAILED: " + " | ".join(detail_parts)
        else:
            container.status = ContainerStatus.RUNNING
            container.error_message = None
        await db.commit()


def _get_service(env_bundle) -> BundleFileService:
    """为环境包创建 BundleFileService 实例（startup.sh 受保护）"""
    return BundleFileService(
        storage_root=env_bundle.storage_root,
        protected_paths=PROTECTED_PATHS,
    )


def _handle_bundle_error(e: BundleFileError):
    """将 BundleFileError 转换为 HTTPException"""
    raise HTTPException(status_code=e.status_code, detail=e.code)


# ─── 环境包 CRUD ───────────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=ApiResponse[EnvBundleResponse],
    status_code=status.HTTP_201_CREATED,
    summary="创建环境包",
)
async def create_env_bundle(
    data: EnvBundleCreate,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """
    创建环境包（10-S1-4）。
    自动生成 startup.sh 模板文件（10-S1-3: 启动脚本以文件形式存储）。
    """
    env_bundle = await crud_experiment.create_env_bundle(
        db,
        name=data.name,
        storage_root="",  # 临时占位
        container_target_dir=data.container_target_dir,
        access_level=data.access_level,
        created_by=teacher_id,
    )
    # 基于 ID 确定 storage_root 并更新
    storage_root = str(ENV_BUNDLES_BASE_DIR / str(env_bundle.id))
    env_bundle.storage_root = storage_root
    await db.commit()
    await db.refresh(env_bundle)

    # 自动生成 startup.sh 模板（10-S1-3）
    create_env_bundle_startup_script(storage_root)

    # 更新文件统计
    svc = _get_service(env_bundle)
    file_count, total_size, _ = svc.scan_directory()
    await crud_experiment.update_env_bundle_stats(
        db, env_bundle=env_bundle,
        file_count=file_count,
        total_size_bytes=total_size,
    )

    return ApiResponse(data=_to_env_bundle_response(env_bundle))


@router.get("", response_model=ApiResponse[EnvBundleListResponse], summary="环境包列表")
async def list_env_bundles(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """分页查询当前教师的环境包列表"""
    bundles, total = await crud_experiment.list_env_bundles(
        db, created_by=teacher_id, page=page, page_size=page_size, keyword=keyword
    )
    items = [
        EnvBundleListItem(
            env_bundle_id=b.id,
            name=b.name,
            container_target_dir=b.container_target_dir,
            access_level=b.access_level.value,
            file_count=b.file_count,
            created_at=b.created_at,
        )
        for b in bundles
    ]
    return ApiResponse(data=EnvBundleListResponse(total=total, list=items))


@router.get("/{env_bundle_id}", response_model=ApiResponse[EnvBundleResponse], summary="环境包详情")
async def get_env_bundle(
    env_bundle_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    env_bundle = await _get_env_bundle_or_404(db, env_bundle_id, teacher_id)
    return ApiResponse(data=_to_env_bundle_response(env_bundle))


@router.patch("/{env_bundle_id}", response_model=ApiResponse[EnvBundleResponse], summary="更新环境包设置")
async def update_env_bundle(
    env_bundle_id: int,
    data: EnvBundleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """更新环境包基础设置（名称、目标目录、访问权限）"""
    env_bundle = await _get_env_bundle_or_404(db, env_bundle_id, teacher_id)
    updated = await crud_experiment.update_env_bundle(
        db,
        env_bundle=env_bundle,
        name=data.name,
        container_target_dir=data.container_target_dir,
        access_level=data.access_level,
    )
    return ApiResponse(data=_to_env_bundle_response(updated))


@router.delete("/{env_bundle_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除环境包")
async def delete_env_bundle(
    env_bundle_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """删除环境包（被版本引用时返回 409）"""
    env_bundle = await _get_env_bundle_or_404(db, env_bundle_id, teacher_id)
    try:
        await crud_experiment.delete_env_bundle(db, env_bundle=env_bundle)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post(
    "/{env_bundle_id}/dry-run",
    response_model=ApiResponse[EnvBundleDryRunByVersionResponse],
    summary="环境包 Dry Run 试运行（Shadow 学生方案）",
)
async def dry_run_env_bundle(
    env_bundle_id: int,
    data: EnvBundleDryRunByVersionRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """
    启动 Dry Run 容器。

    采用 Shadow 学生身份方案：为教师创建/复用一个 Shadow 学生账号，
    在该账号下创建容器（写入 DB），签发 Shadow JWT 返回给前端。
    前端使用 Shadow JWT 访问所有学生 API，获得与学生完全一致的体验。
    支持草稿状态（publish_status != published）的实验版本。
    """
    env_bundle = await _get_env_bundle_or_404(db, env_bundle_id, teacher_id)

    startup_script_path = str(Path(env_bundle.storage_root) / "startup.sh")
    if not Path(startup_script_path).exists():
        raise HTTPException(status_code=409, detail="MISSING_STARTUP_SCRIPT")

    # 从 version 读取启动配置（不检查 publish_status，教师可访问草稿版本）
    version = await crud_experiment.get_version(db, data.version_id)
    if not version:
        raise HTTPException(status_code=404, detail="VERSION_NOT_FOUND")

    image_name = version.image_name or "gzweb_sim:v1"
    launch_file_path = version.launch_file_path
    launch_args = dict(version.launch_args_template) if version.launch_args_template else {}
    env_volumes = {env_bundle.storage_root: env_bundle.container_target_dir}

    # 获取或创建 Shadow 学生
    shadow = await get_or_create_shadow(db, teacher_id)

    # force_recreate：若 Shadow 学生已有容器则先销毁（同一时间只允许 1 个）
    existing = await crud_container.get_container_by_user(db, shadow.id)
    if existing:
        await crud_container.delete_container(db, existing)

    # 以 Shadow 学生身份创建容器（写入 DB）
    try:
        container = await crud_container.create_container(
            db,
            ContainerCreate(
                user_id=shadow.id,
                image_name=image_name,
                current_version_id=version.id,
                launch_file_path=launch_file_path,
                launch_args=launch_args,
                startup_script_path=startup_script_path,
                env_volumes=env_volumes,
            ),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DRY_RUN_START_FAILED: {e}")

    if container.status.value == "error":
        raise HTTPException(status_code=500, detail=f"DRY_RUN_START_FAILED: {container.error_message}")

    # 回退到 creating，避免前端误判“已就绪”提前移除覆盖层
    container.status = ContainerStatus.CREATING
    container.error_message = None
    await db.commit()

    # 异步就绪探测：成功置 running，失败置 error + 失败原因
    asyncio.create_task(
        _probe_dry_run_readiness(container.id, container.gzbridge_port, container.rosbridge_port)
    )

    # 签发 Shadow JWT（role="student" 使所有学生 API 正常通过认证）
    # 注意：容器实际就绪由后台探测 + 前端轮询决定
    shadow_token = create_access_token({
        "sub": shadow.username,
        "user_id": shadow.id,
        "role": "student",
        "role_id": "10",
        "is_shadow": True,
        "shadow_owner_id": teacher_id,
    })

    return ApiResponse(data=EnvBundleDryRunByVersionResponse(
        shadow_token=shadow_token,
        container_id=container.container_id or "",
    ))


# ─── 环境包文件操作 ───────────────────────────────────────────────────────────────

@router.post("/{env_bundle_id}/files/upload", response_model=ApiResponse[FileUploadResponse], summary="上传文件")
async def upload_file_to_env_bundle(
    env_bundle_id: int,
    file: UploadFile = File(...),
    path: Optional[str] = Form(default=None),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """上传文件到环境包。压缩包不自动解压，可在文件树中手动解压。"""
    env_bundle = await _get_env_bundle_or_404(db, env_bundle_id, teacher_id)
    svc = _get_service(env_bundle)

    file_data = await file.read()
    try:
        svc.save_uploaded_file(file.filename or "upload", file_data, target_dir=path)
    except FileSizeExceededError as e:
        _handle_bundle_error(e)
    except PathTraversalError as e:
        _handle_bundle_error(e)

    file_count, total_size, _ = svc.scan_directory()
    await crud_experiment.update_env_bundle_stats(
        db, env_bundle=env_bundle,
        file_count=file_count,
        total_size_bytes=total_size,
    )
    return ApiResponse(data=FileUploadResponse(file_count=file_count, total_size_bytes=total_size))


@router.get("/{env_bundle_id}/files", response_model=ApiResponse[FileListResponse], summary="列目录")
async def list_env_bundle_files(
    env_bundle_id: int,
    path: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """列出环境包指定目录下的文件（startup.sh 始终显示在最顶部）"""
    env_bundle = await _get_env_bundle_or_404(db, env_bundle_id, teacher_id)
    svc = _get_service(env_bundle)
    try:
        items = svc.list_files(path or "")
    except PathTraversalError as e:
        _handle_bundle_error(e)

    # 将 startup.sh 排在最顶部（仅在根目录列表时）
    if not path:
        startup = [i for i in items if i["name"] == "startup.sh"]
        others = [i for i in items if i["name"] != "startup.sh"]
        items = startup + others

    return ApiResponse(data=FileListResponse(
        items=[FileListItem(**item) for item in items]
    ))


@router.get("/{env_bundle_id}/files/read", response_model=ApiResponse[FileReadResponse], summary="读文件内容")
async def read_env_bundle_file(
    env_bundle_id: int,
    path: str = Query(...),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """读取环境包中指定文件的文本内容（含 startup.sh）"""
    env_bundle = await _get_env_bundle_or_404(db, env_bundle_id, teacher_id)
    svc = _get_service(env_bundle)
    try:
        content, encoding = svc.read_file(path)
        abs_path = svc._safe_path(path)
        mtime = abs_path.stat().st_mtime if abs_path.exists() else None
    except BundleFileNotFoundError as e:
        _handle_bundle_error(e)
    except PathTraversalError as e:
        _handle_bundle_error(e)
    return ApiResponse(data=FileReadResponse(content=content, encoding=encoding, modified_at=mtime))


@router.post("/{env_bundle_id}/files/save", response_model=ApiResponse[dict], summary="保存文件内容")
async def save_env_bundle_file(
    env_bundle_id: int,
    data: FileSaveRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """保存环境包中指定文件的内容（含 startup.sh，含冲突检测）"""
    env_bundle = await _get_env_bundle_or_404(db, env_bundle_id, teacher_id)
    svc = _get_service(env_bundle)
    try:
        new_mtime = svc.save_file(data.path, data.content, data.modified_at)
    except FileConflictError as e:
        _handle_bundle_error(e)
    except PathTraversalError as e:
        _handle_bundle_error(e)
    return ApiResponse(data={"modified_at": new_mtime})


@router.delete(
    "/{env_bundle_id}/files/delete",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除文件（startup.sh 禁止删除）",
)
async def delete_env_bundle_file(
    env_bundle_id: int,
    path: str = Query(...),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """
    删除环境包中指定文件。
    startup.sh 受保护，禁止删除（返回 403 STARTUP_SCRIPT_PROTECTED）。
    """
    env_bundle = await _get_env_bundle_or_404(db, env_bundle_id, teacher_id)
    svc = _get_service(env_bundle)
    try:
        svc.delete_file(path)
    except ProtectedPathError as e:
        _handle_bundle_error(e)
    except BundleFileNotFoundError as e:
        _handle_bundle_error(e)
    except PathTraversalError as e:
        _handle_bundle_error(e)

    # 更新统计
    file_count, total_size, _ = svc.scan_directory()
    await crud_experiment.update_env_bundle_stats(
        db, env_bundle=env_bundle,
        file_count=file_count,
        total_size_bytes=total_size,
    )


async def _refresh_env_stats(db: AsyncSession, env_bundle, svc: BundleFileService) -> None:
    """重新扫描目录并写入文件计数/总大小。"""
    file_count, total_size, _ = svc.scan_directory()
    await crud_experiment.update_env_bundle_stats(
        db, env_bundle=env_bundle,
        file_count=file_count,
        total_size_bytes=total_size,
    )


@router.post("/{env_bundle_id}/files/mkdir", response_model=ApiResponse[dict], summary="新建目录")
async def mkdir_env_bundle(
    env_bundle_id: int,
    data: BundleMkdirRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    env_bundle = await _get_env_bundle_or_404(db, env_bundle_id, teacher_id)
    svc = _get_service(env_bundle)
    try:
        target = svc.mkdir(data.path)
    except BundleFileError as e:
        _handle_bundle_error(e)
    return ApiResponse(data={"path": str(target.relative_to(svc.storage_root).as_posix())})


@router.post("/{env_bundle_id}/files/rename", response_model=ApiResponse[dict], summary="重命名文件/目录")
async def rename_env_bundle_file(
    env_bundle_id: int,
    data: BundleRenameRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    env_bundle = await _get_env_bundle_or_404(db, env_bundle_id, teacher_id)
    svc = _get_service(env_bundle)
    try:
        target = svc.rename(data.path, data.new_name)
    except BundleFileError as e:
        _handle_bundle_error(e)
    await _refresh_env_stats(db, env_bundle, svc)
    return ApiResponse(data={"new_path": str(target.relative_to(svc.storage_root).as_posix())})


@router.post("/{env_bundle_id}/files/move", response_model=ApiResponse[BundleOpResponse], summary="移动文件/目录")
async def move_env_bundle_files(
    env_bundle_id: int,
    data: BundleMoveRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    env_bundle = await _get_env_bundle_or_404(db, env_bundle_id, teacher_id)
    svc = _get_service(env_bundle)
    try:
        success, failed = svc.move(data.source_paths, data.target_dir)
    except BundleFileError as e:
        _handle_bundle_error(e)
    if not success and failed:
        raise HTTPException(status_code=400, detail=failed[0]["reason"])
    await _refresh_env_stats(db, env_bundle, svc)
    return ApiResponse(data=BundleOpResponse(success=success, failed=failed))


@router.post("/{env_bundle_id}/files/copy", response_model=ApiResponse[BundleOpResponse], summary="复制文件/目录")
async def copy_env_bundle_files(
    env_bundle_id: int,
    data: BundleCopyRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    env_bundle = await _get_env_bundle_or_404(db, env_bundle_id, teacher_id)
    svc = _get_service(env_bundle)
    try:
        success, failed = svc.copy(data.source_paths, data.target_dir)
    except BundleFileError as e:
        _handle_bundle_error(e)
    if not success and failed:
        raise HTTPException(status_code=400, detail=failed[0]["reason"])
    await _refresh_env_stats(db, env_bundle, svc)
    return ApiResponse(data=BundleOpResponse(success=success, failed=failed))


@router.post("/{env_bundle_id}/files/extract", response_model=ApiResponse[dict], summary="解压文件")
async def extract_env_bundle_archive(
    env_bundle_id: int,
    data: BundleExtractRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    env_bundle = await _get_env_bundle_or_404(db, env_bundle_id, teacher_id)
    svc = _get_service(env_bundle)
    try:
        out_dir = svc.extract(data.path, data.target_dir)
    except BundleFileError as e:
        _handle_bundle_error(e)
    await _refresh_env_stats(db, env_bundle, svc)
    return ApiResponse(data={"target_dir": str(out_dir.relative_to(svc.storage_root).as_posix() or ".")})


@router.post("/{env_bundle_id}/files/compress", response_model=ApiResponse[dict], summary="压缩文件")
async def compress_env_bundle_files(
    env_bundle_id: int,
    data: BundleCompressRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    env_bundle = await _get_env_bundle_or_404(db, env_bundle_id, teacher_id)
    svc = _get_service(env_bundle)
    try:
        out_path = svc.compress(
            paths=data.paths,
            archive_name=data.archive_name,
            format=data.format,
            target_dir=data.target_dir,
        )
    except BundleFileError as e:
        _handle_bundle_error(e)
    await _refresh_env_stats(db, env_bundle, svc)
    return ApiResponse(data={"archive_path": str(out_path.relative_to(svc.storage_root).as_posix())})


@router.get("/{env_bundle_id}/files/download", summary="下载文件或目录")
async def download_env_bundle_file(
    env_bundle_id: int,
    path: str = Query(..., description="文件或目录相对路径"),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """单文件流式返回；目录即时打包为 zip 流式返回。"""
    env_bundle = await _get_env_bundle_or_404(db, env_bundle_id, teacher_id)
    svc = _get_service(env_bundle)
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

async def _get_env_bundle_or_404(db, env_bundle_id: int, teacher_id: int):
    """获取环境包并校验归属权"""
    env_bundle = await crud_experiment.get_env_bundle(db, env_bundle_id)
    if not env_bundle:
        raise HTTPException(status_code=404, detail="环境包不存在")
    if env_bundle.created_by != teacher_id:
        raise HTTPException(status_code=403, detail="无权访问该环境包")
    return env_bundle


def _to_env_bundle_response(env_bundle) -> EnvBundleResponse:
    return EnvBundleResponse(
        env_bundle_id=env_bundle.id,
        name=env_bundle.name,
        storage_root=env_bundle.storage_root,
        container_target_dir=env_bundle.container_target_dir,
        access_level=env_bundle.access_level.value,
        file_count=env_bundle.file_count,
        total_size_bytes=env_bundle.total_size_bytes,
        created_at=env_bundle.created_at,
        created_by=env_bundle.created_by,
        updated_at=env_bundle.updated_at,
    )
