"""
container_lifecycle — 通用容器生命周期编排模块（第12期-补充）

将原 _run_rebuild_task 的核心逻辑抽象为参数化的生命周期函数，
同时支持仿真（实验版本）和考试两种启动来源。

导出：
  ContainerBuildParams         容器构建参数 dataclass
  run_container_lifecycle      通用生命周期编排（后台任务）
  build_params_from_version    从实验版本构建参数（仿真模式）
  build_params_from_exam       从考试定义构建参数（考试模式）
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from sqlalchemy.orm import object_session
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.readiness_checker import check_port_ready, check_rosbridge_ready
from app.core import container_manager
from app.crud import container as crud_container
from app.crud import simulation_task as crud_task
from app.db.database import AsyncSessionLocal
from app.models.container import ContainerStatus
from app.models.simulation_task import SimulationTaskStage, SimulationTaskStatus
from app.schemas.container import ContainerCreate

if TYPE_CHECKING:
    from app.models.experiment import ExperimentVersion, ExperimentEnvBundle
    from app.models.exam import Exam

logger = logging.getLogger(__name__)


# ─── 参数对象 ──────────────────────────────────────────────────────────────────


@dataclass
class ContainerBuildParams:
    """容器构建参数（适配仿真/考试两种来源）"""
    student_id: int
    image_name: str = "gzweb_sim:v1"
    launch_args: dict[str, str] = field(default_factory=dict)
    startup_script_path: Optional[str] = None
    env_volumes: dict[str, str] = field(default_factory=dict)
    purpose: str = ""
    current_version_id: Optional[int] = None


# ─── 内部辅助函数 ──────────────────────────────────────────────────────────────


def _container_status_value(container) -> Optional[str]:
    status = getattr(container, "status", None)
    return getattr(status, "value", status)


async def _sync_container_runtime_state(db: AsyncSession, container) -> object:
    """将运行时 Docker 状态同步到 DB（同 simulation.py 中的同名函数）"""
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


# ─── 核心生命周期编排 ──────────────────────────────────────────────────────────


async def run_container_lifecycle(
    task_id: str,
    params: ContainerBuildParams,
) -> None:
    """
    通用容器生命周期编排（后台任务，由 asyncio.create_task 调用）。

    流程：
      1. PREPARING_CONFIG   → 参数校验（已在调用前完成，此处标记 SUCCEEDED）
      2. STOPPING_OLD       → 删除已有容器
      3. CREATING_NEW       → 创建并启动 Docker 容器 + 写入 purpose
      4. CHECKING_GZWEB     → GzWeb 端口健康检查
      5. CHECKING_ROSBRIDGE → RosBridge 健康检查

    :param task_id: SimulationTask 任务 ID
    :param params:  容器构建参数
    """
    started_at = time.perf_counter()
    async with AsyncSessionLocal() as db:
        task = await crud_task.get_task(db, task_id)
        if not task:
            logger.error(
                "[ContainerLifecycle] task_missing task_id=%s student_id=%s",
                task_id, params.student_id,
            )
            return

        logger.info(
            "[ContainerLifecycle] lifecycle_started task_id=%s student_id=%s purpose=%s",
            task_id, params.student_id, params.purpose,
        )

        try:
            await crud_task.mark_task_running(db, task=task)

            # ── PREPARING_CONFIG ──────────────────────────────────────────────
            await crud_task.mark_stage(
                db, task=task,
                stage=SimulationTaskStage.PREPARING_CONFIG,
                status="SUCCEEDED", elapsed_ms=10,
            )

            # ── STOPPING_OLD_CONTAINER ────────────────────────────────────────
            existing = await crud_container.get_container_by_user(db, params.student_id)
            stop_start = time.perf_counter()
            logger.info(
                "[ContainerLifecycle] stopping_old task_id=%s existing_container_id=%s existing_status=%s",
                task_id,
                (getattr(existing, "container_id", None) if existing else None),
                (_container_status_value(existing) if existing else None),
            )
            if existing:
                await crud_container.delete_container(db, existing)
            await crud_task.mark_stage(
                db, task=task,
                stage=SimulationTaskStage.STOPPING_OLD_CONTAINER,
                status="SUCCEEDED",
                elapsed_ms=int((time.perf_counter() - stop_start) * 1000),
            )

            # ── CREATING_NEW_CONTAINER ────────────────────────────────────────
            create_start = time.perf_counter()
            logger.info(
                "[ContainerLifecycle] creating_new task_id=%s image=%s purpose=%s",
                task_id, params.image_name, params.purpose,
            )
            container = await crud_container.create_container(
                db,
                ContainerCreate(
                    user_id=params.student_id,
                    image_name=params.image_name,
                    current_version_id=params.current_version_id,
                    launch_args=params.launch_args,
                    startup_script_path=params.startup_script_path,
                    env_volumes=params.env_volumes,
                    purpose=params.purpose,
                ),
            )
            if container.status.value == "error":
                raise RuntimeError(container.error_message or "container create failed")

            await crud_task.mark_stage(
                db, task=task,
                stage=SimulationTaskStage.CREATING_NEW_CONTAINER,
                status="SUCCEEDED",
                elapsed_ms=int((time.perf_counter() - create_start) * 1000),
            )
            logger.info(
                "[ContainerLifecycle] container_created task_id=%s docker_id=%s status=%s",
                task_id,
                getattr(container, "container_id", None),
                _container_status_value(container),
            )

            # ── CHECKING_GZWEB ────────────────────────────────────────────────
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
                            "[ContainerLifecycle] container_exited_during_CHECKING_GZWEB task_id=%s docker_id=%s logs_tail=%s",
                            task_id, container.container_id,
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
                        "[ContainerLifecycle] GZWEB_NOT_READY task_id=%s docker_id=%s elapsed_ms=%s logs_tail=%s",
                        task_id, container.container_id, int(gzweb_ms),
                        (logs_tail[-2000:] if logs_tail else None),
                    )
                    raise RuntimeError("GZWEB_NOT_READY")
                await crud_task.mark_stage(
                    db, task=task,
                    stage=SimulationTaskStage.CHECKING_GZWEB,
                    status="SUCCEEDED",
                    elapsed_ms=int(gzweb_ms),
                )

            # ── CHECKING_ROSBRIDGE ────────────────────────────────────────────
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
                        "[ContainerLifecycle] ROSBRIDGE_NOT_READY task_id=%s docker_id=%s elapsed_ms=%s logs_tail=%s",
                        task_id, container.container_id, int(ros_ms),
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
                db, task=task,
                status=SimulationTaskStatus.SUCCEEDED,
                elapsed_ms=int((time.perf_counter() - started_at) * 1000),
                retryable=False,
            )
            logger.info(
                "[ContainerLifecycle] lifecycle_succeeded task_id=%s student_id=%s purpose=%s total_ms=%s docker_id=%s",
                task_id, params.student_id, params.purpose,
                int((time.perf_counter() - started_at) * 1000),
                getattr(container, "container_id", None),
            )

        except asyncio.CancelledError:
            logger.error(
                "[ContainerLifecycle] lifecycle_cancelled task_id=%s student_id=%s",
                task_id, params.student_id,
            )
            try:
                await crud_task.finish_task(
                    db, task=task,
                    status=SimulationTaskStatus.FAILED,
                    elapsed_ms=int((time.perf_counter() - started_at) * 1000),
                    retryable=True,
                    error_code="CONTAINER_REBUILD_CANCELLED",
                    error_message="lifecycle task cancelled before completion",
                )
            except Exception as finish_err:
                logger.error(
                    "[ContainerLifecycle] cancelled_finish_failed task_id=%s error=%s",
                    task_id, str(finish_err),
                )
            raise

        except Exception as e:
            failed_container = locals().get("container")
            if failed_container is None:
                failed_container = await crud_container.get_container_by_user(db, params.student_id)
            failed_container = await _sync_container_runtime_state(db, failed_container)
            logger.error(
                "[ContainerLifecycle] lifecycle_failed task_id=%s student_id=%s error=%s docker_id=%s container_status=%s",
                task_id, params.student_id, str(e),
                (getattr(failed_container, "container_id", None) if failed_container else None),
                (_container_status_value(failed_container) if failed_container else None),
            )
            await crud_task.mark_stage(
                db, task=task,
                stage=task.current_stage,
                status="FAILED", elapsed_ms=0,
                error_code="CONTAINER_REBUILD_FAILED",
                error_message=str(e),
            )
            await crud_task.finish_task(
                db, task=task,
                status=SimulationTaskStatus.FAILED,
                elapsed_ms=int((time.perf_counter() - started_at) * 1000),
                retryable=True,
                error_code="CONTAINER_REBUILD_FAILED",
                error_message=str(e),
            )


# ─── 参数构建辅助函数 ──────────────────────────────────────────────────────────


def build_params_from_version(
    student_id: int,
    version: "ExperimentVersion",
    env_bundle: Optional["ExperimentEnvBundle"],
    experiment_name: str = "",
) -> ContainerBuildParams:
    """
    从实验版本构建容器参数（仿真模式）。

    purpose 格式：「实验：{experiment_name} / {version.version_name}」
    """
    startup_script_path: Optional[str] = None
    env_volumes: dict[str, str] = {}

    if env_bundle:
        startup_script = Path(env_bundle.storage_root) / "startup.sh"
        startup_script_path = str(startup_script)
        env_volumes[env_bundle.storage_root] = env_bundle.container_target_dir

    purpose = f"实验：{experiment_name} / {version.version_name}" if experiment_name else f"实验：{version.version_name}"

    return ContainerBuildParams(
        student_id=student_id,
        image_name=version.image_name,
        launch_args=version.launch_args_template or {},
        startup_script_path=startup_script_path,
        env_volumes=env_volumes,
        purpose=purpose,
        current_version_id=version.id,
    )


async def build_params_from_exam(
    db: AsyncSession,
    student_id: int,
    exam: "Exam",
) -> ContainerBuildParams:
    """
    从考试定义构建容器参数（考试模式）。

    purpose 格式：「考试：{exam.name}」

    参数读取优先级：
      1. exam.runtime_policy_json.image → image_name（若未配置则使用默认镜像）
      2. ExamEnvSnapshot（若 exam.env_snapshot_id 存在）→ startup_script_path + env_volumes
    """
    from app.crud import exam_env_snapshot as crud_env_snapshot

    runtime_policy = exam.runtime_policy_json or {}
    image_name: str = runtime_policy.get("image", "gzweb_sim:v1")
    launch_args: dict[str, str] = runtime_policy.get("launch_args", {})

    startup_script_path: Optional[str] = None
    env_volumes: dict[str, str] = {}

    if exam.env_snapshot_id:
        snapshot = await crud_env_snapshot.get_env_snapshot(db, exam.env_snapshot_id)
        if snapshot:
            startup_script = Path(snapshot.storage_root) / "startup.sh"
            startup_script_path = str(startup_script)
            env_volumes[snapshot.storage_root] = snapshot.container_target_dir

    return ContainerBuildParams(
        student_id=student_id,
        image_name=image_name,
        launch_args=launch_args,
        startup_script_path=startup_script_path,
        env_volumes=env_volumes,
        purpose=f"考试：{exam.name}",
        current_version_id=None,
    )
