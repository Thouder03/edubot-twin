"""
Sidecar 调度执行引擎（第12期 S4）

职责（SDD §7.4）：
  schedule_sidecar(attempt_id)   → 入口：编排快照 → 启动 → 监控 → 结果解析 → 清理
  create_code_snapshot(attempt)  → shutil.copytree 复制 workspace
  build_docker_config(attempt)   → 只按 attempt 快照字段组装 Docker 参数
  start_sidecar(config)          → 调用 Docker SDK 启动
  wait_for_completion(...)       → 等待 exit + 超时 kill
  parse_result_json(...)         → 读取 + Schema 校验
  finalize_attempt(...)          → 写入数据库 + 状态转换
  cleanup_sidecar(container_id)  → docker rm + 保留 artifacts

异步模式：asyncio.create_task + 独立 AsyncSessionLocal（与第10期 _run_rebuild_task 相同模式）
"""

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from docker.errors import APIError, NotFound

from app.core.docker_client import DockerConnectionError, get_docker_client
from app.core.result_parser import ParseError, parse_result_json
from app.core.final_score_calculator import calculate_final_score, get_scoring_mode
from app.core.workspace_snapshot import SnapshotError, create_code_snapshot, get_artifacts_path
from app.crud import exam_attempt as crud_attempt
from app.crud import container as crud_container
from app.core.path_policy import (
    EXAM_EVAL_SCRIPTS_BASE_DIR,
    EXAM_ENV_SNAPSHOTS_BASE_DIR,
    EXAM_FILE_SNAPSHOTS_BASE_DIR,
)
from app.db.database import AsyncSessionLocal
from app.models.exam_attempt import (
    EvidenceEventType,
    ExamAttemptStatus,
)

logger = logging.getLogger(__name__)

# 专用线程池（Sidecar Docker 操作均为同步阻塞调用）
# 每个 sidecar 在等待容器退出期间持续占用 1 个线程（container.wait() 阻塞），
# 因此 max_workers 必须 >= 预期最大并发考试数，否则新考试会排队等待线程释放。
_executor = ThreadPoolExecutor(max_workers=50, thread_name_prefix="sidecar")

# Sidecar 默认镜像（可由 sidecar_policy.image 覆盖）
DEFAULT_SIDECAR_IMAGE = "sidecar-runner:v1"

# Sidecar 容器名前缀
CONTAINER_NAME_PREFIX = "sidecar-exam-"





async def _maybe_prune_lower_attempts(db, attempt) -> None:
    """runtime_policy.highest_objective_only=true 时，仅保留单个客观分最高非错误尝试。"""
    policy = attempt.attempt_runtime_policy_json or {}
    if not bool(policy.get("highest_objective_only", False)):
        return
    deleted = await crud_attempt.prune_lower_non_error_attempts(
        db,
        exam_id=attempt.exam_id,
        student_id=attempt.student_id,
    )
    if deleted:
        logger.info(
            "[Sidecar] highest_objective_only 生效，attempt=%s 清理低分尝试=%s",
            attempt.id,
            deleted,
        )


