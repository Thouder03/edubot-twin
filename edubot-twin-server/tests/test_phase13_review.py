"""
第13期测试：教师复核、面板策略与最终成绩核算（SDD §11.1）

单元测试（F - FinalScoreCalculator）：
  F1  正常双权重核算（objective + manual）
  F2  manual_score 缺失时退化为纯客观分
  F3  分数 clamp 到 [0, 100]
  F4  pass_threshold 判断（刚好及格 / 刚好不及格）
  F5  validate_override_allowed：允许覆盖客观分
  F6  validate_override_allowed：禁止覆盖客观分 → 返回错误描述
  F7  validate_override_allowed：允许覆盖 pass
  F8  validate_override_allowed：禁止覆盖 pass → 返回错误描述

CRUD 集成测试（C - CRUD）：
  C1  apply_manual_score：写入 manual_score / final_score / review_status=reviewed
  C2  apply_manual_score：breakdown_json / teacher_comment 正确写入
  C3  apply_manual_score：status 变为 REVIEWED
  C4  apply_override：覆盖 objective_score
  C5  apply_override：覆盖 pass_flag

API 集成测试（A - API Handler）：
  A1  GET artifacts：artifacts 目录存在时返回文件列表
  A2  GET artifacts：artifacts 目录不存在时 artifacts_available=false
  A3  GET artifacts/file：读取 JSON 文件返回文本内容
  A4  GET artifacts/file：路径穿越 → 403
  A5  GET artifacts/file：文件超 5MB → 413
  A6  GET artifacts/file：文件不存在 → 404
  A7  POST manual-score：attempt=completed → 写入 final_score / status=reviewed
  A8  POST manual-score：attempt=pending → 409 ATTEMPT_NOT_COMPLETED
  A9  POST manual-score：attempt=reviewed → 允许重新评分
  A10 POST override：allow_override_objective=true → 重算 final_score
  A11 POST override：allow_override_objective=false → 403 OVERRIDE_NOT_ALLOWED
  A12 POST override：override 直接覆盖 pass_flag
"""

import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.crud import exam_attempt as crud_attempt
from app.models.exam import ExamMode, ExamStatus
from app.models.exam_attempt import (
    ExamAttempt,
    ExamAttemptStatus,
    ExamAttemptReviewStatus,
    EvidenceEventType,
)

# ═══════════════════════════════════════════════════════════════════════════════
#  常量
# ═══════════════════════════════════════════════════════════════════════════════

STUDENT_ID = 10
TEACHER_ID = 1


# ═══════════════════════════════════════════════════════════════════════════════
#  辅助函数
# ═══════════════════════════════════════════════════════════════════════════════


async def _create_published_exam(
    db,
    code_suffix="",
    scoring_policy: Optional[dict] = None,
):
    from app.models.exam import Exam

    exam = Exam(
        name=f"复核测试考试_{code_suffix}",
        code=f"review_{code_suffix}_{id(db)}",
        exam_mode=ExamMode.RESULT_RUN,
        status=ExamStatus.PUBLISHED,
        runtime_policy_json={"max_duration_ms": 300000, "max_attempts": 3},
        panel_policy_json={},
        scoring_policy_json=scoring_policy or {
            "weight_objective": 0.7,
            "weight_manual": 0.3,
            "pass_threshold": 60.0,
            "allow_override_objective": True,
            "allow_override_pass_flag": True,
        },
        sidecar_policy_json={"image": "edubot/sidecar-runner:v1"},
        created_by=TEACHER_ID,
    )
    db.add(exam)
    await db.commit()
    await db.refresh(exam)
    return exam


