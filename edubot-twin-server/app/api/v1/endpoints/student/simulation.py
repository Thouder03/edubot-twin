from __future__ import annotations

import asyncio
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_student_id
from app.crud import container as crud_container
from app.crud import experiment as crud_experiment
from app.crud import simulation_task as crud_task
from app.db.database import AsyncSessionLocal, get_db
from app.models.simulation_task import SimulationTaskStage, SimulationTaskStatus
from app.schemas.common import ApiResponse
from app.schemas.container import ContainerCreate
from app.schemas.experiment import (
    FileDistributeRequest,
    FileDistributeResponse,
    StudentSimulationStartRequest,
    StudentSimulationStartResponse,
)

router = APIRouter()


async def _run_rebuild_task(task_id: str, student_id: int, version_id: int) -> None:
    started_at = time.perf_counter()
    async with AsyncSessionLocal() as db:
        task = await crud_task.get_task(db, task_id)
        version = await crud_experiment.get_version(db, version_id)
        if not task or not version:
            return

        try:
            await crud_task.mark_task_running(db, task=task)

            await crud_task.mark_stage(
                db,
                task=task,
                stage=SimulationTaskStage.PREPARING_CONFIG,
                status="SUCCEEDED",
                elapsed_ms=10,
            )

            existing = await crud_container.get_container_by_user(db, student_id)
            stop_start = time.perf_counter()
            if existing:
                await crud_container.delete_container(db, existing)
            await crud_task.mark_stage(
                db,
                task=task,
                stage=SimulationTaskStage.STOPPING_OLD_CONTAINER,
                status="SUCCEEDED",
                elapsed_ms=int((time.perf_counter() - stop_start) * 1000),
            )

            create_start = time.perf_counter()
            container = await crud_container.create_container(
                db,
                ContainerCreate(
                    user_id=student_id,
                    image_name=version.image_name,
                    current_version_id=version.id,
                ),
            )
            if container.status.value == "error":
                raise RuntimeError(container.error_message or "container create failed")
            await crud_task.mark_stage(
                db,
                task=task,
                stage=SimulationTaskStage.CREATING_NEW_CONTAINER,
                status="SUCCEEDED",
                elapsed_ms=int((time.perf_counter() - create_start) * 1000),
            )

            health_start = time.perf_counter()
            if container.status.value != "running":
                raise RuntimeError("container health check failed")
            await crud_task.mark_stage(
                db,
                task=task,
                stage=SimulationTaskStage.HEALTH_CHECKING,
                status="SUCCEEDED",
                elapsed_ms=int((time.perf_counter() - health_start) * 1000),
            )

            await crud_task.finish_task(
                db,
                task=task,
                status=SimulationTaskStatus.SUCCEEDED,
                elapsed_ms=int((time.perf_counter() - started_at) * 1000),
                retryable=False,
            )
        except Exception as e:
            await crud_task.mark_stage(
                db,
                task=task,
                stage=task.current_stage,
                status="FAILED",
                elapsed_ms=0,
                error_code="CONTAINER_REBUILD_FAILED",
                error_message=str(e),
            )
            await crud_task.finish_task(
                db,
                task=task,
                status=SimulationTaskStatus.FAILED,
                elapsed_ms=int((time.perf_counter() - started_at) * 1000),
                retryable=True,
                error_code="CONTAINER_REBUILD_FAILED",
                error_message=str(e),
            )


# ── 文件分发辅助函数（独立出来以便 monkeypatch 替换）─────────────────────────────

def _validate_selected_paths(selected_paths: list[str], manifest: list) -> None:
    """校验 selected_paths 安全性与清单归属，失败抛 HTTPException 400。"""
    manifest_paths = {item["relative_path"] for item in manifest}
    for path in selected_paths:
        if ".." in path or path.startswith("/"):
            raise HTTPException(status_code=400, detail="INVALID_PATH")
        if path not in manifest_paths:
            raise HTTPException(status_code=400, detail="PATH_NOT_IN_MANIFEST")


async def _do_file_distribute(files: list, student_id: int) -> None:
    """实际文件分发操作（可被 monkeypatch 替换用于测试）。
    生产实现：docker cp 或通过挂载卷拷贝。"""
    # 本期主链路占位实现；真实分发在后续期次中接入 Docker SDK
    pass


async def _do_set_permissions(student_id: int) -> None:
    """设置容器内 /home/student/experiment 权限（可被 monkeypatch 替换）。
    生产实现：docker exec chmod/chown。"""
    pass


