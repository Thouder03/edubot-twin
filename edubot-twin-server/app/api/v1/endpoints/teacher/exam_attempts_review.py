"""
教师端考试复核 API（第13期 SDD §5.1 / §8 | 第14期 submission 只读端点）

路由前缀在 teacher/__init__.py 中注册（无 prefix，与 exam_attempts 共用路径空间）：
  GET  /teachers/exam-attempts/{id}/artifacts         → artifacts 目录树
  GET  /teachers/exam-attempts/{id}/artifacts/file    → 读取单文件（?path=xxx）
  POST /teachers/exam-attempts/{id}/manual-score      → 提交人工评分
  POST /teachers/exam-attempts/{id}/override          → 覆盖客观分 / pass

第14期新增（提交代码只读查看）：
  GET  /teachers/exam-attempts/{id}/submission/files         → 列目录
  GET  /teachers/exam-attempts/{id}/submission/files/read    → 读文件
  GET  /teachers/exam-attempts/{id}/submission/files/download→ 下载文件/目录
"""

import io
import logging
import mimetypes
import os
import zipfile
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.final_score_calculator import (
    calculate_final_score,
    get_scoring_mode,
    validate_override_allowed,
)
from app.core.security import get_current_user_id, get_current_teacher
from app.core.workspace_snapshot import get_artifacts_path
from app.crud import exam_attempt as crud_attempt
from app.crud import exam as crud_exam
from app.db.database import get_db
from app.models.exam_attempt import (
    ExamAttempt,
    ExamAttemptStatus,
    EvidenceEventType,
)
from app.models.student import User
from app.schemas.common import ApiResponse
from app.schemas.exam_attempt import (
    AttemptExamInfo,
    AttemptStudentInfo,
    ManualScoreRequest,
    OverrideRequest,
    TeacherAttemptFullSchema,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# 单文件预览上限（5MB）
ARTIFACT_PREVIEW_MAX_BYTES = 5 * 1024 * 1024

# 文本预览的 MIME 类型 / 扩展名白名单
TEXT_EXTENSIONS = {".json", ".yaml", ".yml", ".txt", ".log", ".md", ".csv", ".sh", ".py"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


# ─── 内部辅助 ─────────────────────────────────────────────────────────────────


async def _get_attempt_or_404(db: AsyncSession, attempt_id: int) -> ExamAttempt:
    attempt = await crud_attempt.get_attempt(db, attempt_id)
    if attempt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "ATTEMPT_NOT_FOUND", "message": "运行记录不存在"},
        )
    return attempt


async def _get_student_info(db: AsyncSession, student_id: int) -> AttemptStudentInfo:
    result = await db.execute(select(User).where(User.id == student_id))
    user = result.scalar_one_or_none()
    if user:
        return AttemptStudentInfo(
            student_id=user.id,
            username=user.username,
            real_name=getattr(user, "real_name", None),
        )
    return AttemptStudentInfo(student_id=student_id, username=f"student_{student_id}")


async def _get_exam_info(db: AsyncSession, exam_id: int) -> AttemptExamInfo:
    exam = await crud_exam.get_exam(db, exam_id)
    if exam:
        return AttemptExamInfo(
            exam_id=exam.id,
            name=exam.name,
            exam_mode=exam.exam_mode.value,
        )
    return AttemptExamInfo(exam_id=exam_id, name=f"exam_{exam_id}", exam_mode="unknown")


def _is_objective_only_attempt(attempt: ExamAttempt) -> bool:
    scoring_policy = attempt.attempt_scoring_policy_json or {}
    return get_scoring_mode(scoring_policy) == "objective_only"