async def _create_attempt(
    db,
    exam,
    status=ExamAttemptStatus.COMPLETED,
    objective_score: float = 80.0,
    scoring_policy: Optional[dict] = None,
    artifacts_path: Optional[str] = None,
):
    attempt = await crud_attempt.create_attempt(
        db,
        exam_id=exam.id,
        student_id=STUDENT_ID,
        container_id=None,
        sim_container_docker_id=None,
        attempt_exam_mode=exam.exam_mode.value,
        attempt_runtime_policy_json=exam.runtime_policy_json or {},
        attempt_panel_policy_json=exam.panel_policy_json or {},
        attempt_scoring_policy_json=scoring_policy or exam.scoring_policy_json or {},
        attempt_sidecar_policy_json=exam.sidecar_policy_json or {},
    )
    if status != ExamAttemptStatus.PENDING:
        attempt = await crud_attempt.update_attempt_status(db, attempt, status)
    if objective_score is not None:
        attempt = await crud_attempt.finalize_attempt(
            db,
            attempt,
            status=ExamAttemptStatus.COMPLETED,
            objective_score=objective_score,
            pass_=objective_score >= 60,
            summary="测试评测完成",
        )
    if artifacts_path:
        attempt.artifacts_path = artifacts_path
        await db.commit()
        await db.refresh(attempt)
    return attempt


async def _create_user(db, user_id=STUDENT_ID, username="test_student"):
    from app.models.student import User
    from sqlalchemy import select

    result = await db.execute(select(User).where(User.id == user_id))
    if result.scalar_one_or_none():
        return
    user = User(
        id=user_id,
        username=username,
        password_hash="hashed",
        real_name="测试学生",
        role_code="student",
        role_id="10",
    )
    db.add(user)
    await db.commit()


def _mock_user_id(user_id=TEACHER_ID):
    return MagicMock(return_value=user_id)


# ═══════════════════════════════════════════════════════════════════════════════
#  F：final_score_calculator 单元测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestFinalScoreCalculator:
    """final_score_calculator.py 单元测试"""

    def _policy(self, w_obj=0.7, w_man=0.3, threshold=60.0, allow_obj=True, allow_pass=True):
        return {
            "weight_objective": w_obj,
            "weight_manual": w_man,
            "pass_threshold": threshold,
            "allow_override_objective": allow_obj,
            "allow_override_pass_flag": allow_pass,
        }

    def test_f1_normal_dual_weight(self):
        from app.core.final_score_calculator import calculate_final_score

        final, passed = calculate_final_score(
            objective_score=80.0,
            manual_score=90.0,
            scoring_policy=self._policy(w_obj=0.7, w_man=0.3, threshold=60.0),
        )
        expected = 80.0 * 0.7 + 90.0 * 0.3  # = 56 + 27 = 83
        assert abs(final - expected) < 0.001
        assert passed is True

    def test_f2_manual_score_missing_degrades_to_objective(self):
        from app.core.final_score_calculator import calculate_final_score

        final, passed = calculate_final_score(
            objective_score=75.0,
            manual_score=None,
            scoring_policy=self._policy(),
        )
        # 降级：final = objective
        assert abs(final - 75.0) < 0.001
        assert passed is True

    def test_f3_score_clamp_above_100(self):
        from app.core.final_score_calculator import calculate_final_score

        final, passed = calculate_final_score(
            objective_score=100.0,
            manual_score=100.0,
            scoring_policy=self._policy(w_obj=0.8, w_man=0.8),
        )
        assert final == 100.0  # clamp

    def test_f3b_score_clamp_below_0(self):
        from app.core.final_score_calculator import calculate_final_score

        final, _ = calculate_final_score(
            objective_score=0.0,
            manual_score=0.0,
            scoring_policy=self._policy(w_obj=0.7, w_man=0.3),
        )
        assert final == 0.0

    def test_f4_pass_threshold_just_pass(self):
        from app.core.final_score_calculator import calculate_final_score

        final, passed = calculate_final_score(
            objective_score=60.0,
            manual_score=None,
            scoring_policy=self._policy(w_obj=1.0, w_man=0.0, threshold=60.0),
        )
        assert passed is True

    def test_f4b_pass_threshold_just_fail(self):
        from app.core.final_score_calculator import calculate_final_score

        final, passed = calculate_final_score(
            objective_score=59.9,
            manual_score=None,
            scoring_policy=self._policy(w_obj=1.0, w_man=0.0, threshold=60.0),
        )
        assert passed is False

    def test_f5_override_objective_allowed(self):
        from app.core.final_score_calculator import validate_override_allowed

        err = validate_override_allowed(
            self._policy(allow_obj=True),
            wants_override_objective=True,
        )
        assert err is None

    def test_f6_override_objective_forbidden(self):
        from app.core.final_score_calculator import validate_override_allowed

        err = validate_override_allowed(
            self._policy(allow_obj=False),
            wants_override_objective=True,
        )
        assert err is not None
        assert "allow_override_objective=false" in err

    def test_f7_override_pass_allowed(self):
        from app.core.final_score_calculator import validate_override_allowed

        err = validate_override_allowed(
            self._policy(allow_pass=True),
            wants_override_pass=True,
        )
        assert err is None

    def test_f8_override_pass_forbidden(self):
        from app.core.final_score_calculator import validate_override_allowed

        err = validate_override_allowed(
            self._policy(allow_pass=False),
            wants_override_pass=True,
        )
        assert err is not None
        assert "allow_override_pass_flag=false" in err


