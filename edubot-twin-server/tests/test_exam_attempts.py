"""
第12期考试运行闭环测试

覆盖（对应 SDD §11.1 测试覆盖地图）：

单元测试：
  U1  result_parser：合法 JSON 解析
  U2  result_parser：文件不存在 → RESULT_MISSING_FILE
  U3  result_parser：非合法 JSON → RESULT_INVALID_JSON
  U4  result_parser：缺必填字段 → RESULT_MISSING_FIELDS
  U5  result_parser：score 超界自动 clamp
  U6  result_parser：文件超大 → RESULT_TOO_LARGE
  U7  workspace_snapshot：目录不存在 → SnapshotError

CRUD 集成测试（内存 SQLite）：
  C1  创建 attempt → status=pending
  C2  并发控制：已有 pending/running/scoring → 拒绝第二次创建
  C3  count_all_attempts 正确统计
  C4  count_completed_attempts 只计终态
  C5  update_attempt_status：路径字段写入
  C6  finalize_attempt：score clamp、summary 截断、duration_ms 自动计算
  C7  record_event：sequence_no 自动递增
  C8  list_events：按 sequence_no 升序
  C9  find_stale_pending_attempts：超时回收
  C10 find_timeout_running_attempts：按 runtime_policy 超时判断

API 端点集成测试（直接调用 handler + 内存 SQLite）：
  A1  GET /students/exams/{id}：已发布考试返回 ExamRunInfo
  A2  GET /students/exams/{id}：未发布 → 409 EXAM_NOT_PUBLISHED
  A3  GET /students/exams/{id}：process_run → 400 EXAM_MODE_NOT_SUPPORTED_YET
  A4  POST /students/exam-attempts：正常创建 → 201
  A5  POST /students/exam-attempts：容器非 running → 400
  A6  POST /students/exam-attempts：已有进行中 → 409
  A7  POST /students/exam-attempts：超出最大次数 → 409
  A8  GET /students/exam-attempts/{id}：正常查询
  A9  GET /students/exam-attempts/{id}：越权访问 → 403
  A10 POST /students/exam-attempts/{id}/abort：正常放弃
  A11 POST /students/exam-attempts/{id}/abort：非自身 → 403
  A12 GET /teachers/exam-attempts：全局列表分页
  A13 GET /teachers/exam-attempts/{id}：完整详情（含学生信息）
  A14 GET /teachers/exam-attempts/{id}/events：生命周期事件时间轴
  A15 GET /teachers/exams/{id}/attempts：单考试列表
"""

import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.crud import exam_attempt as crud_attempt
from app.crud import exam as crud_exam
from app.models.exam import ExamMode, ExamStatus
from app.models.exam_attempt import (
    EvidenceEventType,
    ExamAttempt,
    ExamAttemptStatus,
)


# ═══════════════════════════════════════════════════════════════════════════════
#  测试常量
# ═══════════════════════════════════════════════════════════════════════════════

STUDENT_ID = 10
TEACHER_ID = 1
OTHER_STUDENT_ID = 20


# ═══════════════════════════════════════════════════════════════════════════════
#  辅助函数
# ═══════════════════════════════════════════════════════════════════════════════


async def _create_published_exam(db, code_suffix="", exam_mode="result_run", max_attempts=3):
    """创建已发布的 result_run 考试"""
    from app.models.exam import Exam
    exam = Exam(
        name=f"自动导航考试_{code_suffix}",
        code=f"exam_{code_suffix}_{id(db)}",
        exam_mode=ExamMode(exam_mode),
        status=ExamStatus.PUBLISHED,
        runtime_policy_json={
            "max_duration_ms": 300000,
            "max_attempts": max_attempts,
            "allow_debug_before_start": True,
        },
        panel_policy_json={},
        scoring_policy_json={},
        sidecar_policy_json={"image": "edubot/sidecar-runner:v1"},
        created_by=TEACHER_ID,
    )
    db.add(exam)
    await db.commit()
    await db.refresh(exam)
    return exam


async def _create_draft_exam(db, code_suffix=""):
    """创建草稿考试"""
    from app.models.exam import Exam
    exam = Exam(
        name=f"草稿考试_{code_suffix}",
        code=f"draft_{code_suffix}_{id(db)}",
        exam_mode=ExamMode.RESULT_RUN,
        status=ExamStatus.DRAFT,
        runtime_policy_json={"max_duration_ms": 300000, "max_attempts": 3},
        panel_policy_json={},
        scoring_policy_json={},
        sidecar_policy_json={},
        created_by=TEACHER_ID,
    )
    db.add(exam)
    await db.commit()
    await db.refresh(exam)
    return exam


async def _create_running_container(db, user_id=STUDENT_ID):
    """创建 running 状态的容器记录"""
    from app.models.container import SimContainer, ContainerStatus
    container = SimContainer(
        user_id=user_id,
        container_id=f"deadbeef{user_id:04d}",
        image_name="gzweb_sim:v1",
        status=ContainerStatus.RUNNING,
        gzbridge_port=8080 + user_id,
        rosbridge_port=9090 + user_id,
    )
    db.add(container)
    await db.commit()
    await db.refresh(container)
    return container