def _build_teacher_full(attempt, student: AttemptStudentInfo, exam: AttemptExamInfo) -> TeacherAttemptFullSchema:
    final_score = attempt.objective_score if _is_objective_only_attempt(attempt) else attempt.final_score
    review_status = None if _is_objective_only_attempt(attempt) else attempt.review_status.value

    return TeacherAttemptFullSchema(
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
        student=student,
        exam=exam,
        review_status=review_status,
        manual_score=attempt.manual_score,
        final_score=final_score,
        breakdown_json=attempt.breakdown_json,
        teacher_comment=attempt.teacher_comment,
        artifact_index_json=attempt.artifact_index_json or {},
        sidecar_container_id=attempt.sidecar_container_id,
        attempt_scoring_policy_json=attempt.attempt_scoring_policy_json or {},
        submission_snapshot_path=attempt.submission_snapshot_path,
    )


def _resolve_artifacts_dir(attempt: ExamAttempt) -> Optional[Path]:
    """返回 artifacts 目录 Path（不存在时返回 None）"""
    if attempt.artifacts_path:
        p = Path(attempt.artifacts_path)
    else:
        p = get_artifacts_path(attempt.id)
    return p if p.exists() and p.is_dir() else None


def _safe_path(artifacts_dir: Path, rel_path: str) -> Path:
    """
    归一化并校验请求路径不越出 artifacts_dir（防路径穿越）。
    不合法时抛 403。
    """
    try:
        candidate = (artifacts_dir / rel_path).resolve()
        artifacts_dir_resolved = artifacts_dir.resolve()
        candidate.relative_to(artifacts_dir_resolved)  # 若越界抛 ValueError
    except (ValueError, Exception):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error_code": "PATH_TRAVERSAL", "message": "非法文件路径"},
        )
    return candidate


# ─── GET /teachers/exam-attempts/{id}/artifacts ───────────────────────────────


@router.get(
    "/exam-attempts/{attempt_id}/artifacts",
    response_model=ApiResponse[dict],
    summary="artifacts 目录树",
)
async def get_artifacts_tree(
    attempt_id: int,
    _user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    attempt = await _get_attempt_or_404(db, attempt_id)

    # 优先从数据库索引返回（数据库为复核主真相源）
    db_index: dict = attempt.artifact_index_json or {}

    # 同时扫描文件系统，补充实际文件列表
    artifacts_dir = _resolve_artifacts_dir(attempt)
    fs_files: list[dict] = []
    if artifacts_dir:
        for f in sorted(artifacts_dir.iterdir()):
            if f.is_file():
                ext = f.suffix.lower()
                size = f.stat().st_size
                mime, _ = mimetypes.guess_type(f.name)
                if ext in TEXT_EXTENSIONS:
                    preview_type = "text"
                elif ext in IMAGE_EXTENSIONS:
                    preview_type = "image"
                elif ext == ".pgm":
                    preview_type = "download"
                else:
                    preview_type = "unsupported"
                fs_files.append({
                    "name": f.name,
                    "size": size,
                    "mime": mime or "application/octet-stream",
                    "preview_type": preview_type,
                    "too_large": size > ARTIFACT_PREVIEW_MAX_BYTES,
                })

    return ApiResponse(
        code=0,
        data={
            "artifact_index": db_index,
            "files": fs_files,
            "artifacts_available": artifacts_dir is not None,
        },
    )


# ─── GET /teachers/exam-attempts/{id}/artifacts/file ─────────────────────────


@router.get(
    "/exam-attempts/{attempt_id}/artifacts/file",
    response_model=ApiResponse[dict],
    summary="读取单个 artifact 文件（文本/Base64 图片）",
)
async def get_artifact_file(
    attempt_id: int,
    path: str = Query(..., description="文件相对路径（相对 artifacts 目录）"),
    _user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    attempt = await _get_attempt_or_404(db, attempt_id)

    artifacts_dir = _resolve_artifacts_dir(attempt)
    if artifacts_dir is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "ARTIFACT_NOT_FOUND", "message": "artifacts 目录不存在或已清理"},
        )

    file_path = _safe_path(artifacts_dir, path)

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "ARTIFACT_NOT_FOUND", "message": "文件不存在"},
        )

    size = file_path.stat().st_size
    if size > ARTIFACT_PREVIEW_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"error_code": "ARTIFACT_TOO_LARGE", "message": "文件超出 5MB 预览限制，请下载查看"},
        )

    ext = file_path.suffix.lower()
    mime, _ = mimetypes.guess_type(file_path.name)

    if ext in TEXT_EXTENSIONS:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        return ApiResponse(
            code=0,
            data={"content": content, "encoding": "utf-8", "mime": mime or "text/plain"},
        )
    elif ext in IMAGE_EXTENSIONS:
        import base64
        b64 = base64.b64encode(file_path.read_bytes()).decode()
        return ApiResponse(
            code=0,
            data={"content": b64, "encoding": "base64", "mime": mime or "image/png"},
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={"error_code": "PREVIEW_NOT_SUPPORTED", "message": "该文件类型不支持预览"},
        )


