"""
考试运行记录 ORM 模型（第12期：Sidecar 执行引擎与考试运行闭环）

包含：
- ExamAttemptStatus：考试尝试状态枚举
- EvidenceEventType：生命周期审计事件类型枚举
- ExamAttempt：考试运行记录主表
- ExamEvidenceEvent：生命周期审计事件表
"""

from datetime import datetime
import enum
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Enum, Float, ForeignKey,
    Index, Integer, JSON, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


# ─── 枚举 ─────────────────────────────────────────────────────────────────────


class ExamAttemptStatus(str, enum.Enum):
    """考试尝试状态枚举（SDD §4.3 状态机）"""
    PENDING = "pending"       # 已创建，未开始执行
    RUNNING = "running"       # Sidecar 容器运行中
    SCORING = "scoring"       # 解析 result.json 中
    COMPLETED = "completed"   # 客观分已入库，等待人工评分
    REVIEWED = "reviewed"     # 第13期：教师已完成人工评分，最终成绩入库
    ABORTED = "aborted"       # 超时 / 学生放弃 / 容器异常
    ERROR = "error"           # 快照失败 / Sidecar 启动失败 / JSON 解析失败


class EvidenceEventType(str, enum.Enum):
    """生命周期审计事件类型（SDD §6.3）"""
    EXAM_ATTEMPT_CREATED = "exam_attempt_created"
    CODE_SNAPSHOT_STARTED = "code_snapshot_started"
    CODE_SNAPSHOT_CREATED = "code_snapshot_created"
    CODE_SNAPSHOT_FAILED = "code_snapshot_failed"
    SIDECAR_CONTAINER_CREATED = "sidecar_container_created"
    SIDECAR_START_FAILED = "sidecar_start_failed"
    SIDECAR_SCRIPT_FINISHED = "sidecar_script_finished"
    SCORING_COMPLETED = "scoring_completed"
    INVALID_RESULT_JSON = "invalid_result_json"
    RESULT_MISSING_FIELDS = "result_missing_fields"
    TIMEOUT_REACHED = "timeout_reached"
    EXAM_ABORTED_BY_STUDENT = "exam_aborted_by_student"
    EXAM_ATTEMPT_FINALIZED = "exam_attempt_finalized"
    SYSTEM_WARNING = "system_warning"
    SYSTEM_ERROR = "system_error"
    # 第13期新增：人工复核事件
    MANUAL_SCORE_SUBMITTED = "manual_score_submitted"   # 教师提交人工评分
    TEACHER_OVERRIDE = "teacher_override"               # 教师覆盖客观分/pass
    FINAL_SCORE_CALCULATED = "final_score_calculated"  # 最终成绩核算完成


class ExamAttemptReviewStatus(str, enum.Enum):
    """人工复核状态"""
    PENDING = "pending"
    REVIEWED = "reviewed"


# ─── 考试运行记录主表 ──────────────────────────────────────────────────────────