async def _run_in_executor(func, *args):
    """将同步 Docker 调用包装为异步"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, func, *args)


# ─── Docker 参数构造 ──────────────────────────────────────────────────────────


@dataclass
class SidecarDockerConfig:
    """Sidecar docker run 参数集合（SDD §7.2）"""
    image: str
    name: str
    network_mode: str
    volumes: dict
    environment: dict
    user: str
    cpu_quota: int
    mem_limit: str
    attempt_id: int
    artifacts_path: str


def build_docker_config(attempt, rosbridge_port: Optional[int] = None) -> SidecarDockerConfig:
    """
    只按 attempt 快照字段组装 Docker 参数，不回读 exams 当前配置。

    SDD §7.4 约束：build_docker_config 、超时处理、前端状态展示
    均以 attempt 快照字段为准。

    Args:
        attempt: ExamAttempt ORM 对象
        rosbridge_port: 仿真容器内 rosbridge 实际监听端口（从 SimContainer.rosbridge_port 传入）；
                        为 None 时回退到默认 9090（仅测试/兼容用）
    """
    sidecar_policy = attempt.attempt_sidecar_policy_json or {}
    runtime_policy = attempt.attempt_runtime_policy_json or {}

    image = sidecar_policy.get("image", DEFAULT_SIDECAR_IMAGE)
    cpu_limit = sidecar_policy.get("cpu_limit", 1.0)    # 默认 1 核
    memory_mb = sidecar_policy.get("memory_limit_mb", 512)  # 默认 512MB
    eval_script_id = sidecar_policy.get("eval_script_id")
    env_snapshot_id = sidecar_policy.get("env_snapshot_id")
    file_snapshot_id = sidecar_policy.get("file_snapshot_id")

    attempt_id = attempt.id
    submission_path = attempt.submission_snapshot_path or ""
    artifacts_path = attempt.artifacts_path or str(get_artifacts_path(attempt_id))

    # 约定目录挂载（SDD §7.1）
    volumes: dict = {}

    # 学生代码快照（只读）
    if submission_path:
        volumes[str(Path(submission_path).resolve())] = {"bind": "/opt/submission", "mode": "ro"}

    # artifacts（读写，脚本写入 result.json）
    # 目录已由 workspace_snapshot.create_code_snapshot 创建，此处只挂载
    volumes[str(Path(artifacts_path).resolve())] = {"bind": "/opt/artifacts", "mode": "rw"}

    # 教师测评脚本（只读，若配置了 eval_script_id）
    if eval_script_id:
        eval_script_path = str((EXAM_EVAL_SCRIPTS_BASE_DIR / str(eval_script_id)).resolve())
        volumes[eval_script_path] = {"bind": "/opt/evaluate", "mode": "ro"}

    # 考试环境快照（只读，若配置了 env_snapshot_id）
    if env_snapshot_id:
        env_path = str((EXAM_ENV_SNAPSHOTS_BASE_DIR / str(env_snapshot_id)).resolve())
        volumes[env_path] = {"bind": "/opt/env", "mode": "ro"}

    # 考试文件快照（只读，若配置了 file_snapshot_id）
    if file_snapshot_id:
        file_path = str((EXAM_FILE_SNAPSHOTS_BASE_DIR / str(file_snapshot_id)).resolve())
        volumes[file_path] = {"bind": "/opt/files", "mode": "ro"}

    # 约定环境变量（SDD §7.1）
    environment = {
        "EXAM_ATTEMPT_ID": str(attempt_id),
        "EXAM_MODE": attempt.attempt_exam_mode,
        "EXAM_ID": str(attempt.exam_id),
        "RESULT_PATH": "/opt/artifacts/result.json",
        "ARTIFACTS_DIR": "/opt/artifacts",
        "RUNTIME_POLICY_JSON": json.dumps(runtime_policy),
        "ROSBRIDGE_URL": f"ws://localhost:{rosbridge_port or 9090}",
        "SIM_CONTAINER_NAME": attempt.sim_container_docker_id or "",
        # 容器以 uid=1000 运行，pip --user 需要可写的 HOME
        "HOME": "/tmp",
    }

    # network_mode：共享主仿真容器 network namespace
    if attempt.sim_container_docker_id:
        network_mode = f"container:{attempt.sim_container_docker_id}"
    else:
        network_mode = "bridge"  # fallback

    return SidecarDockerConfig(
        image=image,
        name=f"{CONTAINER_NAME_PREFIX}{attempt_id}",
        network_mode=network_mode,
        volumes=volumes,
        environment=environment,
        user="1000:1000",  # 以宿主机 ubuntu20 的 uid:gid 运行，避免 artifacts 目录权限问题
        cpu_quota=int(cpu_limit * 100000),
        mem_limit=f"{memory_mb}m",
        attempt_id=attempt_id,
        artifacts_path=artifacts_path,
    )


def _docker_run_sidecar(config: SidecarDockerConfig) -> str:
    """
    同步：启动 Sidecar Docker 容器，返回容器 ID。

    Raises:
        DockerConnectionError, APIError
    """
    client = get_docker_client()
    eval_script_id = None  # 从 volumes 找 entry_point
    entry_point = "evaluate.sh"

    # 找出 evaluate 挂载路径以确定入口
    eval_bind = config.volumes.get(
        next((k for k in config.volumes if "eval_scripts" in k), ""), {}
    )

    container = client.containers.run(
        image=config.image,
        name=config.name,
        network_mode=config.network_mode,
        volumes=config.volumes,
        environment=config.environment,
        user=config.user,
        cpu_quota=config.cpu_quota,
        mem_limit=config.mem_limit,
        command=f"bash /opt/evaluate/{entry_point}",
        detach=True,
        auto_remove=False,      # 后端显式 docker rm，便于读取 exit_code
        read_only=False,        # /opt/artifacts 需要写权限，read_only 需要更复杂挂载
        cap_drop=["ALL"],
        security_opt=["no-new-privileges"],
    )
    return container.id[:12]


def _docker_wait_container(container_id: str, timeout_seconds: int) -> tuple[int, str]:
    """
    同步：等待容器退出，返回 (exit_code, stderr_tail)。

    Args:
        container_id: 容器 ID
        timeout_seconds: 超时秒数

    Returns:
        (exit_code, stderr)
    """
    client = get_docker_client()
    try:
        container = client.containers.get(container_id)
        result = container.wait(timeout=timeout_seconds)
        exit_code = result.get("StatusCode", -1)
        # 获取最后 1000 字符的 stdout+stderr（evaluate.py 用 print 输出到 stdout）
        try:
            logs = container.logs(stdout=True, stderr=True, tail=100)
            stderr = logs.decode("utf-8", errors="replace")[-1000:]
        except Exception:
            stderr = ""
        return exit_code, stderr
    except Exception as e:
        return -1, str(e)


def _docker_kill_container(container_id: str) -> None:
    """同步：强制 kill 容器"""
    client = get_docker_client()
    try:
        container = client.containers.get(container_id)
        container.kill()
    except NotFound:
        pass
    except Exception as e:
        logger.warning(f"[Sidecar] kill {container_id} 失败: {e}")


def _docker_remove_container(container_id: str) -> None:
    """同步：删除容器（docker rm），保留 artifacts"""
    client = get_docker_client()
    try:
        container = client.containers.get(container_id)
        container.remove(force=True)
        logger.info(f"[Sidecar] 容器 {container_id} 已删除")
    except NotFound:
        pass
    except Exception as e:
        logger.warning(f"[Sidecar] rm {container_id} 失败（将由自愈扫描重试）: {e}")


# ─── 主编排流程 ──────────────────────────────────────────────────────────────


async def schedule_sidecar(attempt_id: int) -> None:
    """
    入口：编排快照 → 启动 → 监控 → 结果解析 → 清理。

    异步执行，采用独立 AsyncSessionLocal（不依赖调用方的 DB session）。
    调用方应通过 asyncio.create_task(schedule_sidecar(attempt_id)) 非阻塞触发。
    """
    async with AsyncSessionLocal() as db:
        attempt = await crud_attempt.get_attempt(db, attempt_id)
        if attempt is None:
            logger.error(f"[Sidecar] attempt {attempt_id} 不存在，调度中止")
            return

        logger.info(
            f"[Sidecar] 开始调度 attempt={attempt_id} "
            f"exam={attempt.exam_id} student={attempt.student_id}"
        )

        # ── 1. 代码快照 ────────────────────────────────────────────────────────
        await crud_attempt.record_event(
            db, attempt_id=attempt_id,
            event_type=EvidenceEventType.CODE_SNAPSHOT_STARTED,
            payload={"student_id": attempt.student_id},
        )

        # 从固化的 sidecar_policy 中取 submission_paths（第14期：评测文件范围控制）
        sidecar_policy = attempt.attempt_sidecar_policy_json or {}
        submission_paths: Optional[list[str]] = sidecar_policy.get("submission_paths") or None

        try:
            snapshot_result = await _run_in_executor(
                create_code_snapshot, attempt_id, attempt.student_id, submission_paths
            )
        except SnapshotError as e:
            logger.error(f"[Sidecar] 快照失败 attempt={attempt_id}: {e}")
            await crud_attempt.record_event(
                db, attempt_id=attempt_id,
                event_type=EvidenceEventType.CODE_SNAPSHOT_FAILED,
                payload={"error": str(e)},
            )
            attempt = await crud_attempt.update_attempt_status(
                db, attempt, ExamAttemptStatus.ERROR,
                error_code=e.error_code,
                error_message=str(e),
            )
            await crud_attempt.record_event(
                db, attempt_id=attempt_id,
                event_type=EvidenceEventType.EXAM_ATTEMPT_FINALIZED,
                payload={"final_status": "error"},
            )
            return
        except Exception as e:
            logger.error(f"[Sidecar] 快照异常 attempt={attempt_id}: {e}")
            attempt = await crud_attempt.update_attempt_status(
                db, attempt, ExamAttemptStatus.ERROR,
                error_code="SNAPSHOT_FAILED",
                error_message=str(e),
            )
            return

        # 更新 attempt 路径
        attempt = await crud_attempt.update_attempt_status(
            db, attempt, ExamAttemptStatus.PENDING,
            submission_snapshot_path=snapshot_result.snapshot_path,
            artifacts_path=snapshot_result.artifacts_path,
        )

        await crud_attempt.record_event(
            db, attempt_id=attempt_id,
            event_type=EvidenceEventType.CODE_SNAPSHOT_CREATED,
            payload={
                "file_count": snapshot_result.file_count,
                "total_bytes": snapshot_result.total_bytes,
                "snapshot_path": snapshot_result.snapshot_path,
            },
        )

        # ── 2. 构建 Docker 参数并启动 Sidecar ─────────────────────────────────
        # 从关联的 SimContainer 取出实际 rosbridge 端口（非默认 9090）
        rosbridge_port: Optional[int] = None
        if attempt.container_id:
            sim_container = await crud_container.get_container(db, attempt.container_id)
            if sim_container:
                rosbridge_port = sim_container.rosbridge_port

        config = build_docker_config(attempt, rosbridge_port=rosbridge_port)
        sidecar_docker_id: Optional[str] = None

        try:
            sidecar_docker_id = await _run_in_executor(_docker_run_sidecar, config)
        except (DockerConnectionError, APIError, Exception) as e:
            logger.error(f"[Sidecar] 启动失败 attempt={attempt_id}: {e}")
            await crud_attempt.record_event(
                db, attempt_id=attempt_id,
                event_type=EvidenceEventType.SIDECAR_START_FAILED,
                payload={"error": str(e)},
            )
            attempt = await crud_attempt.update_attempt_status(
                db, attempt, ExamAttemptStatus.ERROR,
                error_code="SIDECAR_START_FAILED",
                error_message=str(e),
            )
            await crud_attempt.record_event(
                db, attempt_id=attempt_id,
                event_type=EvidenceEventType.EXAM_ATTEMPT_FINALIZED,
                payload={"final_status": "error"},
            )
            return

        # 更新为 running 状态
        attempt = await crud_attempt.update_attempt_status(
            db, attempt, ExamAttemptStatus.RUNNING,
            started_at=datetime.utcnow(),
            sidecar_container_id=sidecar_docker_id,
        )

        await crud_attempt.record_event(
            db, attempt_id=attempt_id,
            event_type=EvidenceEventType.SIDECAR_CONTAINER_CREATED,
            payload={"docker_id": sidecar_docker_id, "image": config.image},
        )

        # ── 3. 等待 Sidecar 完成（在新 DB session 中，避免 session 超时） ──────
    # 关闭外层 session，下面用独立 session 轮询

    await _wait_and_finalize(attempt_id, sidecar_docker_id, config)


async def _wait_and_finalize(
    attempt_id: int,
    sidecar_docker_id: str,
    config: SidecarDockerConfig,
) -> None:
    """等待 Sidecar 完成，解析结果，写入数据库（独立 DB session）"""
    async with AsyncSessionLocal() as db:
        attempt = await crud_attempt.get_attempt(db, attempt_id)
        if attempt is None:
            return

        # 获取超时时限
        runtime_policy = attempt.attempt_runtime_policy_json or {}
        max_duration_ms = runtime_policy.get("max_duration_ms", 600000)
        timeout_seconds = int(max_duration_ms / 1000) + 30  # 30s 缓冲

        # 等待容器退出
        try:
            exit_code, stderr = await asyncio.wait_for(
                _run_in_executor(_docker_wait_container, sidecar_docker_id, timeout_seconds),
                timeout=timeout_seconds + 10,  # asyncio 超时额外宽裕 10s
            )
        except asyncio.TimeoutError:
            # asyncio 层超时（应该由 sidecar_timeout_scanner 处理，此处作为 fallback）
            logger.warning(f"[Sidecar] asyncio 超时 attempt={attempt_id}")
            await _handle_timeout(db, attempt, sidecar_docker_id)
            return

        elapsed_ms = 0
        if attempt.started_at:
            delta = datetime.utcnow() - attempt.started_at
            elapsed_ms = int(delta.total_seconds() * 1000)

        await crud_attempt.record_event(
            db, attempt_id=attempt_id,
            event_type=EvidenceEventType.SIDECAR_SCRIPT_FINISHED,
            payload={"exit_code": exit_code, "elapsed_ms": elapsed_ms},
        )

        # ── 4. 检查 exit code ────────────────────────────────────────────────
        if exit_code != 0:
            logger.error(f"[Sidecar] 脚本非 0 退出 attempt={attempt_id} exit={exit_code}")
            await crud_attempt.record_event(
                db, attempt_id=attempt_id,
                event_type=EvidenceEventType.SYSTEM_ERROR,
                payload={"code": "SCRIPT_FAILED", "message": stderr[:500]},
            )
            attempt = await crud_attempt.finalize_attempt(
                db, attempt,
                status=ExamAttemptStatus.ERROR,
                error_code="SCRIPT_FAILED",
                error_message=f"exit_code={exit_code} stderr={stderr[:300]}",
            )
            await crud_attempt.record_event(
                db, attempt_id=attempt_id,
                event_type=EvidenceEventType.EXAM_ATTEMPT_FINALIZED,
                payload={"final_status": "error"},
            )
            await _run_in_executor(_docker_remove_container, sidecar_docker_id)
            return

        # ── 5. 解析 result.json ───────────────────────────────────────────────
        # 更新为 scoring 状态
        attempt = await crud_attempt.update_attempt_status(
            db, attempt, ExamAttemptStatus.SCORING,
        )

        try:
            parse_result = await _run_in_executor(
                parse_result_json, config.artifacts_path
            )
        except ParseError as e:
            logger.error(f"[Sidecar] JSON 解析失败 attempt={attempt_id}: {e}")
            event_type = {
                "RESULT_MISSING_FILE": EvidenceEventType.INVALID_RESULT_JSON,
                "RESULT_INVALID_JSON": EvidenceEventType.INVALID_RESULT_JSON,
                "RESULT_MISSING_FIELDS": EvidenceEventType.RESULT_MISSING_FIELDS,
                "RESULT_TOO_LARGE": EvidenceEventType.INVALID_RESULT_JSON,
            }.get(e.error_code, EvidenceEventType.SYSTEM_ERROR)

            await crud_attempt.record_event(
                db, attempt_id=attempt_id,
                event_type=event_type,
                payload={"error": str(e), "error_code": e.error_code},
            )
            attempt = await crud_attempt.finalize_attempt(
                db, attempt,
                status=ExamAttemptStatus.ERROR,
                error_code=e.error_code,
                error_message=str(e),
            )
            await crud_attempt.record_event(
                db, attempt_id=attempt_id,
                event_type=EvidenceEventType.EXAM_ATTEMPT_FINALIZED,
                payload={"final_status": "error"},
            )
            await _run_in_executor(_docker_remove_container, sidecar_docker_id)
            return

        # 记录 clamp warning
        if parse_result.score_clamped:
            await crud_attempt.record_event(
                db, attempt_id=attempt_id,
                event_type=EvidenceEventType.SYSTEM_WARNING,
                payload={
                    "code": "SCORE_CLAMPED",
                    "message": f"objective_score 超出 [0,100]，已 clamp 至 {parse_result.objective_score}",
                },
            )

        # ── 6. 固化结果 ───────────────────────────────────────────────────────
        artifact_index = parse_result.artifacts or {}

        # 业务规则：0分属于评测异常，按 error 入库
        if parse_result.objective_score == 0:
            await crud_attempt.record_event(
                db, attempt_id=attempt_id,
                event_type=EvidenceEventType.SYSTEM_ERROR,
                payload={
                    "code": "OBJECTIVE_SCORE_ZERO",
                    "message": "客观分为0，按评测异常处理",
                },
            )
            attempt = await crud_attempt.finalize_attempt(
                db,
                attempt,
                status=ExamAttemptStatus.ERROR,
                objective_score=parse_result.objective_score,
                pass_=False,
                summary=parse_result.summary,
                result_json=parse_result.raw,
                custom_fields_json=parse_result.custom_fields,
                artifact_index_json=artifact_index,
                error_code="OBJECTIVE_SCORE_ZERO",
                error_message="客观分为0，按评测异常处理",
            )
            await crud_attempt.record_event(
                db,
                attempt_id=attempt_id,
                event_type=EvidenceEventType.EXAM_ATTEMPT_FINALIZED,
                payload={"final_status": "error"},
            )
        else:
            # objective_only 模式：直接以客观分作为最终成绩，无需等待人工评分
            scoring_policy = attempt.attempt_scoring_policy_json or {}
            auto_final_score: Optional[float] = None
            if get_scoring_mode(scoring_policy) == "objective_only":
                auto_final_score, _ = calculate_final_score(
                    objective_score=parse_result.objective_score,
                    manual_score=None,
                    scoring_policy=scoring_policy,
                )

            attempt = await crud_attempt.finalize_attempt(
                db, attempt,
                status=ExamAttemptStatus.COMPLETED,
                objective_score=parse_result.objective_score,
                pass_=parse_result.pass_,
                summary=parse_result.summary,
                result_json=parse_result.raw,
                custom_fields_json=parse_result.custom_fields,
                artifact_index_json=artifact_index,
                final_score=auto_final_score,
            )

            await crud_attempt.record_event(
                db, attempt_id=attempt_id,
                event_type=EvidenceEventType.SCORING_COMPLETED,
                payload={
                    "objective_score": parse_result.objective_score,
                    "pass": parse_result.pass_,
                    "final_score": auto_final_score,
                    "scoring_mode": get_scoring_mode(scoring_policy),
                },
            )
            await crud_attempt.record_event(
                db, attempt_id=attempt_id,
                event_type=EvidenceEventType.EXAM_ATTEMPT_FINALIZED,
                payload={"final_status": "completed"},
            )

            await _maybe_prune_lower_attempts(db, attempt)

        logger.info(
            f"[Sidecar] 评测完成 attempt={attempt_id} "
            f"score={parse_result.objective_score} pass={parse_result.pass_}"
        )

    # ── 7. 清理容器（在 DB session 关闭后）──────────────────────────────────
    await _run_in_executor(_docker_remove_container, sidecar_docker_id)


async def _handle_timeout(db, attempt, sidecar_docker_id: Optional[str]) -> None:
    """处理 Sidecar 超时（kill + 更新状态）"""
    elapsed_ms = 0
    if attempt.started_at:
        delta = datetime.utcnow() - attempt.started_at
        elapsed_ms = int(delta.total_seconds() * 1000)

    policy = attempt.attempt_runtime_policy_json or {}
    limit_ms = policy.get("max_duration_ms", 600000)

    if sidecar_docker_id:
        await _run_in_executor(_docker_kill_container, sidecar_docker_id)

    await crud_attempt.record_event(
        db, attempt_id=attempt.id,
        event_type=EvidenceEventType.TIMEOUT_REACHED,
        payload={"elapsed_ms": elapsed_ms, "limit_ms": limit_ms},
    )
    await crud_attempt.finalize_attempt(
        db, attempt,
        status=ExamAttemptStatus.ABORTED,
        error_code="SIDECAR_TIMEOUT",
        error_message=f"Sidecar 超时（limit={limit_ms}ms, elapsed={elapsed_ms}ms）",
    )
    await crud_attempt.record_event(
        db, attempt_id=attempt.id,
        event_type=EvidenceEventType.EXAM_ATTEMPT_FINALIZED,
        payload={"final_status": "aborted"},
    )

    if sidecar_docker_id:
        await _run_in_executor(_docker_remove_container, sidecar_docker_id)


async def kill_timeout_sidecar(attempt_id: int) -> None:
    """
    超时终止接口（由 sidecar_timeout_scanner 调用）。

    对 status=running 的 attempt 执行强制终止流程。
    """
    async with AsyncSessionLocal() as db:
        attempt = await crud_attempt.get_attempt(db, attempt_id)
        if attempt is None or attempt.status != ExamAttemptStatus.RUNNING:
            return
        await _handle_timeout(db, attempt, attempt.sidecar_container_id)