# ─── POST /teachers/exam-attempts/{id}/manual-score ──────────────────────────


@router.post(
    "/exam-attempts/{attempt_id}/manual-score",
    response_model=ApiResponse[TeacherAttemptFullSchema],
    summary="提交人工评分（自动核算 final_score）",
)
async def submit_manual_score(
    attempt_id: int,
    body: ManualScoreRequest,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    attempt = await _get_attempt_or_404(db, attempt_id)

    # 仅 completed / reviewed 状态允许提交（reviewed 表示可重新评分）
    if attempt.status not in (ExamAttemptStatus.COMPLETED, ExamAttemptStatus.REVIEWED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "ATTEMPT_NOT_COMPLETED",
                "message": f"当前状态 {attempt.status.value} 不允许提交人工评分",
            },
        )

    scoring_policy = attempt.attempt_scoring_policy_json or {}

    # 核算最终成绩
    final_score, pass_final = calculate_final_score(
        objective_score=attempt.objective_score,
        manual_score=body.manual_score,
        scoring_policy=scoring_policy,
    )

    # 写入数据库
    attempt = await crud_attempt.apply_manual_score(
        db,
        attempt,
        manual_score=body.manual_score,
        breakdown_json=body.breakdown.model_dump(),
        teacher_comment=body.comment,
        final_score=final_score,
        pass_=pass_final,
    )

    # 写入审计事件
    await crud_attempt.record_event(
        db,
        attempt_id=attempt_id,
        event_type=EvidenceEventType.MANUAL_SCORE_SUBMITTED,
        payload={"teacher_id": user_id, "manual_score": body.manual_score},
    )
    await crud_attempt.record_event(
        db,
        attempt_id=attempt_id,
        event_type=EvidenceEventType.FINAL_SCORE_CALCULATED,
        payload={
            "objective": attempt.objective_score,
            "manual": body.manual_score,
            "final": final_score,
        },
    )

    student = await _get_student_info(db, attempt.student_id)
    exam = await _get_exam_info(db, attempt.exam_id)

    logger.info(
        "人工评分提交成功 attempt_id=%d teacher_id=%d manual=%.2f final=%.2f",
        attempt_id, user_id, body.manual_score, final_score,
    )

    return ApiResponse(code=0, data=_build_teacher_full(attempt, student, exam))


# ─── POST /teachers/exam-attempts/{id}/override ───────────────────────────────


