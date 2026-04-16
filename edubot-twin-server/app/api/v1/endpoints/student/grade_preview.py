"""
学生端成绩预览 API（第16期）

路由（在 student/__init__.py 中以无 prefix 方式挂载）：
  GET /students/my-grade-summary                             → 学生所有考试最高分摘要
  GET /students/exams/{exam_id}/my-grade-detail              → 某考试所有尝试详情（含评语）
  GET /students/exam-attempts/{id}/submission/files          → 列出提交代码文件树（仅本人）
  GET /students/exam-attempts/{id}/submission/files/read     → 读取文件内容
  GET /students/exam-attempts/{id}/submission/files/download → 下载文件/目录

安全约束：
- submission 端点额外校验 attempt.student_id == current_user_id，失败返回 403
"""

import io
import logging
import mimetypes
import zipfile
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user_id
from app.crud import exam as crud_exam
from app.crud import exam_attempt as crud_attempt
from app.db.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.grade_preview import (
    StudentAttemptGradeDetailItem,
    StudentGradeSummaryItem,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# 文本预览扩展名白名单
SUBMISSION_TEXT_EXTENSIONS = {
    ".json", ".yaml", ".yml", ".txt", ".log", ".md", ".csv", ".sh", ".py",
    ".cpp", ".c", ".h", ".hpp", ".java", ".js", ".ts", ".vue", ".html", ".css",
    ".xml", ".launch", ".urdf", ".xacro", ".cmake", ".msg", ".srv", ".action",
    ".conf", ".cfg", ".ini", ".toml", ".rs",
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
SUBMISSION_PREVIEW_MAX_BYTES = 5 * 1024 * 1024


# ─── 内部辅助 ─────────────────────────────────────────────────────────────────


def _resolve_submission_dir(attempt) -> Optional[Path]:
    """返回提交代码快照目录 Path（不存在时返回 None）"""
    if attempt.submission_snapshot_path:
        p = Path(attempt.submission_snapshot_path)
        return p if p.exists() and p.is_dir() else None
    return None


def _submission_safe_path(submission_dir: Path, rel_path: str) -> Path:
    """校验相对路径不越出 submission_dir，越界时抛 400"""
    try:
        candidate = (submission_dir / rel_path).resolve()
        candidate.relative_to(submission_dir.resolve())
    except (ValueError, Exception):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "PATH_TRAVERSAL", "message": "非法文件路径"},
        )
    return candidate


async def _get_attempt_owned_by_student(
    db: AsyncSession, attempt_id: int, student_id: int
):
    """查询 attempt 并校验归属，失败时分别抛 404 / 403"""
    attempt = await crud_attempt.get_attempt(db, attempt_id)
    if attempt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "ATTEMPT_NOT_FOUND", "message": "运行记录不存在"},
        )
    if attempt.student_id != student_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error_code": "FORBIDDEN", "message": "无权访问他人的运行记录"},
        )
    return attempt


# ─── 学生端成绩汇总 ──────────────────────────────────────────────────────────


@router.get(
    "/my-grade-summary",
    response_model=ApiResponse[list[StudentGradeSummaryItem]],
    summary="我的成绩汇总（每考试最高分）",
)
async def get_my_grade_summary(
    current_user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    rows = await crud_attempt.list_my_grade_summary(db, student_id=current_user_id)
    items: list[StudentGradeSummaryItem] = []
    for attempt, exam_name, exam_code in rows:
        # summary 截断 200 字
        summary = attempt.summary
        if summary and len(summary) > 200:
            summary = summary[:200] + "…"
        teacher_comment = attempt.teacher_comment
        if teacher_comment and len(teacher_comment) > 200:
            teacher_comment = teacher_comment[:200] + "…"
        items.append(
            StudentGradeSummaryItem(
                exam_id=attempt.exam_id,
                exam_name=exam_name,
                exam_code=exam_code,
                best_attempt_id=attempt.id,
                objective_score=attempt.objective_score,
                final_score=attempt.final_score,
                **{"pass": attempt.pass_},
                summary=summary,
                teacher_comment=teacher_comment,
                status=attempt.status.value,
                ended_at=attempt.ended_at,
            )
        )
    return ApiResponse(code=0, data=items)


# ─── 学生端考试成绩详情 ───────────────────────────────────────────────────────


@router.get(
    "/exams/{exam_id}/my-grade-detail",
    response_model=ApiResponse[list[StudentAttemptGradeDetailItem]],
    summary="某考试我的所有尝试详情（含评语）",
)
async def get_my_grade_detail(
    exam_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    exam = await crud_exam.get_exam(db, exam_id)
    if exam is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "EXAM_NOT_FOUND", "message": "考试不存在"},
        )
    attempts = await crud_attempt.list_grade_detail_for_student(
        db, student_id=current_user_id, exam_id=exam_id
    )
    items = [
        StudentAttemptGradeDetailItem(
            attempt_id=a.id,
            status=a.status.value,
            objective_score=a.objective_score,
            final_score=a.final_score,
            **{"pass": a.pass_},
            summary=a.summary,
            teacher_comment=a.teacher_comment,
            custom_fields=a.custom_fields_json,
            has_code_snapshot=a.submission_snapshot_path is not None,
            started_at=a.started_at,
            ended_at=a.ended_at,
            duration_ms=a.duration_ms,
            created_at=a.created_at,
        )
        for a in attempts
    ]
    return ApiResponse(code=0, data=items)


