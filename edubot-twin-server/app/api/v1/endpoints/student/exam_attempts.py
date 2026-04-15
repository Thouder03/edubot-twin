"""
学生端考试运行 API（第12期 S6）

路由前缀：/api/v1/students/
  GET  /exams                              → 获取已发布考试列表（学生首页选考试用）
  GET  /exams/{exam_id}                    → 获取考试运行信息（ExamRunInfo）
  GET  /exams/{exam_id}/my-attempts        → 获取我的尝试列表
  POST /exam-attempts                      → 创建考试尝试（status=pending）
  POST /exam-attempts/{id}/start           → 开始考试（代码快照 + 启动 Sidecar）
  GET  /exam-attempts/{id}                 → 查询尝试详情
  POST /exam-attempts/{id}/abort           → 学生主动放弃
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user_id
from app.crud import exam_attempt as crud_attempt
from app.crud import container as crud_container
from app.crud import exam as crud_exam
from app.db.database import get_db
from app.models.container import ContainerStatus
from app.models.exam import ExamMode, ExamStatus
from app.models.exam_attempt import ExamAttemptStatus, EvidenceEventType
from app.schemas.common import ApiResponse
from app.schemas.exam_attempt import (
    AbortAttemptRequest,
    AttemptListResponse,
    CreateAttemptRequest,
    CreateAttemptResponse,
    ExamRunInfoSchema,
    RuntimePolicySchema,
    StudentAttemptDetailSchema,
    StudentAttemptSummarySchema,
)
from app.core.sidecar_manager import schedule_sidecar
from app.models.exam import Exam
from pydantic import BaseModel
from sqlalchemy import select

router = APIRouter()
logger = logging.getLogger(__name__)

# 本期只支持 result_run 模式
SUPPORTED_EXAM_MODES = {ExamMode.RESULT_RUN.value}


class ExamListItemSchema(BaseModel):
    """学生端可参加的考试列表条目"""
    exam_id: int
    name: str
    code: str
    description: Optional[str] = None
    exam_mode: str
    time_limit_ms: int
    max_attempts: int


def _build_exam_run_info(exam, remaining_attempts: int) -> ExamRunInfoSchema:
    """从 Exam ORM 对象构建 ExamRunInfo"""
    runtime_policy = exam.runtime_policy_json or {}
    return ExamRunInfoSchema(
        exam_id=exam.id,
        name=exam.name,
        description=exam.description,
        exam_mode=exam.exam_mode.value,
        runtime_policy=RuntimePolicySchema(**runtime_policy),
        panel_policy=exam.panel_policy_json or {},
        time_limit_ms=runtime_policy.get("max_duration_ms", 600000),
        remaining_attempts=remaining_attempts,
    )


def _build_student_detail(attempt) -> StudentAttemptDetailSchema:
    """从 ORM 对象构建 StudentAttemptDetailSchema"""
    return StudentAttemptDetailSchema(
        attempt_id=attempt.id,
        exam_id=attempt.exam_id,
        status=attempt.status.value,
        attempt_exam_mode=attempt.attempt_exam_mode,
        started_at=attempt.started_at,
        ended_at=attempt.ended_at,
        duration_ms=attempt.duration_ms,
        objective_score=attempt.objective_score,
        **{"pass": attempt.pass_},
        summary=attempt.summary,
        result_json=attempt.result_json,
        error_code=attempt.error_code,
        error_message=attempt.error_message,
        created_at=attempt.created_at,
        updated_at=attempt.updated_at,
    )


# ─── GET /students/exams（已发布考试列表） ────────────────────────────────────


@router.get(
    "/exams",
    response_model=ApiResponse[list[ExamListItemSchema]],
    summary="获取可参加的已发布考试列表（学生首页用）",
)
async def list_published_exams(
    _user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """返回全部已发布（published）且模式为 result_run 的考试，供学生首页选择。"""
    result = await db.execute(
        select(Exam)
        .where(Exam.status == ExamStatus.PUBLISHED)
        .order_by(Exam.created_at.desc())
    )
    exams = list(result.scalars().all())
    items = []
    for exam in exams:
        policy = exam.runtime_policy_json or {}
        items.append(ExamListItemSchema(
            exam_id=exam.id,
            name=exam.name,
            code=exam.code,
            description=exam.description,
            exam_mode=exam.exam_mode.value,
            time_limit_ms=policy.get("max_duration_ms", 600000),
            max_attempts=policy.get("max_attempts", 3),
        ))
    return ApiResponse(code=0, data=items)


# ─── GET /students/exams/{exam_id} ───────────────────────────────────────────


@router.get(
    "/exams/{exam_id}",
    response_model=ApiResponse[ExamRunInfoSchema],
    summary="获取考试运行信息（学生进入考试页）",
)
async def get_exam_run_info(
    exam_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    学生进入考试模式时获取考试配置。

    - 考试必须处于 published 状态
    - 本期只支持 result_run 模式
    """
    exam = await crud_exam.get_exam(db, exam_id)
    if exam is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "EXAM_NOT_FOUND", "message": "考试不存在"},
        )

    if exam.status != ExamStatus.PUBLISHED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error_code": "EXAM_NOT_PUBLISHED", "message": "考试尚未发布"},
        )

    if exam.exam_mode.value not in SUPPORTED_EXAM_MODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "EXAM_MODE_NOT_SUPPORTED_YET",
                "message": f"该考试模式（{exam.exam_mode.value}）将在后续期次开放",
            },
        )

    runtime_policy = exam.runtime_policy_json or {}
    max_attempts = runtime_policy.get("max_attempts", 3)
    used_attempts = await crud_attempt.count_all_attempts(db, user_id, exam_id)
    remaining = max(0, max_attempts - used_attempts)

    return ApiResponse(
        code=0,
        data=_build_exam_run_info(exam, remaining),
    )