@router.post(
    "/exam-attempts/{attempt_id}/override",
    response_model=ApiResponse[TeacherAttemptFullSchema],
    summary="教师覆盖客观分 / pass（受 scoring_policy 控制）",
)
async def override_scores(
    attempt_id: int,
    body: OverrideRequest,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    attempt = await _get_attempt_or_404(db, attempt_id)

    scoring_policy = attempt.attempt_scoring_policy_json or {}

    # 策略校验
    err = validate_override_allowed(
        scoring_policy,
        wants_override_objective=body.objective_score is not None,
        wants_override_pass=body.pass_flag is not None,
    )
    if err:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error_code": "OVERRIDE_NOT_ALLOWED", "message": err},
        )

    # 重算最终分（若需要）
    new_objective = body.objective_score if body.objective_score is not None else attempt.objective_score
    new_manual = attempt.manual_score  # 覆盖不改变 manual_score

    if body.pass_flag is not None:
        # 直接覆盖 pass，不重算分数
        new_final = attempt.final_score
        new_pass = body.pass_flag
    else:
        # 覆盖了 objective_score → 重算
        new_final, new_pass = calculate_final_score(
            objective_score=new_objective,
            manual_score=new_manual,
            scoring_policy=scoring_policy,
        )

    # 写入审计事件
    await crud_attempt.record_event(
        db,
        attempt_id=attempt_id,
        event_type=EvidenceEventType.TEACHER_OVERRIDE,
        payload={
            "teacher_id": user_id,
            "reason": body.override_reason,
            "overrides": {
                "objective_score": body.objective_score,
                "pass_flag": body.pass_flag,
            },
        },
    )

    # 更新数据库
    attempt = await crud_attempt.apply_override(
        db,
        attempt,
        objective_score=body.objective_score,
        pass_flag=new_pass if body.pass_flag is not None else None,
        final_score=new_final,
    )

    student = await _get_student_info(db, attempt.student_id)
    exam = await _get_exam_info(db, attempt.exam_id)

    logger.info(
        "教师覆盖 attempt_id=%d teacher_id=%d reason=%s",
        attempt_id, user_id, body.override_reason,
    )

    return ApiResponse(code=0, data=_build_teacher_full(attempt, student, exam))


# ─── 第14期：学生提交代码只读查看 ──────────────────────────────────────────────


def _resolve_submission_dir(attempt):
    """返回提交代码快照目录 Path（不存在时返回 None）"""
    from pathlib import Path as _Path
    if attempt.submission_snapshot_path:
        p = _Path(attempt.submission_snapshot_path)
        return p if p.exists() and p.is_dir() else None
    return None


def _build_content_disposition(filename: str) -> str:
    """RFC 5987 兼容的 Content-Disposition，支持中文文件名"""
    from urllib.parse import quote as _quote
    try:
        filename.encode("latin-1")
        return f'attachment; filename="{filename}"'
    except UnicodeEncodeError:
        quoted = _quote(filename, safe="")
        return f'attachment; filename="download"; filename*=UTF-8''{quoted}'


def _submission_safe_path(submission_dir, rel_path: str):
    """校验相对路径不越出 submission_dir，越界时抛 403"""
    try:
        candidate = (submission_dir / rel_path).resolve()
        candidate.relative_to(submission_dir.resolve())
    except (ValueError, Exception):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error_code": "PATH_TRAVERSAL", "message": "非法文件路径"},
        )
    return candidate


SUBMISSION_TEXT_EXTENSIONS = TEXT_EXTENSIONS | {
    ".cpp", ".c", ".h", ".hpp", ".java", ".js", ".ts", ".vue", ".html", ".css",
    ".xml", ".launch", ".urdf", ".xacro", ".cmake", ".msg", ".srv", ".action",
    ".conf", ".cfg", ".ini", ".toml", ".rs",
}
SUBMISSION_PREVIEW_MAX_BYTES = 5 * 1024 * 1024


@router.get(
    "/exam-attempts/{attempt_id}/submission/files",
    response_model=ApiResponse[dict],
    summary="（教师只读）列出学生提交代码文件树",
)
async def list_submission_files(
    attempt_id: int,
    path: Optional[str] = Query(default=None),
    _teacher_id: int = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db),
):
    attempt = await _get_attempt_or_404(db, attempt_id)
    submission_dir = _resolve_submission_dir(attempt)
    if submission_dir is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "SUBMISSION_NOT_FOUND", "message": "提交代码快照不存在或尚未生成"},
        )
    base = submission_dir if not path else _submission_safe_path(submission_dir, path)
    if not base.exists() or not base.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "PATH_NOT_FOUND", "message": "目录不存在"},
        )
    items = []
    for entry in sorted(base.iterdir(), key=lambda e: (e.is_file(), e.name)):
        rel = str(entry.relative_to(submission_dir).as_posix())
        mime, _ = mimetypes.guess_type(entry.name)
        items.append({
            "name": entry.name,
            "relative_path": rel,
            "type": "file" if entry.is_file() else "dir",
            "size": entry.stat().st_size if entry.is_file() else None,
            "mime": mime or ("application/octet-stream" if entry.is_file() else None),
        })
    return ApiResponse(code=0, data={"items": items, "path": path or ""})