# ═══════════════════════════════════════════════════════════════════════════════
#  C：CRUD 集成测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestReviewCRUD:
    """apply_manual_score / apply_override CRUD 集成测试"""

    @pytest.mark.asyncio
    async def test_c1_apply_manual_score_writes_fields(self, db_session):
        exam = await _create_published_exam(db_session, "crud1")
        attempt = await _create_attempt(db_session, exam)

        updated = await crud_attempt.apply_manual_score(
            db_session,
            attempt,
            manual_score=88.0,
            breakdown_json={"operation_quality": 90, "stability": 85},
            teacher_comment="操作规范，路径合理",
            final_score=83.6,
            pass_=True,
        )

        assert updated.manual_score == 88.0
        assert abs(updated.final_score - 83.6) < 0.001
        assert updated.teacher_comment == "操作规范，路径合理"

    @pytest.mark.asyncio
    async def test_c2_apply_manual_score_breakdown_stored(self, db_session):
        exam = await _create_published_exam(db_session, "crud2")
        attempt = await _create_attempt(db_session, exam)

        bd = {"operation_quality": 95, "path_rationality": 80, "stability": 90}
        updated = await crud_attempt.apply_manual_score(
            db_session,
            attempt,
            manual_score=90.0,
            breakdown_json=bd,
            final_score=85.0,
            pass_=True,
        )

        assert updated.breakdown_json == bd

    @pytest.mark.asyncio
    async def test_c3_apply_manual_score_status_becomes_reviewed(self, db_session):
        exam = await _create_published_exam(db_session, "crud3")
        attempt = await _create_attempt(db_session, exam)

        assert attempt.status == ExamAttemptStatus.COMPLETED

        updated = await crud_attempt.apply_manual_score(
            db_session,
            attempt,
            manual_score=70.0,
            final_score=72.0,
            pass_=True,
        )

        assert updated.status == ExamAttemptStatus.REVIEWED
        assert updated.review_status == ExamAttemptReviewStatus.REVIEWED

    @pytest.mark.asyncio
    async def test_c4_apply_override_objective_score(self, db_session):
        exam = await _create_published_exam(db_session, "crud4")
        attempt = await _create_attempt(db_session, exam, objective_score=50.0)

        updated = await crud_attempt.apply_override(
            db_session,
            attempt,
            objective_score=70.0,
            final_score=70.0,
        )

        assert abs(updated.objective_score - 70.0) < 0.001

    @pytest.mark.asyncio
    async def test_c5_apply_override_pass_flag(self, db_session):
        exam = await _create_published_exam(db_session, "crud5")
        attempt = await _create_attempt(db_session, exam, objective_score=55.0)

        # 客观上未通过，教师覆盖为通过
        updated = await crud_attempt.apply_override(
            db_session,
            attempt,
            pass_flag=True,
        )

        assert updated.pass_ is True