async def _run_distribute_task(task_id: str, student_id: int, files: list) -> None:
    started_at = time.perf_counter()
    async with AsyncSessionLocal() as db:
        task = await crud_task.get_task(db, task_id)
        if not task:
            return
        try:
            await crud_task.mark_task_running(db, task=task)

            await crud_task.mark_stage(
                db, task=task,
                stage=SimulationTaskStage.VALIDATING_MANIFEST,
                status="SUCCEEDED", elapsed_ms=1,
            )

            dist_start = time.perf_counter()
            await _do_file_distribute(files, student_id)
            await crud_task.mark_stage(
                db, task=task,
                stage=SimulationTaskStage.DISTRIBUTING_FILES,
                status="SUCCEEDED",
                elapsed_ms=int((time.perf_counter() - dist_start) * 1000),
            )

            perm_start = time.perf_counter()
            await _do_set_permissions(student_id)
            await crud_task.mark_stage(
                db, task=task,
                stage=SimulationTaskStage.SETTING_PERMISSIONS,
                status="SUCCEEDED",
                elapsed_ms=int((time.perf_counter() - perm_start) * 1000),
            )

            await crud_task.finish_task(
                db, task=task,
                status=SimulationTaskStatus.SUCCEEDED,
                elapsed_ms=int((time.perf_counter() - started_at) * 1000),
                retryable=False,
            )
        except Exception as e:
            await crud_task.mark_stage(
                db, task=task,
                stage=task.current_stage,
                status="FAILED", elapsed_ms=0,
                error_code="FILE_BUNDLE_DISTRIBUTION_FAILED",
                error_message=str(e),
            )
            await crud_task.finish_task(
                db, task=task,
                status=SimulationTaskStatus.FAILED,
                elapsed_ms=int((time.perf_counter() - started_at) * 1000),
                retryable=True,
                error_code="FILE_BUNDLE_DISTRIBUTION_FAILED",
                error_message=str(e),
            )


@router.post(
    "/files/distribute",
    summary="分发实验文件到容器",
    status_code=status.HTTP_202_ACCEPTED,
)
async def distribute_files(
    data: FileDistributeRequest,
    db: AsyncSession = Depends(get_db),
    student_id: int = Depends(get_current_student_id),
):
    version = await crud_experiment.get_version(db, data.version_id)
    if not version or not version.is_visible or version.publish_status.value != "published":
        raise HTTPException(status_code=404, detail="EXPERIMENT_VERSION_NOT_FOUND")

    if not version.file_bundle_id:
        raise HTTPException(status_code=400, detail="NO_FILE_BUNDLE_ATTACHED")

    bundle = await crud_experiment.get_bundle(db, version.file_bundle_id)
    if not bundle or bundle.validate_status.value != "valid":
        raise HTTPException(status_code=400, detail="FILE_BUNDLE_NOT_VALID")

    manifest: list = bundle.file_manifest or []

    # 路径安全校验（仅在 selected_paths 非空时逐项校验）
    if data.selected_paths:
        _validate_selected_paths(data.selected_paths, manifest)
        files_to_distribute = [
            item for item in manifest
            if item["relative_path"] in set(data.selected_paths)
        ]
    else:
        # selected_paths=[] 表示全选清单所有文件
        files_to_distribute = list(manifest)

    task = await crud_task.create_task(
        db,
        student_id=student_id,
        target_version_id=version.id,
        container_id=None,
    )

    asyncio.create_task(_run_distribute_task(task.task_id, student_id, files_to_distribute))

    payload = ApiResponse(
        data=FileDistributeResponse(
            task_id=task.task_id,
            task_status="PENDING",
            accepted_at=datetime.utcnow().isoformat(),
            target_dir="/home/student/experiment",
        )
    )
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=payload.model_dump())


@router.post("/start", response_model=ApiResponse[StudentSimulationStartResponse], summary="开始仿真")
async def start_simulation(
    data: StudentSimulationStartRequest,
    db: AsyncSession = Depends(get_db),
    student_id: int = Depends(get_current_student_id),
):
    version = await crud_experiment.get_version(db, data.version_id)
    if not version or not version.is_visible or version.publish_status.value != "published":
        raise HTTPException(status_code=404, detail="EXPERIMENT_VERSION_NOT_FOUND")

    existing = await crud_container.get_container_by_user(db, student_id)

    if (
        existing
        and not data.force_recreate
        and existing.current_version_id == version.id
        and existing.status.value == "running"
    ):
        return ApiResponse(
            data=StudentSimulationStartResponse(
                task_id=None,
                container_status="running",
                experiment_context={
                    "experiment_id": version.experiment_id,
                    "version_id": version.id,
                    "environment_key": version.environment_key,
                },
            )
        )

    active_task = await crud_task.get_active_task_by_student(db, student_id)
    if active_task:
        raise HTTPException(status_code=409, detail="CONTAINER_REBUILD_IN_PROGRESS")

    task = await crud_task.create_task(
        db,
        student_id=student_id,
        target_version_id=version.id,
        container_id=getattr(existing, "id", None) if existing else None,
    )

    asyncio.create_task(_run_rebuild_task(task.task_id, student_id, version.id))

    payload = ApiResponse(
        data=StudentSimulationStartResponse(
            task_id=task.task_id,
            container_status="creating",
            experiment_context={
                "experiment_id": version.experiment_id,
                "version_id": version.id,
                "environment_key": version.environment_key,
            },
        )
    )
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=payload.model_dump())