# ─── GET /students/exams/{exam_id}/my-attempts ────────────────────────────────


@router.get(
    "/exams/{exam_id}/my-attempts",
    response_model=ApiResponse[AttemptListResponse],
    summary="获取我对该考试的全部尝试",
)
async def get_my_attempts(
    exam_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    attempts = await crud_attempt.list_student_attempts(db, user_id, exam_id)
    items = [StudentAttemptSummarySchema.from_orm(a) for a in attempts]
    return ApiResponse(
        code=0,
        data=AttemptListResponse(
            items=[i.model_dump(by_alias=True) for i in items],
            total=len(items),
            page=1,
            page_size=len(items),
        ),
    )


# ─── POST /students/exam-attempts ─────────────────────────────────────────────


@router.post(
    "/exam-attempts",
    response_model=ApiResponse[CreateAttemptResponse],
    status_code=status.HTTP_201_CREATED,
    summary="创建考试尝试（status=pending）",
)
async def create_attempt(
    body: CreateAttemptRequest,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    创建考试尝试记录。

    校验顺序：
    1. 考试已发布且 exam_mode=result_run
    2. 学生容器正在运行
    3. 无进行中的 attempt
    4. 未超出最大尝试次数
    """
    exam = await crud_exam.get_exam(db, body.exam_id)
    if exam is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "EXAM_NOT_FOUND", "message": "考试不存在"},
        )

    if exam.status != ExamStatus.PUBLISHED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error_code": "EXAM_NOT_PUBLISHED", "message": "考试尚未发布"},
        )

    if exam.exam_mode.value not in SUPPORTED_EXAM_MODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "EXAM_MODE_NOT_SUPPORTED_YET",
                "message": "该考试模式暂未支持",
            },
        )

    # 校验容器状态
    container = await crud_container.get_container_by_user(db, user_id)
    if container is None or container.status != ContainerStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "CONTAINER_NOT_RUNNING",
                "message": "请先启动仿真容器再参加考试",
            },
        )

    # 并发控制：不能有进行中的 attempt
    in_progress = await crud_attempt.get_in_progress_attempt(db, user_id, body.exam_id)
    if in_progress is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "ATTEMPT_IN_PROGRESS",
                "message": f"已有进行中的考试尝试（attempt_id={in_progress.id}）",
                "attempt_id": in_progress.id,
            },
        )

    # 尝试次数限制
    runtime_policy = exam.runtime_policy_json or {}
    max_attempts = runtime_policy.get("max_attempts", 3)
    used_attempts = await crud_attempt.count_all_attempts(db, user_id, body.exam_id)
    if used_attempts >= max_attempts:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "MAX_ATTEMPTS_EXCEEDED",
                "message": f"已达最大尝试次数（{max_attempts}）",
            },
        )

    # 创建 attempt，同时固化 exam 配置快照
    attempt = await crud_attempt.create_attempt(
        db,
        exam_id=body.exam_id,
        student_id=user_id,
        container_id=container.id,
        sim_container_docker_id=container.container_id,
        attempt_exam_mode=exam.exam_mode.value,
        attempt_runtime_policy_json=exam.runtime_policy_json or {},
        attempt_panel_policy_json=exam.panel_policy_json or {},
        attempt_scoring_policy_json=exam.scoring_policy_json or {},
        attempt_sidecar_policy_json=exam.sidecar_policy_json or {},
    )

    await crud_attempt.record_event(
        db, attempt_id=attempt.id,
        event_type=EvidenceEventType.EXAM_ATTEMPT_CREATED,
        payload={"exam_id": body.exam_id, "student_id": user_id},
    )

    logger.info(f"[考试] attempt={attempt.id} 创建成功 exam={body.exam_id} student={user_id}")

    return ApiResponse(
        code=0,
        data=CreateAttemptResponse(
            attempt_id=attempt.id,
            status=attempt.status.value,
        ),
        message="考试尝试已创建，请调用 /start 开始考试",
    )


# ─── POST /students/exam-attempts/{id}/start ─────────────────────────────────


@router.post(
    "/exam-attempts/{attempt_id}/start",
    response_model=ApiResponse[StudentAttemptDetailSchema],
    summary="开始考试（代码快照 + 启动 Sidecar）",
)
async def start_attempt(
    attempt_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    触发考试执行流程：
    1. 校验 attempt 归属和状态（必须为 pending）
    2. 异步启动 schedule_sidecar（非阻塞）
    3. 立即返回当前状态
    """
    attempt = await crud_attempt.get_attempt(db, attempt_id)
    if attempt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "ATTEMPT_NOT_FOUND", "message": "考试尝试不存在"},
        )

    if attempt.student_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error_code": "FORBIDDEN_NOT_OWNER", "message": "无权操作此考试尝试"},
        )

    if attempt.status != ExamAttemptStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "ATTEMPT_WRONG_STATUS",
                "message": f"当前状态为 {attempt.status.value}，只有 pending 状态可以开始",
            },
        )

    # 非阻塞触发 Sidecar 调度（快照 + 启动 + 等待 + 解析 + 清理）
    asyncio.create_task(schedule_sidecar(attempt_id))

    logger.info(f"[考试] attempt={attempt_id} /start 调用，Sidecar 调度已触发")

    return ApiResponse(
        code=0,
        data=_build_student_detail(attempt),
        message="考试评测已启动，请轮询 GET /exam-attempts/{id} 获取结果",
    )


