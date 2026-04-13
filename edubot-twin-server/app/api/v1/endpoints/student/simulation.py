from __future__ import annotations

import asyncio
import logging
import shlex
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import object_session

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_student_id
from app.core.readiness_checker import (
    check_gzweb_ready,
    check_rosbridge_ready,
    check_port_ready,
)
from app.core import container_manager
from app.crud import container as crud_container
from app.crud import experiment as crud_experiment
from app.crud import simulation_task as crud_task
from app.db.database import AsyncSessionLocal, get_db
from app.models.container import ContainerStatus
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
logger = logging.getLogger(__name__)

# 活跃重建任务超过该阈值视为孤儿任务，允许在 start 接口自愈回收
REBUILD_TASK_STALE_SECONDS = 300

def _container_status_value(container) -> str | None:
    status = getattr(container, "status", None)
    return getattr(status, "value", status)


async def _sync_container_runtime_state(db: AsyncSession, container) -> object:
    if not container:
        return container
    if _container_status_value(container) != ContainerStatus.RUNNING.value:
        return container
    if not getattr(container, "container_id", None):
        return container

    state = await container_manager.inspect_container_state(container.container_id)
    if state is None:
        container.status = ContainerStatus.STOPPED
        container.error_message = "DOCKER_CONTAINER_NOT_FOUND"
    elif state.get("status") in ("exited", "dead"):
        exit_code = state.get("exit_code")
        state_error = state.get("error")
        container.status = ContainerStatus.STOPPED
        container.error_message = (
            f"docker_status={state.get('status')} exit_code={exit_code}"
            + (f" error={state_error}" if state_error else "")
        )
    else:
        return container

    container.updated_at = datetime.utcnow()
    if object_session(container) is not None:
        await db.commit()
        await db.refresh(container)
    return container