async def _create_user(db, user_id, username, role_code="student"):
    """创建用户记录（供 teacher 端查询学生信息）"""
    from app.models.student import User
    from sqlalchemy import select
    result = await db.execute(select(User).where(User.id == user_id))
    existing = result.scalar_one_or_none()
    if existing:
        return existing
    user = User(
        id=user_id,
        username=username,
        password_hash="hashed",
        real_name=f"{username}_真名",
        role_code=role_code,
        role_id="10",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _base_sidecar_policy():
    return {"image": "edubot/sidecar-runner:v1", "cpu_limit": 1.0, "memory_limit_mb": 512}


async def _create_attempt(db, exam, container=None, status=ExamAttemptStatus.PENDING, student_id=STUDENT_ID):
    """快捷创建 attempt"""
    attempt = await crud_attempt.create_attempt(
        db,
        exam_id=exam.id,
        student_id=student_id,
        container_id=container.id if container else None,
        sim_container_docker_id=container.container_id if container else None,
        attempt_exam_mode=exam.exam_mode.value,
        attempt_runtime_policy_json=exam.runtime_policy_json or {},
        attempt_panel_policy_json=exam.panel_policy_json or {},
        attempt_scoring_policy_json=exam.scoring_policy_json or {},
        attempt_sidecar_policy_json=exam.sidecar_policy_json or {},
    )
    if status != ExamAttemptStatus.PENDING:
        attempt = await crud_attempt.update_attempt_status(db, attempt, status)
    return attempt


# ═══════════════════════════════════════════════════════════════════════════════
#  U：result_parser 单元测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestResultParser:
    """result_parser.py 单元测试"""

    def _make_result_file(self, tmpdir, content: str) -> str:
        """在临时目录中写入 result.json，返回 artifacts 目录路径"""
        result_path = Path(tmpdir) / "result.json"
        result_path.write_text(content, encoding="utf-8")
        return str(tmpdir)

    def _valid_result(self, score=85.0, pass_=True, summary="评测通过"):
        return json.dumps({
            "status": "completed",
            "objective_score": score,
            "pass": pass_,
            "summary": summary,
            "metrics": {"goal_reached": True, "elapsed_seconds": 45.2},
            "custom_fields": {"obstacle_count": 0},
        })

    def test_u1_valid_json_parse(self, tmp_path):
        from app.core.result_parser import parse_result_json
        artifacts = self._make_result_file(tmp_path, self._valid_result(score=85.0))
        result = parse_result_json(artifacts)
        assert result.objective_score == 85.0
        assert result.pass_ is True
        assert result.summary == "评测通过"
        assert result.status == "completed"
        assert result.score_clamped is False
        assert result.metrics is not None

    def test_u2_file_not_found(self, tmp_path):
        from app.core.result_parser import parse_result_json, ParseError
        with pytest.raises(ParseError) as exc_info:
            parse_result_json(str(tmp_path))
        assert exc_info.value.error_code == "RESULT_MISSING_FILE"

    def test_u3_invalid_json(self, tmp_path):
        from app.core.result_parser import parse_result_json, ParseError
        artifacts = self._make_result_file(tmp_path, "not valid json {{")
        with pytest.raises(ParseError) as exc_info:
            parse_result_json(artifacts)
        assert exc_info.value.error_code == "RESULT_INVALID_JSON"

    def test_u4_missing_required_fields(self, tmp_path):
        from app.core.result_parser import parse_result_json, ParseError
        incomplete = json.dumps({"status": "completed", "objective_score": 80})
        artifacts = self._make_result_file(tmp_path, incomplete)
        with pytest.raises(ParseError) as exc_info:
            parse_result_json(artifacts)
        assert exc_info.value.error_code == "RESULT_MISSING_FIELDS"

    def test_u5_score_clamp_above_100(self, tmp_path):
        from app.core.result_parser import parse_result_json
        over = json.dumps({"status": "completed", "objective_score": 110, "pass": True, "summary": "超分了"})
        artifacts = self._make_result_file(tmp_path, over)
        result = parse_result_json(artifacts)
        assert result.objective_score == 100.0
        assert result.score_clamped is True

    def test_u5b_score_clamp_below_0(self, tmp_path):
        from app.core.result_parser import parse_result_json
        under = json.dumps({"status": "failed", "objective_score": -5, "pass": False, "summary": "负分"})
        artifacts = self._make_result_file(tmp_path, under)
        result = parse_result_json(artifacts)
        assert result.objective_score == 0.0
        assert result.score_clamped is True

    def test_u6_file_too_large(self, tmp_path):
        from app.core.result_parser import parse_result_json, ParseError, MAX_RESULT_FILE_BYTES
        large_content = "x" * (MAX_RESULT_FILE_BYTES + 1)
        (Path(tmp_path) / "result.json").write_text(large_content)
        with pytest.raises(ParseError) as exc_info:
            parse_result_json(str(tmp_path))
        assert exc_info.value.error_code == "RESULT_TOO_LARGE"

    def test_u7_unknown_fields_tolerated(self, tmp_path):
        from app.core.result_parser import parse_result_json
        extended = json.dumps({
            "status": "completed",
            "objective_score": 70,
            "pass": False,
            "summary": "合格线以下",
            "unknown_future_field": "future_value",
            "another_field": 42,
        })
        artifacts = self._make_result_file(tmp_path, extended)
        result = parse_result_json(artifacts)
        assert result.objective_score == 70.0
        assert "unknown_future_field" in result.raw


# ═══════════════════════════════════════════════════════════════════════════════
#  U：workspace_snapshot 单元测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestWorkspaceSnapshot:
    """workspace_snapshot.py 单元测试"""

    def test_u7_workspace_not_found(self):
        from app.core.workspace_snapshot import create_code_snapshot, SnapshotError
        with pytest.raises(SnapshotError) as exc_info:
            create_code_snapshot(attempt_id=9999, student_id=99999)
        assert exc_info.value.error_code == "SNAPSHOT_FAILED"

    def test_snapshot_success(self, tmp_path):
        from app.core.workspace_snapshot import create_code_snapshot, SUBMISSIONS_ROOT

        # 创建一个假 workspace
        student_id = 77777
        workspace = Path("data/students") / str(student_id) / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "src").mkdir(exist_ok=True)
        (workspace / "src" / "main.py").write_text("print('hello')")

        # 覆盖 SUBMISSIONS_ROOT 到 tmp_path
        with patch("app.core.workspace_snapshot.SUBMISSIONS_ROOT", tmp_path):
            with patch("app.core.workspace_snapshot.Path.__new__", side_effect=Path.__new__):
                import app.core.workspace_snapshot as ws_mod
                orig_root = ws_mod.SUBMISSIONS_ROOT
                ws_mod.SUBMISSIONS_ROOT = tmp_path
                try:
                    result = create_code_snapshot(attempt_id=1001, student_id=student_id)
                    assert result.file_count >= 1
                    assert result.total_bytes > 0
                    assert result.snapshot_path != ""
                finally:
                    ws_mod.SUBMISSIONS_ROOT = orig_root
                    import shutil
                    shutil.rmtree(str(workspace.parent.parent), ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  C：exam_attempt CRUD 集成测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestExamAttemptCRUD:
    """app/crud/exam_attempt.py 集成测试（内存 SQLite）"""

    @pytest.mark.asyncio
    async def test_c1_create_attempt_pending(self, db_session):
        exam = await _create_published_exam(db_session, "c1")
        attempt = await _create_attempt(db_session, exam)
        assert attempt.id is not None
        assert attempt.status == ExamAttemptStatus.PENDING
        assert attempt.exam_id == exam.id
        assert attempt.student_id == STUDENT_ID
        assert attempt.attempt_exam_mode == "result_run"
        assert isinstance(attempt.attempt_runtime_policy_json, dict)

    @pytest.mark.asyncio
    async def test_c2_concurrent_attempt_detected(self, db_session):
        exam = await _create_published_exam(db_session, "c2")

        # 创建进行中 attempt
        attempt1 = await _create_attempt(db_session, exam, status=ExamAttemptStatus.RUNNING)

        # 检测到进行中
        in_progress = await crud_attempt.get_in_progress_attempt(db_session, STUDENT_ID, exam.id)
        assert in_progress is not None
        assert in_progress.id == attempt1.id

    @pytest.mark.asyncio
    async def test_c2b_scoring_counts_as_in_progress(self, db_session):
        exam = await _create_published_exam(db_session, "c2b")
        await _create_attempt(db_session, exam, status=ExamAttemptStatus.SCORING)
        in_progress = await crud_attempt.get_in_progress_attempt(db_session, STUDENT_ID, exam.id)
        assert in_progress is not None

    @pytest.mark.asyncio
    async def test_c2c_completed_not_in_progress(self, db_session):
        exam = await _create_published_exam(db_session, "c2c")
        await _create_attempt(db_session, exam, status=ExamAttemptStatus.COMPLETED)
        in_progress = await crud_attempt.get_in_progress_attempt(db_session, STUDENT_ID, exam.id)
        assert in_progress is None

    @pytest.mark.asyncio
    async def test_c3_count_all_attempts(self, db_session):
        exam = await _create_published_exam(db_session, "c3")
        assert await crud_attempt.count_all_attempts(db_session, STUDENT_ID, exam.id) == 0
        await _create_attempt(db_session, exam, status=ExamAttemptStatus.COMPLETED)
        await _create_attempt(db_session, exam, status=ExamAttemptStatus.ERROR)
        assert await crud_attempt.count_all_attempts(db_session, STUDENT_ID, exam.id) == 2

    @pytest.mark.asyncio
    async def test_c4_count_completed_attempts_excludes_pending(self, db_session):
        exam = await _create_published_exam(db_session, "c4")
        await _create_attempt(db_session, exam, status=ExamAttemptStatus.COMPLETED)
        await _create_attempt(db_session, exam, status=ExamAttemptStatus.ABORTED)
        await _create_attempt(db_session, exam, status=ExamAttemptStatus.PENDING)  # 不计入
        count = await crud_attempt.count_completed_attempts(db_session, STUDENT_ID, exam.id)
        assert count == 2  # completed + aborted

    @pytest.mark.asyncio
    async def test_c5_update_status_with_path_fields(self, db_session):
        exam = await _create_published_exam(db_session, "c5")
        attempt = await _create_attempt(db_session, exam)
        updated = await crud_attempt.update_attempt_status(
            db_session, attempt, ExamAttemptStatus.RUNNING,
            started_at=datetime.utcnow(),
            sidecar_container_id="abc123",
            submission_snapshot_path="/data/exam_submissions/1/workspace",
        )
        assert updated.status == ExamAttemptStatus.RUNNING
        assert updated.sidecar_container_id == "abc123"
        assert updated.submission_snapshot_path == "/data/exam_submissions/1/workspace"
        assert updated.started_at is not None

    @pytest.mark.asyncio
    async def test_c6_finalize_attempt_computes_duration(self, db_session):
        exam = await _create_published_exam(db_session, "c6")
        attempt = await _create_attempt(db_session, exam)
        # 设置开始时间为 60 秒前
        started = datetime.utcnow() - timedelta(seconds=60)
        attempt = await crud_attempt.update_attempt_status(
            db_session, attempt, ExamAttemptStatus.RUNNING,
            started_at=started,
        )
        finalized = await crud_attempt.finalize_attempt(
            db_session, attempt,
            status=ExamAttemptStatus.COMPLETED,
            objective_score=90.0,
            pass_=True,
            summary="测试通过",
            result_json={"status": "completed", "objective_score": 90, "pass": True, "summary": "测试通过"},
        )
        assert finalized.status == ExamAttemptStatus.COMPLETED
        assert finalized.objective_score == 90.0
        assert finalized.pass_ is True
        assert finalized.duration_ms is not None
        assert finalized.duration_ms >= 59000  # 约 60 秒

    @pytest.mark.asyncio
    async def test_c6b_finalize_clamps_score(self, db_session):
        exam = await _create_published_exam(db_session, "c6b")
        attempt = await _create_attempt(db_session, exam)
        finalized = await crud_attempt.finalize_attempt(
            db_session, attempt,
            status=ExamAttemptStatus.COMPLETED,
            objective_score=150.0,  # 超界
            pass_=True,
            summary="超分了",
        )
        assert finalized.objective_score == 100.0  # clamp

    @pytest.mark.asyncio
    async def test_c6c_finalize_summary_truncated(self, db_session):
        exam = await _create_published_exam(db_session, "c6c")
        attempt = await _create_attempt(db_session, exam)
        long_summary = "a" * 600
        finalized = await crud_attempt.finalize_attempt(
            db_session, attempt,
            status=ExamAttemptStatus.COMPLETED,
            objective_score=70.0,
            pass_=False,
            summary=long_summary,
        )
        assert len(finalized.summary) <= 512

    @pytest.mark.asyncio
    async def test_c7_record_event_sequence_no(self, db_session):
        exam = await _create_published_exam(db_session, "c7")
        attempt = await _create_attempt(db_session, exam)

        e1 = await crud_attempt.record_event(
            db_session, attempt_id=attempt.id,
            event_type=EvidenceEventType.EXAM_ATTEMPT_CREATED,
            payload={"test": True},
        )
        e2 = await crud_attempt.record_event(
            db_session, attempt_id=attempt.id,
            event_type=EvidenceEventType.CODE_SNAPSHOT_STARTED,
        )
        assert e1.sequence_no == 1
        assert e2.sequence_no == 2

    @pytest.mark.asyncio
    async def test_c8_list_events_sorted_by_seq(self, db_session):
        exam = await _create_published_exam(db_session, "c8")
        attempt = await _create_attempt(db_session, exam)

        event_types = [
            EvidenceEventType.EXAM_ATTEMPT_CREATED,
            EvidenceEventType.CODE_SNAPSHOT_STARTED,
            EvidenceEventType.CODE_SNAPSHOT_CREATED,
            EvidenceEventType.SIDECAR_CONTAINER_CREATED,
        ]
        for et in event_types:
            await crud_attempt.record_event(db_session, attempt_id=attempt.id, event_type=et)

        events = await crud_attempt.list_events(db_session, attempt.id)
        assert len(events) == 4
        seq_nos = [e.sequence_no for e in events]
        assert seq_nos == sorted(seq_nos)

    @pytest.mark.asyncio
    async def test_c9_find_stale_pending(self, db_session):
        exam = await _create_published_exam(db_session, "c9")
        attempt = await _create_attempt(db_session, exam)

        # 手动把创建时间设为过去
        from sqlalchemy import update
        await db_session.execute(
            update(ExamAttempt)
            .where(ExamAttempt.id == attempt.id)
            .values(created_at=datetime.utcnow() - timedelta(minutes=15))
        )
        await db_session.commit()

        stale = await crud_attempt.find_stale_pending_attempts(db_session, stale_minutes=10)
        assert any(a.id == attempt.id for a in stale)

    @pytest.mark.asyncio
    async def test_c9b_fresh_pending_not_stale(self, db_session):
        exam = await _create_published_exam(db_session, "c9b")
        await _create_attempt(db_session, exam)
        stale = await crud_attempt.find_stale_pending_attempts(db_session, stale_minutes=10)
        assert len(stale) == 0

    @pytest.mark.asyncio
    async def test_c10_find_timeout_running(self, db_session):
        exam = await _create_published_exam(db_session, "c10")
        attempt = await _create_attempt(db_session, exam)

        # 设为 running，开始时间设为很久以前
        from sqlalchemy import update
        very_old = datetime.utcnow() - timedelta(minutes=20)
        await db_session.execute(
            update(ExamAttempt)
            .where(ExamAttempt.id == attempt.id)
            .values(status=ExamAttemptStatus.RUNNING, started_at=very_old)
        )
        await db_session.commit()

        timeout_list = await crud_attempt.find_timeout_running_attempts(db_session)
        assert any(a.id == attempt.id for a in timeout_list)

    @pytest.mark.asyncio
    async def test_c10b_not_yet_timeout(self, db_session):
        exam = await _create_published_exam(db_session, "c10b")
        attempt = await _create_attempt(db_session, exam)
        from sqlalchemy import update
        just_started = datetime.utcnow() - timedelta(seconds=30)
        await db_session.execute(
            update(ExamAttempt)
            .where(ExamAttempt.id == attempt.id)
            .values(status=ExamAttemptStatus.RUNNING, started_at=just_started)
        )
        await db_session.commit()
        timeout_list = await crud_attempt.find_timeout_running_attempts(db_session)
        assert not any(a.id == attempt.id for a in timeout_list)

    @pytest.mark.asyncio
    async def test_list_student_attempts_sorted_desc(self, db_session):
        exam = await _create_published_exam(db_session, "list_sort")
        a1 = await _create_attempt(db_session, exam, status=ExamAttemptStatus.COMPLETED)
        a2 = await _create_attempt(db_session, exam, status=ExamAttemptStatus.ERROR)
        attempts = await crud_attempt.list_student_attempts(db_session, STUDENT_ID, exam.id)
        assert len(attempts) == 2
        # 最新的在前
        assert attempts[0].id == a2.id

    @pytest.mark.asyncio
    async def test_list_attempts_teacher_pagination(self, db_session):
        exam = await _create_published_exam(db_session, "teacher_page")
        for i in range(5):
            await _create_attempt(db_session, exam, status=ExamAttemptStatus.COMPLETED)
        items, total = await crud_attempt.list_attempts_for_teacher(
            db_session, exam_id=exam.id, page=1, page_size=3
        )
        assert total == 5
        assert len(items) == 3


# ═══════════════════════════════════════════════════════════════════════════════
#  A：学生端 API 端点集成测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestStudentExamAttemptAPI:
    """直接调用 endpoint handler 的集成测试"""

    async def _get_exam_info(self, db, exam_id, user_id=STUDENT_ID):
        from app.api.v1.endpoints.student.exam_attempts import get_exam_run_info
        return await get_exam_run_info(exam_id=exam_id, user_id=user_id, db=db)

    async def _create_attempt(self, db, exam_id, user_id=STUDENT_ID):
        from app.api.v1.endpoints.student.exam_attempts import create_attempt
        from app.schemas.exam_attempt import CreateAttemptRequest
        return await create_attempt(
            body=CreateAttemptRequest(exam_id=exam_id),
            user_id=user_id,
            db=db,
        )

    async def _get_attempt_detail(self, db, attempt_id, user_id=STUDENT_ID):
        from app.api.v1.endpoints.student.exam_attempts import get_attempt_detail
        return await get_attempt_detail(attempt_id=attempt_id, user_id=user_id, db=db)

    async def _abort_attempt(self, db, attempt_id, user_id=STUDENT_ID, reason=None):
        from app.api.v1.endpoints.student.exam_attempts import abort_attempt
        from app.schemas.exam_attempt import AbortAttemptRequest
        return await abort_attempt(
            attempt_id=attempt_id,
            body=AbortAttemptRequest(reason=reason),
            user_id=user_id,
            db=db,
        )

    @pytest.mark.asyncio
    async def test_a1_get_exam_info_published(self, db_session):
        exam = await _create_published_exam(db_session, "a1")
        resp = await self._get_exam_info(db_session, exam.id)
        assert resp.code == 0
        assert resp.data.exam_id == exam.id
        assert resp.data.time_limit_ms == 300000
        assert resp.data.remaining_attempts == 3

    @pytest.mark.asyncio
    async def test_a2_get_exam_info_not_published(self, db_session):
        from fastapi import HTTPException
        exam = await _create_draft_exam(db_session, "a2")
        with pytest.raises(HTTPException) as exc_info:
            await self._get_exam_info(db_session, exam.id)
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["error_code"] == "EXAM_NOT_PUBLISHED"

    @pytest.mark.asyncio
    async def test_a3_get_exam_info_unsupported_mode(self, db_session):
        from fastapi import HTTPException
        exam = await _create_published_exam(db_session, "a3", exam_mode="process_run")
        with pytest.raises(HTTPException) as exc_info:
            await self._get_exam_info(db_session, exam.id)
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["error_code"] == "EXAM_MODE_NOT_SUPPORTED_YET"

    @pytest.mark.asyncio
    async def test_a4_create_attempt_normal(self, db_session):
        exam = await _create_published_exam(db_session, "a4")
        container = await _create_running_container(db_session)
        resp = await self._create_attempt(db_session, exam.id)
        assert resp.code == 0
        assert resp.data.attempt_id is not None
        assert resp.data.status == "pending"

    @pytest.mark.asyncio
    async def test_a5_create_attempt_container_not_running(self, db_session):
        from fastapi import HTTPException
        from app.models.container import SimContainer, ContainerStatus
        exam = await _create_published_exam(db_session, "a5")
        # 创建 stopped 容器
        container = SimContainer(
            user_id=STUDENT_ID,
            container_id="stopped001",
            image_name="gzweb:v1",
            status=ContainerStatus.STOPPED,
            gzbridge_port=7001,
            rosbridge_port=7002,
        )
        db_session.add(container)
        await db_session.commit()
        with pytest.raises(HTTPException) as exc_info:
            await self._create_attempt(db_session, exam.id)
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["error_code"] == "CONTAINER_NOT_RUNNING"

    @pytest.mark.asyncio
    async def test_a5b_create_attempt_no_container(self, db_session):
        from fastapi import HTTPException
        exam = await _create_published_exam(db_session, "a5b")
        # 该学生没有容器
        with pytest.raises(HTTPException) as exc_info:
            await self._create_attempt(db_session, exam.id, user_id=OTHER_STUDENT_ID)
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["error_code"] == "CONTAINER_NOT_RUNNING"

    @pytest.mark.asyncio
    async def test_a6_create_attempt_already_in_progress(self, db_session):
        from fastapi import HTTPException
        exam = await _create_published_exam(db_session, "a6")
        await _create_running_container(db_session)
        # 先创建一个
        await self._create_attempt(db_session, exam.id)
        # 再创建一个 → 409
        with pytest.raises(HTTPException) as exc_info:
            await self._create_attempt(db_session, exam.id)
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["error_code"] == "ATTEMPT_IN_PROGRESS"

    @pytest.mark.asyncio
    async def test_a7_create_attempt_max_exceeded(self, db_session):
        from fastapi import HTTPException
        exam = await _create_published_exam(db_session, "a7", max_attempts=2)
        container = await _create_running_container(db_session)
        # 先用掉 2 次
        for status in [ExamAttemptStatus.COMPLETED, ExamAttemptStatus.ABORTED]:
            await _create_attempt(db_session, exam, container, status)
        # 第 3 次 → 409
        with pytest.raises(HTTPException) as exc_info:
            await self._create_attempt(db_session, exam.id)
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["error_code"] == "MAX_ATTEMPTS_EXCEEDED"

    @pytest.mark.asyncio
    async def test_a8_get_attempt_detail(self, db_session):
        exam = await _create_published_exam(db_session, "a8")
        container = await _create_running_container(db_session)
        attempt = await _create_attempt(db_session, exam, container)
        resp = await self._get_attempt_detail(db_session, attempt.id)
        assert resp.code == 0
        assert resp.data.attempt_id == attempt.id
        assert resp.data.status == "pending"

    @pytest.mark.asyncio
    async def test_a9_get_attempt_forbidden(self, db_session):
        from fastapi import HTTPException
        exam = await _create_published_exam(db_session, "a9")
        container = await _create_running_container(db_session)
        attempt = await _create_attempt(db_session, exam, container, student_id=STUDENT_ID)
        # 其他学生访问 → 403
        with pytest.raises(HTTPException) as exc_info:
            await self._get_attempt_detail(db_session, attempt.id, user_id=OTHER_STUDENT_ID)
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["error_code"] == "FORBIDDEN_NOT_OWNER"

    @pytest.mark.asyncio
    async def test_a10_abort_pending_attempt(self, db_session):
        exam = await _create_published_exam(db_session, "a10")
        container = await _create_running_container(db_session)
        attempt = await _create_attempt(db_session, exam, container)
        resp = await self._abort_attempt(db_session, attempt.id, reason="改变主意")
        assert resp.code == 0
        assert resp.data.status == "aborted"

    @pytest.mark.asyncio
    async def test_a11_abort_other_student_forbidden(self, db_session):
        from fastapi import HTTPException
        exam = await _create_published_exam(db_session, "a11")
        container = await _create_running_container(db_session)
        attempt = await _create_attempt(db_session, exam, container, student_id=STUDENT_ID)
        with pytest.raises(HTTPException) as exc_info:
            await self._abort_attempt(db_session, attempt.id, user_id=OTHER_STUDENT_ID)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_abort_completed_attempt_rejected(self, db_session):
        from fastapi import HTTPException
        exam = await _create_published_exam(db_session, "abort_done")
        container = await _create_running_container(db_session)
        attempt = await _create_attempt(db_session, exam, container, status=ExamAttemptStatus.COMPLETED)
        with pytest.raises(HTTPException) as exc_info:
            await self._abort_attempt(db_session, attempt.id)
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_start_attempt_triggers_async_task(self, db_session):
        """start endpoint 应触发 asyncio.create_task 而不阻塞"""
        exam = await _create_published_exam(db_session, "start_task")
        container = await _create_running_container(db_session)
        attempt = await _create_attempt(db_session, exam, container)

        from app.api.v1.endpoints.student.exam_attempts import start_attempt

        # mock schedule_sidecar，避免真实 Docker 调用
        with patch(
            "app.api.v1.endpoints.student.exam_attempts.schedule_sidecar",
            new_callable=AsyncMock,
        ) as mock_schedule:
            with patch("asyncio.create_task") as mock_task:
                resp = await start_attempt(
                    attempt_id=attempt.id, user_id=STUDENT_ID, db=db_session
                )
        assert resp.code == 0
        mock_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_attempt_wrong_status_rejected(self, db_session):
        from fastapi import HTTPException
        exam = await _create_published_exam(db_session, "start_bad")
        container = await _create_running_container(db_session)
        attempt = await _create_attempt(db_session, exam, container, status=ExamAttemptStatus.RUNNING)

        from app.api.v1.endpoints.student.exam_attempts import start_attempt
        with pytest.raises(HTTPException) as exc_info:
            await start_attempt(attempt_id=attempt.id, user_id=STUDENT_ID, db=db_session)
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["error_code"] == "ATTEMPT_WRONG_STATUS"

    @pytest.mark.asyncio
    async def test_remaining_attempts_decrements(self, db_session):
        """remaining_attempts 随使用次数减少"""
        exam = await _create_published_exam(db_session, "remaining", max_attempts=3)
        container = await _create_running_container(db_session)
        # 用掉 1 次
        await _create_attempt(db_session, exam, container, status=ExamAttemptStatus.COMPLETED)
        resp = await self._get_exam_info(db_session, exam.id)
        assert resp.data.remaining_attempts == 2


# ═══════════════════════════════════════════════════════════════════════════════
#  A：教师端 API 端点集成测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestTeacherExamAttemptAPI:

    @pytest.mark.asyncio
    async def test_a12_list_all_attempts_pagination(self, db_session):
        from app.api.v1.endpoints.teacher.exam_attempts import list_all_attempts
        exam = await _create_published_exam(db_session, "t12")
        container = await _create_running_container(db_session)
        for _ in range(5):
            await _create_attempt(db_session, exam, container)

        resp = await list_all_attempts(
            page=1, page_size=3,
            student_id=None, exam_id=exam.id, status_filter=None,
            _user_id=TEACHER_ID, db=db_session,
        )
        assert resp.code == 0
        assert resp.data.total == 5
        assert len(resp.data.items) == 3

    @pytest.mark.asyncio
    async def test_a12b_filter_by_status(self, db_session):
        from app.api.v1.endpoints.teacher.exam_attempts import list_all_attempts
        exam = await _create_published_exam(db_session, "t12b")
        container = await _create_running_container(db_session)
        await _create_attempt(db_session, exam, container, status=ExamAttemptStatus.COMPLETED)
        await _create_attempt(db_session, exam, container, status=ExamAttemptStatus.ERROR)
        await _create_attempt(db_session, exam, container, status=ExamAttemptStatus.ABORTED)

        resp = await list_all_attempts(
            page=1, page_size=20,
            student_id=None, exam_id=exam.id, status_filter="completed",
            _user_id=TEACHER_ID, db=db_session,
        )
        assert resp.data.total == 1
        assert resp.data.items[0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_a13_get_attempt_full_detail(self, db_session):
        from app.api.v1.endpoints.teacher.exam_attempts import get_attempt_full
        exam = await _create_published_exam(db_session, "t13")
        container = await _create_running_container(db_session)
        attempt = await _create_attempt(db_session, exam, container)
        await _create_user(db_session, STUDENT_ID, "student_t13")

        resp = await get_attempt_full(attempt_id=attempt.id, _user_id=TEACHER_ID, db=db_session)
        assert resp.code == 0
        assert resp.data.attempt_id == attempt.id
        assert resp.data.student.student_id == STUDENT_ID
        assert resp.data.exam.exam_id == exam.id
        assert resp.data.review_status == "pending"

    @pytest.mark.asyncio
    async def test_a13_not_found(self, db_session):
        from fastapi import HTTPException
        from app.api.v1.endpoints.teacher.exam_attempts import get_attempt_full
        with pytest.raises(HTTPException) as exc_info:
            await get_attempt_full(attempt_id=99999, _user_id=TEACHER_ID, db=db_session)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_a14_get_attempt_events(self, db_session):
        from app.api.v1.endpoints.teacher.exam_attempts import get_attempt_events
        exam = await _create_published_exam(db_session, "t14")
        container = await _create_running_container(db_session)
        attempt = await _create_attempt(db_session, exam, container)

        event_types = [
            EvidenceEventType.EXAM_ATTEMPT_CREATED,
            EvidenceEventType.CODE_SNAPSHOT_STARTED,
            EvidenceEventType.CODE_SNAPSHOT_CREATED,
        ]
        for et in event_types:
            await crud_attempt.record_event(db_session, attempt_id=attempt.id, event_type=et)

        resp = await get_attempt_events(attempt_id=attempt.id, _user_id=TEACHER_ID, db=db_session)
        assert resp.code == 0
        assert len(resp.data["items"]) == 3
        assert resp.data["items"][0]["event_type"] == "exam_attempt_created"

    @pytest.mark.asyncio
    async def test_a15_list_exam_attempts(self, db_session):
        from app.api.v1.endpoints.teacher.exam_attempts import list_exam_attempts
        exam = await _create_published_exam(db_session, "t15")
        container = await _create_running_container(db_session)
        await _create_attempt(db_session, exam, container, status=ExamAttemptStatus.COMPLETED)
        await _create_attempt(db_session, exam, container, status=ExamAttemptStatus.ERROR)

        resp = await list_exam_attempts(
            exam_id=exam.id, page=1, page_size=20,
            student_id=None, status_filter=None,
            _user_id=TEACHER_ID, db=db_session,
        )
        assert resp.code == 0
        assert resp.data.total == 2


# ═══════════════════════════════════════════════════════════════════════════════
#  sidecar_manager 关键逻辑单元测试（mock Docker）
# ═══════════════════════════════════════════════════════════════════════════════


class TestSidecarManagerUnit:
    """mock Docker，只测 sidecar_manager 的逻辑分支"""

    @pytest.mark.asyncio
    async def test_build_docker_config_uses_snapshot_fields(self, db_session):
        """build_docker_config 只读 attempt 快照字段，不读 exams"""
        from app.core.sidecar_manager import build_docker_config
        exam = await _create_published_exam(db_session, "mgr1")
        container = await _create_running_container(db_session)
        attempt = await _create_attempt(db_session, exam, container)
        # 设置 snapshot_path 和 artifacts_path
        attempt = await crud_attempt.update_attempt_status(
            db_session, attempt, ExamAttemptStatus.RUNNING,
            submission_snapshot_path="/data/exam_submissions/1/workspace",
            artifacts_path="/data/exam_artifacts/1",
        )
        config = build_docker_config(attempt)
        assert config.attempt_id == attempt.id
        assert "sidecar-exam-" in config.name
        assert config.image == "edubot/sidecar-runner:v1"
        assert "EXAM_ATTEMPT_ID" in config.environment
        assert config.environment["EXAM_ATTEMPT_ID"] == str(attempt.id)
        assert config.environment["EXAM_MODE"] == "result_run"

    @pytest.mark.asyncio
    async def test_build_docker_config_network_mode(self, db_session):
        """有 sim_container_docker_id 时使用 container: 网络模式"""
        from app.core.sidecar_manager import build_docker_config
        exam = await _create_published_exam(db_session, "mgr2")
        container = await _create_running_container(db_session)
        attempt = await _create_attempt(db_session, exam, container)
        attempt = await crud_attempt.update_attempt_status(
            db_session, attempt, ExamAttemptStatus.RUNNING,
            submission_snapshot_path="/tmp/snapshot",
            artifacts_path="/tmp/artifacts",
        )
        config = build_docker_config(attempt)
        assert config.network_mode.startswith("container:")

    @pytest.mark.asyncio
    async def test_schedule_sidecar_snapshot_failure_sets_error(self, db_session):
        """快照失败时 attempt 状态变为 error"""
        from app.core import sidecar_manager
        exam = await _create_published_exam(db_session, "mgr_snap_fail")
        container = await _create_running_container(db_session)
        attempt = await _create_attempt(db_session, exam, container)

        from app.core.workspace_snapshot import SnapshotError

        with patch("app.core.sidecar_manager.AsyncSessionLocal") as mock_session_cls:
            # 构造 async context manager 返回 db_session
            mock_ctx = MagicMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=db_session)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_session_cls.return_value = mock_ctx

            with patch(
                "app.core.sidecar_manager._run_in_executor",
                new_callable=AsyncMock,
                side_effect=SnapshotError("workspace not found", "SNAPSHOT_FAILED"),
            ):
                await sidecar_manager.schedule_sidecar(attempt.id)

        # 刷新 attempt
        await db_session.refresh(attempt)
        assert attempt.status == ExamAttemptStatus.ERROR
        assert attempt.error_code == "SNAPSHOT_FAILED"