class ExamAttempt(Base):
    """
    考试运行记录主表（SDD §6.1）

    记录学生每次参加考试的完整上下文：
    - 快照字段（exam_mode / runtime_policy / panel_policy / scoring_policy / sidecar_policy）
      在 attempt 创建时从 exams 表固化，后续所有逻辑读快照，不回读 exams 当前值
    - 状态机遵循 §4.3
    """
    __tablename__ = "exam_attempts"
    __table_args__ = (
        Index("idx_attempts_student_id", "student_id"),
        Index("idx_attempts_exam_id", "exam_id"),
        Index("idx_attempts_status", "status"),
        Index("idx_attempts_exam_student", "exam_id", "student_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exam_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("exams.id", ondelete="CASCADE"),
        nullable=False, comment="FK → exams.id"
    )
    student_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, comment="FK → users.id（学生）"
    )
    container_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("sim_containers.id", ondelete="SET NULL"),
        nullable=True, comment="关联主仿真容器 DB ID"
    )
    sim_container_docker_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="主仿真容器 Docker ID（快照，用于共享 network）"
    )
    sidecar_container_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="Sidecar Docker 容器 ID"
    )

    # 状态
    status: Mapped[ExamAttemptStatus] = mapped_column(
        Enum(ExamAttemptStatus), default=ExamAttemptStatus.PENDING,
        nullable=False, index=True, comment="考试尝试状态"
    )

    # 创建 attempt 时固化的考试快照字段
    attempt_exam_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="创建时固化的考试模式快照"
    )
    attempt_runtime_policy_json: Mapped[dict] = mapped_column(
        JSON, default=dict, nullable=False, comment="创建时固化的运行策略快照"
    )
    attempt_panel_policy_json: Mapped[dict] = mapped_column(
        JSON, default=dict, nullable=False, comment="创建时固化的面板策略快照"
    )
    attempt_scoring_policy_json: Mapped[dict] = mapped_column(
        JSON, default=dict, nullable=False, comment="创建时固化的评分策略快照"
    )
    attempt_sidecar_policy_json: Mapped[dict] = mapped_column(
        JSON, default=dict, nullable=False,
        comment="创建时固化的 Sidecar 运行配置快照；启动、超时处理一律只读此字段"
    )

    # 文件路径
    submission_snapshot_path: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True, comment="代码快照绝对路径"
    )
    artifacts_path: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True, comment="artifacts 目录路径 /data/exam_artifacts/{attempt_id}/"
    )

    # 评测结果
    result_json: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="完整 Sidecar 输出 JSON"
    )
    objective_score: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, comment="从 result_json.objective_score 解析"
    )
    manual_score: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, comment="人工分（第13期写入）"
    )
    breakdown_json: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="人工评分细项分 JSON（第13期写入）"
    )
    final_score: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, comment="最终分（第13期核算）"
    )
    pass_: Mapped[Optional[bool]] = mapped_column(
        Boolean, nullable=True, name="pass", comment="从 result_json.pass 解析"
    )
    summary: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True, comment="从 result_json.summary 解析"
    )
    custom_fields_json: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="从 result_json.custom_fields 解析"
    )

    # 多阶段（第13期使用，本期为空数组）
    stage_statuses_json: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False, comment="第13期多阶段使用；本期为空数组"
    )

    # artifacts 索引（数据库侧复核主索引）
    artifact_index_json: Mapped[dict] = mapped_column(
        JSON, default=dict, nullable=False, comment="artifacts 文件索引；数据库侧复核主索引"
    )

    # 复核字段
    review_status: Mapped[ExamAttemptReviewStatus] = mapped_column(
        Enum(ExamAttemptReviewStatus), default=ExamAttemptReviewStatus.PENDING,
        nullable=False, comment="人工复核状态"
    )
    teacher_comment: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="教师评语（第13期写入）"
    )

    # 错误信息
    error_code: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="错误码（error 状态时）"
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True, comment="错误详情"
    )

    # 时间字段
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="实际开始时间（快照 + Sidecar 启动成功）"
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="结束时间"
    )
    duration_ms: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="总时长（毫秒）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,
        nullable=False, comment="更新时间"
    )


# ─── 生命周期审计事件表 ────────────────────────────────────────────────────────


class ExamEvidenceEvent(Base):
    """
    考试生命周期审计事件表（SDD §6.2）

    只记录生命周期事件，不记录证据数据（位姿/碰撞采集已废弃）。
    用于教师复核时的事件时间轴展示。
    """
    __tablename__ = "exam_evidence_events"
    __table_args__ = (
        Index("idx_evidence_attempt_id", "attempt_id"),
        Index("idx_evidence_attempt_time", "attempt_id", "event_time_ms"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    attempt_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("exam_attempts.id", ondelete="CASCADE"),
        nullable=False, comment="FK → exam_attempts.id"
    )
    event_type: Mapped[EvidenceEventType] = mapped_column(
        Enum(EvidenceEventType), nullable=False, comment="事件类型"
    )
    event_time_ms: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="毫秒 UNIX 时间"
    )
    sequence_no: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="同 attempt 下序号"
    )
    source: Mapped[str] = mapped_column(
        String(20), default="backend", nullable=False,
        comment="事件来源：backend / sidecar / frontend"
    )
    payload_json: Mapped[dict] = mapped_column(
        JSON, default=dict, nullable=False, comment="事件负载"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, comment="入库时间"
    )