async def _run_rebuild_task(task_id: str, student_id: int, version_id: int) -> None:
    started_at = time.perf_counter()
    async with AsyncSessionLocal() as db:
        task = await crud_task.get_task(db, task_id)
        version = await crud_experiment.get_version(db, version_id)
        if not task or not version:
            logger.error(
                "[SimStartDiag] rebuild_task_bootstrap_missing task_id=%s student_id=%s has_task=%s has_version=%s",
                task_id,
                student_id,
                bool(task),
                bool(version),
            )
            return

        logger.info(
            "[SimStartDiag] rebuild_task_started task_id=%s student_id=%s version_id=%s task_status=%s task_stage=%s",
            task_id,
            student_id,
            version_id,
            getattr(task.status, "value", task.status),
            getattr(task.current_stage, "value", task.current_stage),
        )

        try:
            await crud_task.mark_task_running(db, task=task)
            logger.info(
                "[SimStartDiag] stage_enter task_id=%s stage=%s status=%s",
                task_id,
                SimulationTaskStage.PREPARING_CONFIG.value,
                SimulationTaskStatus.IN_PROGRESS.value,
            )

            await crud_task.mark_stage(
                db,
                task=task,
                stage=SimulationTaskStage.PREPARING_CONFIG,
                status="SUCCEEDED",
                elapsed_ms=10,
            )

            existing = await crud_container.get_container_by_user(db, student_id)
            stop_start = time.perf_counter()
            logger.info(
                "[SimStartDiag] stage_enter task_id=%s stage=%s existing_container_id=%s existing_status=%s",
                task_id,
                SimulationTaskStage.STOPPING_OLD_CONTAINER.value,
                (getattr(existing, "container_id", None) if existing else None),
                (_container_status_value(existing) if existing else None),
            )
            if existing:
                await crud_container.delete_container(db, existing)
            await crud_task.mark_stage(
                db,
                task=task,
                stage=SimulationTaskStage.STOPPING_OLD_CONTAINER,
                status="SUCCEEDED",
                elapsed_ms=int((time.perf_counter() - stop_start) * 1000),
            )

            logger.info(
                "[SimStartDiag] stage_exit task_id=%s stage=%s elapsed_ms=%s",
                task_id,
                SimulationTaskStage.STOPPING_OLD_CONTAINER.value,
                int((time.perf_counter() - stop_start) * 1000),
            )

            create_start = time.perf_counter()
            logger.info(
                "[SimStartDiag] stage_enter task_id=%s stage=%s version_id=%s",
                task_id,
                SimulationTaskStage.CREATING_NEW_CONTAINER.value,
                version_id,
            )
            startup_script_path = None
            env_volumes: dict[str, str] = {}
            if version.env_bundle_id:
                env_bundle = await crud_experiment.get_env_bundle(db, version.env_bundle_id)
                if not env_bundle:
                    raise RuntimeError("MISSING_ENV_BUNDLE")
                startup_script = Path(env_bundle.storage_root) / "startup.sh"
                if not startup_script.exists():
                    raise RuntimeError("MISSING_STARTUP_SCRIPT")
                startup_script_path = str(startup_script)
                env_volumes[env_bundle.storage_root] = env_bundle.container_target_dir

            container = await crud_container.create_container(
                db,
                ContainerCreate(
                    user_id=student_id,
                    image_name=version.image_name,
                    current_version_id=version.id,
                    launch_args=version.launch_args_template or {},
                    startup_script_path=startup_script_path,
                    env_volumes=env_volumes,
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
            logger.info(
                "[SimStartDiag] stage_exit task_id=%s stage=%s elapsed_ms=%s new_container_id=%s new_status=%s",
                task_id,
                SimulationTaskStage.CREATING_NEW_CONTAINER.value,
                int((time.perf_counter() - create_start) * 1000),
                getattr(container, "container_id", None),
                _container_status_value(container),
            )

            health_start = time.perf_counter()

            # 10-S1-8: 拆分健康检测为 CHECKING_GZWEB + CHECKING_ROSBRIDGE
            # 使用模型字段中的宿主机映射端口
            gz_port = getattr(container, "gzbridge_port", None)
            ros_port = getattr(container, "rosbridge_port", None)

            if gz_port:
                await crud_task.mark_stage(
                    db, task=task,
                    stage=SimulationTaskStage.CHECKING_GZWEB,
                    status="IN_PROGRESS", elapsed_ms=0,
                )
                gzweb_ok = False
                gzweb_ms = 0.0
                gz_start = time.perf_counter()
                while (time.perf_counter() - gz_start) < 60.0:
                    state = (
                        await container_manager.inspect_container_state(container.container_id)
                        if container.container_id else None
                    )
                    if state and state.get("status") in ("exited", "dead"):
                        logs_tail = (
                            await container_manager.get_container_logs_tail(container.container_id, tail=80)
                            if container.container_id else None
                        )
                        logger.error(
                            "[SimStartDiag] container exited during CHECKING_GZWEB task_id=%s docker_id=%s container_state=%s logs_tail=%s",
                            task_id,
                            container.container_id,
                            state,
                            (logs_tail[-2000:] if logs_tail else None),
                        )
                        raise RuntimeError("CONTAINER_EXITED_BEFORE_GZWEB_READY")

                    probe_ok, probe_ms = await check_port_ready(
                        "127.0.0.1", gz_port, timeout_s=2.0, interval_s=0.5
                    )
                    gzweb_ms = (time.perf_counter() - gz_start) * 1000
                    if probe_ok:
                        gzweb_ok = True
                        break

                if not gzweb_ok:
                    failed_state = (
                        await container_manager.inspect_container_state(container.container_id)
                        if container.container_id else None
                    )
                    logs_tail = (
                        await container_manager.get_container_logs_tail(container.container_id, tail=60)
                        if container.container_id else None
                    )
                    logger.error(
                        "[SimStartDiag] GZWEB_NOT_READY task_id=%s docker_id=%s elapsed_ms=%s container_state=%s logs_tail=%s",
                        task_id,
                        container.container_id,
                        int(gzweb_ms),
                        failed_state,
                        (logs_tail[-2000:] if logs_tail else None),
                    )
                    raise RuntimeError("GZWEB_NOT_READY")
                await crud_task.mark_stage(
                    db, task=task,
                    stage=SimulationTaskStage.CHECKING_GZWEB,
                    status="SUCCEEDED",
                    elapsed_ms=int(gzweb_ms),
                )

            if ros_port:
                await crud_task.mark_stage(
                    db, task=task,
                    stage=SimulationTaskStage.CHECKING_ROSBRIDGE,
                    status="IN_PROGRESS", elapsed_ms=0,
                )
                ros_ok, ros_ms = await check_rosbridge_ready(ros_port)
                if not ros_ok:
                    failed_state = (
                        await container_manager.inspect_container_state(container.container_id)
                        if container.container_id else None
                    )
                    logs_tail = (
                        await container_manager.get_container_logs_tail(container.container_id, tail=60)
                        if container.container_id else None
                    )
                    logger.error(
                        "[SimStartDiag] ROSBRIDGE_NOT_READY task_id=%s docker_id=%s elapsed_ms=%s container_state=%s logs_tail=%s",
                        task_id,
                        container.container_id,
                        int(ros_ms),
                        failed_state,
                        (logs_tail[-2000:] if logs_tail else None),
                    )
                    raise RuntimeError("ROSBRIDGE_NOT_READY")
                await crud_task.mark_stage(
                    db, task=task,
                    stage=SimulationTaskStage.CHECKING_ROSBRIDGE,
                    status="SUCCEEDED",
                    elapsed_ms=int(ros_ms),
                )

            if not gz_port and not ros_port:
                # 无端口信息时降级为简单状态检查（向后兼容）
                if container.status.value != "running":
                    raise RuntimeError("container health check failed")

            await crud_task.finish_task(
                db,
                task=task,
                status=SimulationTaskStatus.SUCCEEDED,
                elapsed_ms=int((time.perf_counter() - started_at) * 1000),
                retryable=False,
            )
            logger.info(
                "[SimStartDiag] rebuild_task_succeeded task_id=%s student_id=%s total_elapsed_ms=%s final_container_id=%s final_container_status=%s",
                task_id,
                student_id,
                int((time.perf_counter() - started_at) * 1000),
                getattr(container, "container_id", None),
                _container_status_value(container),
            )
        except asyncio.CancelledError:
            logger.error(
                "[SimStartDiag] rebuild_task_cancelled task_id=%s student_id=%s task_status=%s task_stage=%s",
                task_id,
                student_id,
                (getattr(task.status, "value", task.status) if task else None),
                (getattr(task.current_stage, "value", task.current_stage) if task else None),
            )
            try:
                await crud_task.finish_task(
                    db,
                    task=task,
                    status=SimulationTaskStatus.FAILED,
                    elapsed_ms=int((time.perf_counter() - started_at) * 1000),
                    retryable=True,
                    error_code="CONTAINER_REBUILD_CANCELLED",
                    error_message="rebuild task cancelled before completion",
                )
            except Exception as finish_err:
                logger.error(
                    "[SimStartDiag] rebuild_task_cancelled_finish_failed task_id=%s error=%s",
                    task_id,
                    str(finish_err),
                )
            raise
        except Exception as e:
            failed_container = locals().get("container")
            if failed_container is None:
                failed_container = await crud_container.get_container_by_user(db, student_id)
            failed_container = await _sync_container_runtime_state(db, failed_container)
            logger.error(
                "[SimStartDiag] rebuild_failed task_id=%s student_id=%s error=%s failed_container_id=%s failed_container_status=%s failed_container_version_id=%s failed_container_error=%s",
                task_id,
                student_id,
                str(e),
                (getattr(failed_container, "container_id", None) if failed_container else None),
                (_container_status_value(failed_container) if failed_container else None),
                (getattr(failed_container, "current_version_id", None) if failed_container else None),
                (getattr(failed_container, "error_message", None) if failed_container else None),
            )
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


async def _run_docker_cmd(*args: str, timeout: float = 30.0) -> tuple[int, str]:
    """异步执行 docker 子命令，返回 (returncode, output)。"""
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return 124, "docker command timeout"

    output = ((stdout or b"") + (stderr or b"")).decode("utf-8", errors="replace").strip()
    return proc.returncode or 0, output


async def _do_file_distribute(files: list, student_id: int) -> None:
    """实际文件分发操作：将文件包中的文件复制进学生容器。"""
    async with AsyncSessionLocal() as db:
        container = await crud_container.get_container_by_user(db, student_id)

    if not container or not getattr(container, "container_id", None):
        logger.warning("[FileDistributeDiag] skip distribute: no running container student_id=%s", student_id)
        return

    container_id = container.container_id
    target_root = "/home/student/experiment"

    logger.info(
        "[FileDistributeDiag] distribute begin student_id=%s docker_id=%s file_count=%s",
        student_id,
        container_id,
        len(files),
    )

    rc, out = await _run_docker_cmd(
        "docker", "exec", container_id, "mkdir", "-p", target_root,
        timeout=20.0,
    )
    if rc != 0:
        raise RuntimeError(f"prepare target dir failed: {out}")

    for item in files:
        relative_path = str(item.get("relative_path", ""))
        source_abs_path = item.get("source_abs_path")

        if not relative_path or not source_abs_path:
            logger.warning(
                "[FileDistributeDiag] skip file due to missing source metadata relative_path=%s source=%s",
                relative_path,
                source_abs_path,
            )
            continue

        rel_path = Path(relative_path)
        target_file = f"{target_root}/{rel_path.as_posix()}"
        target_parent = str(Path(target_file).parent)

        rc, out = await _run_docker_cmd(
            "docker",
            "exec",
            container_id,
            "bash",
            "-lc",
            f"mkdir -p {shlex.quote(target_parent)}",
            timeout=20.0,
        )
        if rc != 0:
            raise RuntimeError(f"mkdir target parent failed for {relative_path}: {out}")

        rc, out = await _run_docker_cmd(
            "docker",
            "cp",
            str(source_abs_path),
            f"{container_id}:{target_file}",
            timeout=30.0,
        )
        if rc != 0:
            raise RuntimeError(f"docker cp failed for {relative_path}: {out}")


async def _do_set_permissions(student_id: int) -> None:
    """设置容器内 /home/student/experiment 权限。"""
    async with AsyncSessionLocal() as db:
        container = await crud_container.get_container_by_user(db, student_id)

    if not container or not getattr(container, "container_id", None):
        logger.warning("[FileDistributeDiag] skip chmod: no running container student_id=%s", student_id)
        return

    container_id = container.container_id
    cmd = (
        "mkdir -p /home/student/experiment && "
        "chown -R 1000:1000 /home/student/experiment && "
        "chmod -R u+rwX,g+rwX /home/student/experiment"
    )
    rc, out = await _run_docker_cmd("docker", "exec", container_id, "bash", "-lc", cmd, timeout=30.0)
    if rc != 0:
        raise RuntimeError(f"set permissions failed: {out}")


async def _run_distribute_task(task_id: str, student_id: int, files: list) -> None:
    started_at = time.perf_counter()
    async with AsyncSessionLocal() as db:
        task = await crud_task.get_task(db, task_id)
        if not task:
            logger.warning("[FileDistributeDiag] task missing task_id=%s student_id=%s", task_id, student_id)
            return
        try:
            logger.info(
                "[FileDistributeDiag] task started task_id=%s student_id=%s file_count=%s",
                task_id,
                student_id,
                len(files),
            )
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
            logger.error(
                "[FileDistributeDiag] task failed task_id=%s student_id=%s error=%s",
                task_id,
                student_id,
                str(e),
            )
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
    logger.info(
        "[FileDistributeDiag] distribute request student_id=%s version_id=%s mode=%s selected_paths_count=%s",
        student_id,
        data.version_id,
        data.mode,
        len(data.selected_paths),
    )

    # 10-S1-12: 可见性过滤同步移除 is_visible 条件
    version = await crud_experiment.get_version(db, data.version_id)
    if not version or version.publish_status.value != "published":
        raise HTTPException(status_code=404, detail="EXPERIMENT_VERSION_NOT_FOUND")
    from app.models.experiment import ExperimentStatus
    exp = await crud_experiment.get_experiment(db, version.experiment_id)
    if not exp or exp.status != ExperimentStatus.ACTIVE:
        raise HTTPException(status_code=404, detail="EXPERIMENT_VERSION_NOT_FOUND")


    if not version.file_bundle_id:
        raise HTTPException(status_code=400, detail="NO_FILE_BUNDLE_ATTACHED")

    bundle = await crud_experiment.get_bundle(db, version.file_bundle_id)
    if not bundle or bundle.validate_status.value != "valid":
        raise HTTPException(status_code=400, detail="FILE_BUNDLE_NOT_VALID")

    manifest: list = bundle.file_manifest or []

    bundle_root = Path(bundle.storage_root)
    if not bundle_root.exists():
        raise HTTPException(status_code=409, detail="FILE_BUNDLE_STORAGE_MISSING")

    # 路径安全校验（仅在 selected_paths 非空时逐项校验）
    if data.selected_paths:
        _validate_selected_paths(data.selected_paths, manifest)
        selected_set = set(data.selected_paths)
        files_to_distribute = [item for item in manifest if item["relative_path"] in selected_set]
    else:
        # selected_paths=[] 表示全选清单所有文件
        files_to_distribute = list(manifest)

    # 将源文件绝对路径附带到任务参数，避免后台任务再次查询 bundle
    files_to_distribute = [
        {
            **item,
            "source_abs_path": str((bundle_root / item["relative_path"]).resolve()),
        }
        for item in files_to_distribute
    ]

    task = await crud_task.create_task(
        db,
        student_id=student_id,
        target_version_id=version.id,
        container_id=None,
    )

    logger.info(
        "[FileDistributeDiag] task created task_id=%s student_id=%s manifest_count=%s distribute_count=%s",
        task.task_id,
        student_id,
        len(manifest),
        len(files_to_distribute),
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
    # 10-S1-12: 可见性过滤改为 Experiment.status=active + publish_status=published
    # 移除原 is_visible 条件
    version = await crud_experiment.get_version(db, data.version_id)
    if not version or version.publish_status.value != "published":
        raise HTTPException(status_code=404, detail="EXPERIMENT_VERSION_NOT_FOUND")

    # 验证父实验状态为 active
    from app.models.experiment import ExperimentStatus
    exp = await crud_experiment.get_experiment(db, version.experiment_id)
    if not exp or exp.status != ExperimentStatus.ACTIVE:
        raise HTTPException(status_code=404, detail="EXPERIMENT_VERSION_NOT_FOUND")

    if version.env_bundle_id:
        env_bundle = await crud_experiment.get_env_bundle(db, version.env_bundle_id)
        if not env_bundle:
            raise HTTPException(status_code=409, detail="MISSING_ENV_BUNDLE")
        startup_script = Path(env_bundle.storage_root) / "startup.sh"
        if not startup_script.exists():
            raise HTTPException(status_code=409, detail="MISSING_STARTUP_SCRIPT")

    existing = await crud_container.get_container_by_user(db, student_id)
    logger.info(
        "[SimStartDiag] start_simulation request student_id=%s version_id=%s force_recreate=%s existing_container_id=%s existing_status=%s existing_version_id=%s existing_error=%s",
        student_id,
        version.id,
        data.force_recreate,
        (getattr(existing, "container_id", None) if existing else None),
        (_container_status_value(existing) if existing else None),
        (getattr(existing, "current_version_id", None) if existing else None),
        (getattr(existing, "error_message", None) if existing else None),
    )

    # 若容器处于 stopping，先等待其完成，避免“启动即被上一轮 stop 打断”竞态
    if existing and _container_status_value(existing) == ContainerStatus.STOPPING.value:
        for _ in range(12):
            await asyncio.sleep(1)
            await db.refresh(existing)
            existing = await crud_container.get_container_by_user(db, student_id)
            if not existing:
                break
            if _container_status_value(existing) in (ContainerStatus.STOPPED.value, ContainerStatus.ERROR.value):
                break
            if _container_status_value(existing) == ContainerStatus.RUNNING.value:
                # stop 尚未完成但状态回到 running，继续走下方复用判断
                break
        if existing and _container_status_value(existing) == ContainerStatus.STOPPING.value:
            raise HTTPException(status_code=409, detail="CONTAINER_STOPPING_IN_PROGRESS")

    existing = await _sync_container_runtime_state(db, existing)

    if (
        existing
        and not data.force_recreate
        and existing.current_version_id == version.id
        and _container_status_value(existing) == ContainerStatus.RUNNING.value
    ):
        logger.warning(
            "[SimStartDiag] reuse_running_container_without_readiness_check student_id=%s version_id=%s docker_id=%s status=%s error_message=%s",
            student_id,
            version.id,
            getattr(existing, "container_id", None),
            _container_status_value(existing),
            getattr(existing, "error_message", None),
        )
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
        updated_at = getattr(active_task, "updated_at", None)
        task_age_seconds = (
            (datetime.utcnow() - updated_at).total_seconds()
            if updated_at is not None
            else None
        )

        # 自愈：活跃任务超过阈值视为孤儿任务，自动回收后继续启动
        if task_age_seconds is not None and task_age_seconds > REBUILD_TASK_STALE_SECONDS:
            logger.warning(
                "[SimStartDiag] stale_active_task_auto_recovered student_id=%s version_id=%s task_id=%s task_age_seconds=%.2f status=%s stage=%s",
                student_id,
                version.id,
                active_task.task_id,
                task_age_seconds,
                getattr(active_task.status, "value", active_task.status),
                getattr(active_task.current_stage, "value", active_task.current_stage),
            )
            await crud_task.finish_task(
                db,
                task=active_task,
                status=SimulationTaskStatus.FAILED,
                elapsed_ms=getattr(active_task, "elapsed_ms", 0) or 0,
                retryable=True,
                error_code="ORPHAN_TASK_RECOVERED",
                error_message=(
                    f"检测到活跃任务超时未结束（>{REBUILD_TASK_STALE_SECONDS}s），"
                    "已自动回收为失败，可重试"
                ),
            )
            active_task = None

    if active_task:
        latest_task = await crud_task.get_latest_task_by_student(db, student_id)
        logger.error(
            "[SimStartDiag] blocked_by_active_task student_id=%s version_id=%s active_task_id=%s active_status=%s active_stage=%s active_updated_at=%s latest_task_id=%s latest_status=%s latest_updated_at=%s existing_container_id=%s existing_status=%s",
            student_id,
            version.id,
            active_task.task_id,
            getattr(active_task.status, "value", active_task.status),
            getattr(active_task.current_stage, "value", active_task.current_stage),
            getattr(active_task, "updated_at", None),
            (latest_task.task_id if latest_task else None),
            (getattr(latest_task.status, "value", latest_task.status) if latest_task else None),
            (getattr(latest_task, "updated_at", None) if latest_task else None),
            (getattr(existing, "container_id", None) if existing else None),
            (_container_status_value(existing) if existing else None),
        )
        raise HTTPException(status_code=409, detail="CONTAINER_REBUILD_IN_PROGRESS")

    task = await crud_task.create_task(
        db,
        student_id=student_id,
        target_version_id=version.id,
        container_id=getattr(existing, "id", None) if existing else None,
    )

    logger.info(
        "[SimStartDiag] rebuild_task_created task_id=%s student_id=%s version_id=%s existing_container_id=%s",
        task.task_id,
        student_id,
        version.id,
        (getattr(existing, "container_id", None) if existing else None),
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
