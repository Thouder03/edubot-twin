"""
教师端环境包管理 API（10-S1-4 新增）

端点前缀：/api/v1/teachers/env-bundles
"""
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container_manager import create_container as create_docker_container
from app.core.container_manager import remove_container
from app.core.dry_run_manager import DryRunSession, dry_run_manager
from app.core.port_allocator import allocate_ports
from app.core.readiness_checker import check_gzweb_ready, check_rosbridge_ready
from app.core.security import get_current_teacher
from app.core.system_entrypoint import create_env_bundle_startup_script
from app.crud import experiment as crud_experiment
from app.db.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.experiment import (
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
    summary="环境包 Dry Run 试运行（SDD §6.2）",
)
async def dry_run_env_bundle(
    env_bundle_id: int,
    data: EnvBundleDryRunByVersionRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """
    启动 Dry Run 容器并执行就绪检测。

    从 version_id 对应的版本配置读取 image_name、launch_file_path、launch_args_template。
    返回 {container_id, simulation_url}，前端直接跳转复用学生仿真页面。
    """
    env_bundle = await _get_env_bundle_or_404(db, env_bundle_id, teacher_id)

    startup_script_path = str(Path(env_bundle.storage_root) / "startup.sh")
    if not Path(startup_script_path).exists():
        raise HTTPException(status_code=409, detail="MISSING_STARTUP_SCRIPT")

    # 从 version 读取启动配置
    version = await crud_experiment.get_version(db, data.version_id)
    if not version:
        raise HTTPException(status_code=404, detail="VERSION_NOT_FOUND")

    image_name = version.image_name or "gzweb_sim:v1"
    launch_file_path = version.launch_file_path
    launch_args = dict(version.launch_args_template) if version.launch_args_template else {}
    readiness_timeout_seconds = 60.0

    # 配额检查（单教师最多 3 个 Dry Run 容器）
    if dry_run_manager.count_for_teacher(teacher_id) >= 3:
        raise HTTPException(status_code=429, detail="DRY_RUN_RESOURCE_EXHAUSTED")

    gz_port, ros_port = await allocate_ports(db)
    env_volumes = {env_bundle.storage_root: env_bundle.container_target_dir}

    try:
        container_id = await create_docker_container(
            image=image_name,
            student_id=teacher_id,
            gz_port=gz_port,
            ros_port=ros_port,
            launch_file_path=(
                launch_file_path
                or "/home/ubuntu20/catkin_ws/src/bingda_tutorials/launch/simulation_robot.launch"
            ),
            launch_args=launch_args,
            startup_script_path=startup_script_path,
            env_volumes=env_volumes,
            is_dry_run=True,
        )

        dry_run_manager.register(
            DryRunSession(
                container_id=container_id,
                env_bundle_id=env_bundle_id,
                teacher_id=teacher_id,
                gzbridge_port=gz_port,
                rosbridge_port=ros_port,
                created_at=datetime.utcnow(),
            )
        )

        gz_ok, _ = await check_gzweb_ready(gz_port, timeout_s=readiness_timeout_seconds)
        ros_ok, _ = await check_rosbridge_ready(ros_port, timeout_s=readiness_timeout_seconds)
        if not gz_ok or not ros_ok:
            await remove_container(container_id)
            dry_run_manager.unregister(container_id)
            raise HTTPException(status_code=504, detail="DRY_RUN_READINESS_TIMEOUT")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DRY_RUN_START_FAILED: {e}")

    host = os.getenv("SERVER_HOST", "localhost")
    gzbridge_url = f"http://{host}:{gz_port}"
    rosbridge_url = f"ws://{host}:{ros_port}"
    return ApiResponse(data=EnvBundleDryRunByVersionResponse(
        container_id=container_id,
        simulation_url=gzbridge_url,
        rosbridge_url=rosbridge_url,
    ))


@router.delete(
    "/dry-run/{container_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="停止并清理 Dry Run 容器",
)
async def stop_dry_run_container(
    container_id: str,
    teacher_id: int = Depends(get_current_teacher),
):
    """停止并删除 Dry Run 容器（仅创建者可操作）。"""
    session = dry_run_manager.get(container_id)
    if not session:
        raise HTTPException(status_code=404, detail="DRY_RUN_NOT_FOUND")
    if session.teacher_id != teacher_id:
        raise HTTPException(status_code=403, detail="FORBIDDEN")

    try:
        await remove_container(container_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DRY_RUN_REMOVE_FAILED: {e}")
    finally:
        dry_run_manager.unregister(container_id)


# ─── 环境包文件操作 ───────────────────────────────────────────────────────────────

@router.post("/{env_bundle_id}/files/upload", response_model=ApiResponse[FileUploadResponse], summary="上传文件")
async def upload_file_to_env_bundle(
    env_bundle_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """上传文件到环境包。压缩包不自动解压，可在文件树中手动解压。"""
    env_bundle = await _get_env_bundle_or_404(db, env_bundle_id, teacher_id)
    svc = _get_service(env_bundle)

    file_data = await file.read()
    try:
        svc.save_uploaded_file(file.filename or "upload", file_data)
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