# ─── GET /students/exam-attempts/{id} ─────────────────────────────────────────


@router.get(
    "/exam-attempts/{attempt_id}",
    response_model=ApiResponse[StudentAttemptDetailSchema],
    summary="查询考试尝试详情（含实时状态轮询）",
)
async def get_attempt_detail(
    attempt_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    attempt = await crud_attempt.get_attempt(db, attempt_id)
    if attempt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "ATTEMPT_NOT_FOUND", "message": "考试尝试不存在"},
        )

    if attempt.student_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error_code": "FORBIDDEN_NOT_OWNER", "message": "无权查看此考试尝试"},
        )

    return ApiResponse(code=0, data=_build_student_detail(attempt))


# ─── GET /students/exam-attempts/{id} ─────────────────────────────────────────


@router.get(
    "/exam-attempts/{attempt_id}/logs",
    response_model=ApiResponse[dict],
    summary="获取 Sidecar 容器执行日志",
)
async def get_attempt_sidecar_logs(
    attempt_id: int,
    lines: int = Query(default=500, ge=1, le=2000),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    attempt = await crud_attempt.get_attempt(db, attempt_id)
    if attempt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "ATTEMPT_NOT_FOUND", "message": "考试尝试不存在"},
        )

    if attempt.student_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error_code": "FORBIDDEN_NOT_OWNER", "message": "无权查看此考试尝试"},
        )

    if not attempt.sidecar_container_id:
        return ApiResponse(code=0, data={"logs": "Sidecar container not yet created.", "lines_requested": lines})

    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "logs", "--tail", str(lines), attempt.sidecar_container_id,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        logs = stdout.decode("utf-8", errors="replace")
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="获取日志超时")
    except Exception as e:
        logger.warning("[exam_attempts] docker logs 失败: %s", e)
        raise HTTPException(status_code=500, detail=f"获取日志失败: {e}")

    return ApiResponse(code=0, data={"logs": logs, "lines_requested": lines})


# ─── POST /students/exam-attempts/{id}/abort ─────────────────────────────────


@router.post(
    "/exam-attempts/{attempt_id}/abort",
    response_model=ApiResponse[StudentAttemptDetailSchema],
    summary="学生主动放弃考试",
)
async def abort_attempt(
    attempt_id: int,
    body: AbortAttemptRequest,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    attempt = await crud_attempt.get_attempt(db, attempt_id)
    if attempt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "ATTEMPT_NOT_FOUND", "message": "考试尝试不存在"},
        )

    if attempt.student_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error_code": "FORBIDDEN_NOT_OWNER", "message": "无权操作此考试尝试"},
        )

    abortable = {ExamAttemptStatus.PENDING, ExamAttemptStatus.RUNNING, ExamAttemptStatus.SCORING}
    if attempt.status not in abortable:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "ATTEMPT_WRONG_STATUS",
                "message": f"当前状态 {attempt.status.value} 无法放弃",
            },
        )

    # 若 Sidecar 容器在运行，异步终止
    if attempt.sidecar_container_id and attempt.status == ExamAttemptStatus.RUNNING:
        from app.core.sidecar_manager import kill_timeout_sidecar
        asyncio.create_task(kill_timeout_sidecar(attempt_id))
    else:
        # pending/scoring 直接标记 aborted
        await crud_attempt.record_event(
            db, attempt_id=attempt_id,
            event_type=EvidenceEventType.EXAM_ABORTED_BY_STUDENT,
            payload={"reason": body.reason or ""},
        )
        attempt = await crud_attempt.finalize_attempt(
            db, attempt,
            status=ExamAttemptStatus.ABORTED,
            error_code=None,
            error_message=body.reason,
        )
        await crud_attempt.record_event(
            db, attempt_id=attempt_id,
            event_type=EvidenceEventType.EXAM_ATTEMPT_FINALIZED,
            payload={"final_status": "aborted"},
        )

    return ApiResponse(code=0, data=_build_student_detail(attempt))