# ═══════════════════════════════════════════════════════════════════════════════
#  A：API 端点集成测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestReviewAPI:
    """exam_attempts_review.py 端点测试"""

    # ── artifacts ────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_a1_get_artifacts_with_files(self, db_session, tmp_path):
        """artifacts 目录存在时返回文件列表"""
        from app.api.v1.endpoints.teacher.exam_attempts_review import get_artifacts_tree

        # 创建实际文件
        (tmp_path / "result.json").write_text('{"status":"ok"}')
        (tmp_path / "eval.log").write_text("log content")
        (tmp_path / "screenshot.png").write_bytes(b"\x89PNG\r\n")

        exam = await _create_published_exam(db_session, "a1")
        attempt = await _create_attempt(db_session, exam, artifacts_path=str(tmp_path))

        response = await get_artifacts_tree(
            attempt_id=attempt.id,
            _user_id=TEACHER_ID,
            db=db_session,
        )

        data = response.data
        assert data["artifacts_available"] is True
        names = {f["name"] for f in data["files"]}
        assert "result.json" in names
        assert "eval.log" in names
        assert "screenshot.png" in names

    @pytest.mark.asyncio
    async def test_a2_get_artifacts_dir_missing(self, db_session):
        """artifacts 目录不存在时 artifacts_available=False"""
        from app.api.v1.endpoints.teacher.exam_attempts_review import get_artifacts_tree

        exam = await _create_published_exam(db_session, "a2")
        attempt = await _create_attempt(db_session, exam, artifacts_path="/nonexistent/path/999")

        response = await get_artifacts_tree(
            attempt_id=attempt.id,
            _user_id=TEACHER_ID,
            db=db_session,
        )

        assert response.data["artifacts_available"] is False
        assert response.data["files"] == []

    @pytest.mark.asyncio
    async def test_a3_get_artifact_file_text(self, db_session, tmp_path):
        """读取 JSON 文件返回 utf-8 文本"""
        from app.api.v1.endpoints.teacher.exam_attempts_review import get_artifact_file

        content = '{"objective_score": 85, "pass": true}'
        (tmp_path / "result.json").write_text(content)

        exam = await _create_published_exam(db_session, "a3")
        attempt = await _create_attempt(db_session, exam, artifacts_path=str(tmp_path))

        response = await get_artifact_file(
            attempt_id=attempt.id,
            path="result.json",
            _user_id=TEACHER_ID,
            db=db_session,
        )

        assert response.data["encoding"] == "utf-8"
        assert response.data["content"] == content

    @pytest.mark.asyncio
    async def test_a4_get_artifact_file_path_traversal(self, db_session, tmp_path):
        """路径穿越攻击 → 403"""
        from fastapi import HTTPException
        from app.api.v1.endpoints.teacher.exam_attempts_review import get_artifact_file

        exam = await _create_published_exam(db_session, "a4")
        attempt = await _create_attempt(db_session, exam, artifacts_path=str(tmp_path))

        with pytest.raises(HTTPException) as exc_info:
            await get_artifact_file(
                attempt_id=attempt.id,
                path="../../etc/passwd",
                _user_id=TEACHER_ID,
                db=db_session,
            )
        assert exc_info.value.status_code == 403
        assert "PATH_TRAVERSAL" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_a5_get_artifact_file_too_large(self, db_session, tmp_path):
        """文件超 5MB → 413"""
        from fastapi import HTTPException
        from app.api.v1.endpoints.teacher.exam_attempts_review import (
            get_artifact_file,
            ARTIFACT_PREVIEW_MAX_BYTES,
        )

        large_file = tmp_path / "big.log"
        large_file.write_bytes(b"x" * (ARTIFACT_PREVIEW_MAX_BYTES + 1))

        exam = await _create_published_exam(db_session, "a5")
        attempt = await _create_attempt(db_session, exam, artifacts_path=str(tmp_path))

        with pytest.raises(HTTPException) as exc_info:
            await get_artifact_file(
                attempt_id=attempt.id,
                path="big.log",
                _user_id=TEACHER_ID,
                db=db_session,
            )
        assert exc_info.value.status_code == 413
        assert "ARTIFACT_TOO_LARGE" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_a6_get_artifact_file_not_found(self, db_session, tmp_path):
        """文件不存在 → 404"""
        from fastapi import HTTPException
        from app.api.v1.endpoints.teacher.exam_attempts_review import get_artifact_file

        exam = await _create_published_exam(db_session, "a6")
        attempt = await _create_attempt(db_session, exam, artifacts_path=str(tmp_path))

        with pytest.raises(HTTPException) as exc_info:
            await get_artifact_file(
                attempt_id=attempt.id,
                path="nonexistent.json",
                _user_id=TEACHER_ID,
                db=db_session,
            )
        assert exc_info.value.status_code == 404

    # ── manual-score ──────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_a7_submit_manual_score_completed(self, db_session):
        """completed 状态 → 人工评分写入，final_score 核算，status=reviewed"""
        from app.api.v1.endpoints.teacher.exam_attempts_review import submit_manual_score
        from app.schemas.exam_attempt import ManualScoreRequest, ManualScoreBreakdown

        scoring_policy = {
            "weight_objective": 0.6,
            "weight_manual": 0.4,
            "pass_threshold": 60.0,
        }
        exam = await _create_published_exam(db_session, "a7", scoring_policy=scoring_policy)
        attempt = await _create_attempt(db_session, exam, objective_score=70.0)

        body = ManualScoreRequest(
            manual_score=90.0,
            breakdown=ManualScoreBreakdown(operation_quality=90, stability=90),
            comment="表现优秀",
        )

        response = await submit_manual_score(
            attempt_id=attempt.id,
            body=body,
            user_id=TEACHER_ID,
            db=db_session,
        )

        data = response.data
        assert data.manual_score == 90.0
        # final = 70 * 0.6 + 90 * 0.4 = 42 + 36 = 78
        assert abs(data.final_score - 78.0) < 0.01
        assert data.review_status == "reviewed"
        assert data.teacher_comment == "表现优秀"

    @pytest.mark.asyncio
    async def test_a8_submit_manual_score_wrong_status(self, db_session):
        """pending 状态 → 409 ATTEMPT_NOT_COMPLETED"""
        from fastapi import HTTPException
        from app.api.v1.endpoints.teacher.exam_attempts_review import submit_manual_score
        from app.schemas.exam_attempt import ManualScoreRequest, ManualScoreBreakdown

        exam = await _create_published_exam(db_session, "a8")
        # 创建 pending 状态 attempt（不经过 finalize）
        attempt = await crud_attempt.create_attempt(
            db_session,
            exam_id=exam.id,
            student_id=STUDENT_ID,
            container_id=None,
            sim_container_docker_id=None,
            attempt_exam_mode=exam.exam_mode.value,
            attempt_runtime_policy_json={},
            attempt_panel_policy_json={},
            attempt_scoring_policy_json=exam.scoring_policy_json,
            attempt_sidecar_policy_json={},
        )

        body = ManualScoreRequest(
            manual_score=80.0,
            breakdown=ManualScoreBreakdown(),
        )
        with pytest.raises(HTTPException) as exc_info:
            await submit_manual_score(
                attempt_id=attempt.id,
                body=body,
                user_id=TEACHER_ID,
                db=db_session,
            )
        assert exc_info.value.status_code == 409
        assert "ATTEMPT_NOT_COMPLETED" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_a9_submit_manual_score_reviewed_allowed(self, db_session):
        """reviewed 状态（已评过一次）→ 允许重新评分"""
        from app.api.v1.endpoints.teacher.exam_attempts_review import submit_manual_score
        from app.schemas.exam_attempt import ManualScoreRequest, ManualScoreBreakdown

        exam = await _create_published_exam(db_session, "a9")
        attempt = await _create_attempt(db_session, exam, objective_score=75.0)
        # 先提交一次
        attempt = await crud_attempt.apply_manual_score(
            db_session,
            attempt,
            manual_score=70.0,
            final_score=72.5,
            pass_=True,
        )
        assert attempt.status == ExamAttemptStatus.REVIEWED

        # 再次提交（修改评分）
        body = ManualScoreRequest(
            manual_score=85.0,
            breakdown=ManualScoreBreakdown(),
        )
        response = await submit_manual_score(
            attempt_id=attempt.id,
            body=body,
            user_id=TEACHER_ID,
            db=db_session,
        )
        assert response.data.manual_score == 85.0

    # ── override ──────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_a10_override_objective_allowed(self, db_session):
        """allow_override_objective=True → 覆盖客观分并重算 final_score"""
        from app.api.v1.endpoints.teacher.exam_attempts_review import override_scores
        from app.schemas.exam_attempt import OverrideRequest

        scoring_policy = {
            "weight_objective": 1.0,
            "weight_manual": 0.0,
            "pass_threshold": 60.0,
            "allow_override_objective": True,
            "allow_override_pass_flag": False,
        }
        exam = await _create_published_exam(db_session, "a10", scoring_policy=scoring_policy)
        attempt = await _create_attempt(db_session, exam, objective_score=50.0)

        body = OverrideRequest(
            objective_score=75.0,
            override_reason="录入错误，已确认",
        )
        response = await override_scores(
            attempt_id=attempt.id,
            body=body,
            user_id=TEACHER_ID,
            db=db_session,
        )

        assert abs(response.data.objective_score - 75.0) < 0.01
        # final = 75 * 1.0 + 0 * 0 = 75
        assert abs(response.data.final_score - 75.0) < 0.01

    @pytest.mark.asyncio
    async def test_a11_override_objective_forbidden(self, db_session):
        """allow_override_objective=False → 403 OVERRIDE_NOT_ALLOWED"""
        from fastapi import HTTPException
        from app.api.v1.endpoints.teacher.exam_attempts_review import override_scores
        from app.schemas.exam_attempt import OverrideRequest

        scoring_policy = {
            "weight_objective": 1.0,
            "weight_manual": 0.0,
            "pass_threshold": 60.0,
            "allow_override_objective": False,
            "allow_override_pass_flag": False,
        }
        exam = await _create_published_exam(db_session, "a11", scoring_policy=scoring_policy)
        attempt = await _create_attempt(db_session, exam)

        body = OverrideRequest(
            objective_score=90.0,
            override_reason="试图强行覆盖",
        )
        with pytest.raises(HTTPException) as exc_info:
            await override_scores(
                attempt_id=attempt.id,
                body=body,
                user_id=TEACHER_ID,
                db=db_session,
            )
        assert exc_info.value.status_code == 403
        assert "OVERRIDE_NOT_ALLOWED" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_a12_override_pass_flag_direct(self, db_session):
        """覆盖 pass_flag：直接写入 pass，不重算分数"""
        from app.api.v1.endpoints.teacher.exam_attempts_review import override_scores
        from app.schemas.exam_attempt import OverrideRequest

        scoring_policy = {
            "weight_objective": 1.0,
            "weight_manual": 0.0,
            "pass_threshold": 60.0,
            "allow_override_objective": False,
            "allow_override_pass_flag": True,
        }
        exam = await _create_published_exam(db_session, "a12", scoring_policy=scoring_policy)
        # 客观分 55，未通过
        attempt = await _create_attempt(db_session, exam, objective_score=55.0)
        assert attempt.pass_ is False

        body = OverrideRequest(
            pass_flag=True,
            override_reason="学生特殊情况，教学委员会决议通过",
        )
        response = await override_scores(
            attempt_id=attempt.id,
            body=body,
            user_id=TEACHER_ID,
            db=db_session,
        )
        assert response.data.pass_ is True
        # 分数未变
        assert abs(response.data.objective_score - 55.0) < 0.01