@router.get(
    "/exam-attempts/{attempt_id}/submission/files/read",
    response_model=ApiResponse[dict],
    summary="（教师只读）读取学生提交代码文件内容",
)
async def read_submission_file(
    attempt_id: int,
    path: str = Query(...),
    _teacher_id: int = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db),
):
    attempt = await _get_attempt_or_404(db, attempt_id)
    submission_dir = _resolve_submission_dir(attempt)
    if submission_dir is None:
        raise HTTPException(status_code=404, detail={"error_code": "SUBMISSION_NOT_FOUND", "message": "快照不存在"})
    file_path = _submission_safe_path(submission_dir, path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail={"error_code": "FILE_NOT_FOUND", "message": "文件不存在"})
    size = file_path.stat().st_size
    if size > SUBMISSION_PREVIEW_MAX_BYTES:
        raise HTTPException(status_code=413, detail={"error_code": "FILE_TOO_LARGE", "message": "超出5MB限制"})
    ext = file_path.suffix.lower()
    mime, _ = mimetypes.guess_type(file_path.name)
    if ext in SUBMISSION_TEXT_EXTENSIONS:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        return ApiResponse(code=0, data={"content": content, "encoding": "utf-8", "mime": mime or "text/plain", "modified_at": file_path.stat().st_mtime})
    elif ext in IMAGE_EXTENSIONS:
        import base64
        b64 = base64.b64encode(file_path.read_bytes()).decode()
        return ApiResponse(code=0, data={"content": b64, "encoding": "base64", "mime": mime or "image/png"})
    else:
        raise HTTPException(status_code=415, detail={"error_code": "PREVIEW_NOT_SUPPORTED", "message": "不支持预览"})


@router.get(
    "/exam-attempts/{attempt_id}/submission/files/download",
    summary="（教师只读）下载学生提交代码文件或目录",
)
async def download_submission_file(
    attempt_id: int,
    path: str = Query(...),
    _teacher_id: int = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db),
):
    import io as _io, zipfile as _zip
    from urllib.parse import quote as _quote
    attempt = await _get_attempt_or_404(db, attempt_id)
    submission_dir = _resolve_submission_dir(attempt)
    if submission_dir is None:
        raise HTTPException(status_code=404, detail={"error_code": "SUBMISSION_NOT_FOUND", "message": "快照不存在"})
    target = _submission_safe_path(submission_dir, path)
    if not target.exists():
        raise HTTPException(status_code=404, detail={"error_code": "PATH_NOT_FOUND", "message": "路径不存在"})
    if target.is_file():
        filename = target.name
        try:
            filename.encode("latin-1")
            cd = f'attachment; filename="{filename}"'
        except UnicodeEncodeError:
            cd = f'attachment; filename="download"; filename*=UTF-8\'\'{_quote(filename, safe="")}'

        def _gen():
            with open(target, "rb") as f:
                while c := f.read(65536):
                    yield c

        return StreamingResponse(_gen(), media_type="application/octet-stream", headers={"Content-Disposition": cd, "Content-Length": str(target.stat().st_size)})
    zip_name = target.name + ".zip"
    try:
        zip_name.encode("latin-1")
        cd = f'attachment; filename="{zip_name}"'
    except UnicodeEncodeError:
        cd = f'attachment; filename="download"; filename*=UTF-8\'\'{_quote(zip_name, safe="")}'

    def _zip_gen():
        buf = _io.BytesIO()
        with _zip.ZipFile(buf, "w", _zip.ZIP_DEFLATED) as zf:
            for f in target.rglob("*"):
                if f.is_file():
                    zf.write(f, target.name + "/" + str(f.relative_to(target)))
        buf.seek(0)
        while c := buf.read(65536):
            yield c

    return StreamingResponse(_zip_gen(), media_type="application/zip", headers={"Content-Disposition": cd})