# ─── 学生端 submission 只读端点（对称教师端，鉴权不同）───────────────────────


@router.get(
    "/exam-attempts/{attempt_id}/submission/files",
    response_model=ApiResponse[dict],
    summary="（学生只读）列出自己提交代码文件树",
)
async def list_my_submission_files(
    attempt_id: int,
    path: Optional[str] = Query(default=None),
    current_user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    attempt = await _get_attempt_owned_by_student(db, attempt_id, current_user_id)
    submission_dir = _resolve_submission_dir(attempt)
    if submission_dir is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "SNAPSHOT_NOT_FOUND", "message": "代码快照不存在或已清理"},
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
    summary="（学生只读）读取自己提交代码文件内容",
)
async def read_my_submission_file(
    attempt_id: int,
    path: str = Query(...),
    current_user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    attempt = await _get_attempt_owned_by_student(db, attempt_id, current_user_id)
    submission_dir = _resolve_submission_dir(attempt)
    if submission_dir is None:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "SNAPSHOT_NOT_FOUND", "message": "快照不存在或已清理"},
        )
    file_path = _submission_safe_path(submission_dir, path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(
            status_code=404,
            detail={"error_code": "FILE_NOT_FOUND", "message": "文件不存在"},
        )
    size = file_path.stat().st_size
    if size > SUBMISSION_PREVIEW_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"error_code": "FILE_TOO_LARGE", "message": "超出5MB预览限制"},
        )
    ext = file_path.suffix.lower()
    mime, _ = mimetypes.guess_type(file_path.name)
    if ext in SUBMISSION_TEXT_EXTENSIONS:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        return ApiResponse(
            code=0,
            data={
                "content": content,
                "encoding": "utf-8",
                "mime": mime or "text/plain",
                "modified_at": file_path.stat().st_mtime,
            },
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
            status_code=415,
            detail={"error_code": "PREVIEW_NOT_SUPPORTED", "message": "不支持预览该文件类型"},
        )


@router.get(
    "/exam-attempts/{attempt_id}/submission/files/download",
    summary="（学生只读）下载自己提交代码文件或目录",
)
async def download_my_submission_file(
    attempt_id: int,
    path: str = Query(...),
    current_user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    attempt = await _get_attempt_owned_by_student(db, attempt_id, current_user_id)
    submission_dir = _resolve_submission_dir(attempt)
    if submission_dir is None:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "SNAPSHOT_NOT_FOUND", "message": "快照不存在或已清理"},
        )
    target = _submission_safe_path(submission_dir, path)
    if not target.exists():
        raise HTTPException(
            status_code=404,
            detail={"error_code": "PATH_NOT_FOUND", "message": "路径不存在"},
        )

    if target.is_file():
        filename = target.name
        try:
            filename.encode("latin-1")
            cd = f'attachment; filename="{filename}"'
        except UnicodeEncodeError:
            cd = f'attachment; filename="download"; filename*=UTF-8\'\'{quote(filename, safe="")}'

        def _gen():
            with open(target, "rb") as f:
                while chunk := f.read(65536):
                    yield chunk

        return StreamingResponse(
            _gen(),
            media_type="application/octet-stream",
            headers={"Content-Disposition": cd, "Content-Length": str(target.stat().st_size)},
        )

    # 目录：打包成 zip
    zip_name = target.name + ".zip"
    try:
        zip_name.encode("latin-1")
        cd = f'attachment; filename="{zip_name}"'
    except UnicodeEncodeError:
        cd = f'attachment; filename="download"; filename*=UTF-8\'\'{quote(zip_name, safe="")}'

    def _zip_gen():
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in target.rglob("*"):
                if f.is_file():
                    zf.write(f, target.name + "/" + str(f.relative_to(target)))
        buf.seek(0)
        while chunk := buf.read(65536):
            yield chunk

    return StreamingResponse(
        _zip_gen(),
        media_type="application/zip",
        headers={"Content-Disposition": cd},
    )
