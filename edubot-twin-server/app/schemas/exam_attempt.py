"""
考试运行记录 Pydantic Schema（第12期）

继承链（SDD §5.2 审查决议）：
  AttemptBaseSchema
    └─ StudentAttemptDetailSchema    （学生自查）
    └─ TeacherAttemptFullSchema      （教师管理：含学生信息 + 考试信息）

错误码：ExamAttemptErrorCode 枚举（统一，禁止自由字符串）
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


# ─── 错误码枚举 ────────────────────────────────────────────────────────────────


class ExamAttemptErrorCode(str, enum.Enum):
    """考试尝试错误码（SDD §5.3，统一枚举，禁止自由字符串）"""
    EXAM_NOT_PUBLISHED = "EXAM_NOT_PUBLISHED"
    EXAM_MODE_NOT_SUPPORTED_YET = "EXAM_MODE_NOT_SUPPORTED_YET"
    CONTAINER_NOT_RUNNING = "CONTAINER_NOT_RUNNING"
    ATTEMPT_IN_PROGRESS = "ATTEMPT_IN_PROGRESS"
    MAX_ATTEMPTS_EXCEEDED = "MAX_ATTEMPTS_EXCEEDED"
    SNAPSHOT_FAILED = "SNAPSHOT_FAILED"
    SIDECAR_START_FAILED = "SIDECAR_START_FAILED"
    ATTEMPT_PENDING_STALE = "ATTEMPT_PENDING_STALE"
    RESULT_INVALID_JSON = "RESULT_INVALID_JSON"
    RESULT_MISSING_FIELDS = "RESULT_MISSING_FIELDS"
    RESULT_MISSING_FILE = "RESULT_MISSING_FILE"
    RESULT_TOO_LARGE = "RESULT_TOO_LARGE"
    SIDECAR_TIMEOUT = "SIDECAR_TIMEOUT"
    FORBIDDEN_NOT_OWNER = "FORBIDDEN_NOT_OWNER"
    ATTEMPT_NOT_FOUND = "ATTEMPT_NOT_FOUND"
    EXAM_NOT_FOUND = "EXAM_NOT_FOUND"
    ATTEMPT_WRONG_STATUS = "ATTEMPT_WRONG_STATUS"
    SCRIPT_FAILED = "SCRIPT_FAILED"


# ─── 请求 Schema ──────────────────────────────────────────────────────────────


class CreateAttemptRequest(BaseModel):
    """POST /students/exam-attempts 请求体"""
    exam_id: int = Field(..., description="考试 ID")


class AbortAttemptRequest(BaseModel):
    """POST /students/exam-attempts/{id}/abort 请求体"""
    reason: Optional[str] = Field(None, description="放弃原因（可选）", max_length=200)


# ─── 第13期：人工评分 / 覆盖请求 ─────────────────────────────────────────────


class ManualScoreBreakdown(BaseModel):
    """人工评分细项分（字段推荐但非强制，额外字段允许）"""
    operation_quality: Optional[float] = Field(None, ge=0, le=100, description="操作规范性")
    path_rationality: Optional[float] = Field(None, ge=0, le=100, description="路径合理性")
    recovery_ability: Optional[float] = Field(None, ge=0, le=100, description="恢复能力")
    stability: Optional[float] = Field(None, ge=0, le=100, description="运行稳定性")
    extra_comment: Optional[str] = Field(None, max_length=500, description="附加评语")

    class Config:
        extra = "allow"


class ManualScoreRequest(BaseModel):
    """POST /teachers/exam-attempts/{id}/manual-score 请求体"""
    manual_score: float = Field(..., ge=0, le=100, description="综合人工分（0-100）")
    breakdown: ManualScoreBreakdown = Field(default_factory=ManualScoreBreakdown, description="细项分")
    comment: Optional[str] = Field(None, max_length=1000, description="教师评语")


class OverrideRequest(BaseModel):
    """POST /teachers/exam-attempts/{id}/override 请求体"""
    objective_score: Optional[float] = Field(None, ge=0, le=100, description="覆盖客观分（需 allow_override_objective=true）")
    pass_flag: Optional[bool] = Field(None, description="覆盖 pass 标记（需 allow_override_pass_flag=true）")
    override_reason: str = Field(..., min_length=1, max_length=500, description="覆盖原因（必填，写入审计日志）")


# ─── 考试运行信息（学生进入考试页时获取） ────────────────────────────────────


class RuntimePolicySchema(BaseModel):
    """运行策略（从 exam.runtime_policy_json 反序列化）"""
    max_duration_ms: int = Field(default=600000, description="最大考试时限（毫秒）")
    max_attempts: int = Field(default=3, description="最大尝试次数")
    allow_debug_before_start: bool = Field(default=True, description="开始前是否允许调试")

    class Config:
        extra = "allow"  # 容忍未知字段


class PanelPolicySchema(BaseModel):
    """面板策略（本期仅传递，不生效）"""
    class Config:
        extra = "allow"


class ExamRunInfoSchema(BaseModel):
    """
    GET /students/exams/{exam_id} 响应体

    学生进入考试页时获取的考试配置信息。
    """
    exam_id: int
    name: str
    description: Optional[str] = None
    exam_mode: str
    runtime_policy: RuntimePolicySchema
    panel_policy: dict = Field(default_factory=dict)
    time_limit_ms: int = Field(..., description="来自 runtime_policy.max_duration_ms")
    remaining_attempts: int = Field(..., description="剩余尝试次数（max_attempts - 已完成尝试数）")


# ─── ResultJson 子结构 ────────────────────────────────────────────────────────


class ResultJsonMetrics(BaseModel):
    """result.json 的 metrics 字段（推荐字段，非强制）"""
    goal_reached: Optional[bool] = None
    elapsed_seconds: Optional[float] = None
    collision_count: Optional[int] = None
    path_length: Optional[float] = None
    stage_count: Optional[int] = None
    stage_passed_count: Optional[int] = None

    class Config:
        extra = "allow"


class ResultJsonSchema(BaseModel):
    """Sidecar 标准 result.json 结构（SDD §7.3）"""
    status: str = Field(..., description="completed / failed（脚本自判）")
    objective_score: float = Field(..., ge=0, le=100, description="客观分 0-100")
    pass_: bool = Field(..., alias="pass", description="是否通过")
    summary: str = Field(..., max_length=500, description="评语")
    metrics: Optional[ResultJsonMetrics] = None
    artifacts: Optional[dict[str, str]] = None
    custom_fields: Optional[dict[str, Any]] = None

    class Config:
        populate_by_name = True
        extra = "allow"


# ─── AttemptBaseSchema（公共基础字段） ────────────────────────────────────────


class AttemptBaseSchema(BaseModel):
    """
    所有 Attempt 响应的公共基础字段（SDD §5.2 继承链根）

    学生端和教师端均从此派生，禁止重复手写字段。
    """
    attempt_id: int
    exam_id: int
    status: str
    attempt_exam_mode: str

    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_ms: Optional[int] = None

    objective_score: Optional[float] = None
    pass_: Optional[bool] = Field(None, alias="pass")
    summary: Optional[str] = None
    result_json: Optional[dict] = None

    error_code: Optional[str] = None
    error_message: Optional[str] = None

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        populate_by_name = True

    @classmethod
    def from_orm(cls, attempt: Any) -> "AttemptBaseSchema":
        return cls(
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


# ─── StudentAttemptDetailSchema（学生自查） ───────────────────────────────────


class StudentAttemptDetailSchema(AttemptBaseSchema):
    """
    GET /students/exam-attempts/{id} 响应体

    学生只能看到自己的 attempt，不含其他学生信息。
    """
    pass


class StudentAttemptSummarySchema(BaseModel):
    """学生尝试列表摘要（不含完整 result_json）"""
    attempt_id: int
    exam_id: int
    status: str
    objective_score: Optional[float] = None
    pass_: Optional[bool] = Field(None, alias="pass")
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    error_code: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
        populate_by_name = True

    @classmethod
    def from_orm(cls, attempt: Any) -> "StudentAttemptSummarySchema":
        return cls(
            attempt_id=attempt.id,
            exam_id=attempt.exam_id,
            status=attempt.status.value,
            objective_score=attempt.objective_score,
            **{"pass": attempt.pass_},
            started_at=attempt.started_at,
            ended_at=attempt.ended_at,
            duration_ms=attempt.duration_ms,
            error_code=attempt.error_code,
            created_at=attempt.created_at,
        )


class CreateAttemptResponse(BaseModel):
    """POST /students/exam-attempts 成功响应"""
    attempt_id: int
    status: str


# ─── TeacherAttemptFullSchema（教师端：含学生信息 + 考试信息） ────────────────


class AttemptStudentInfo(BaseModel):
    """内嵌学生简要信息"""
    student_id: int
    username: str
    real_name: Optional[str] = None


class AttemptExamInfo(BaseModel):
    """内嵌考试简要信息"""
    exam_id: int
    name: str
    exam_mode: str


class TeacherAttemptListItemSchema(BaseModel):
    """教师端运行记录列表条目（不含完整 result_json）"""
    attempt_id: int
    exam_id: int
    status: str
    student: AttemptStudentInfo
    objective_score: Optional[float] = None
    pass_: Optional[bool] = Field(None, alias="pass")
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    error_code: Optional[str] = None
    review_status: str
    manual_score: Optional[float] = None
    final_score: Optional[float] = None
    created_at: datetime

    class Config:
        populate_by_name = True


class TeacherAttemptFullSchema(AttemptBaseSchema):
    """
    GET /teachers/exam-attempts/{id} 响应体

    教师端完整详情：公共基础字段 + 学生信息 + 考试信息 + artifacts 下载信息。
    第13期扩展：manual_score / final_score / breakdown_json。
    """
    student: AttemptStudentInfo
    exam: AttemptExamInfo
    review_status: str
    manual_score: Optional[float] = None
    final_score: Optional[float] = None
    breakdown_json: Optional[dict] = None
    teacher_comment: Optional[str] = None
    artifact_index_json: dict = Field(default_factory=dict)
    sidecar_container_id: Optional[str] = None
    attempt_scoring_policy_json: dict = Field(default_factory=dict)
    # 第14期新增：学生代码快照路径（用于判断是否可查看提交代码）
    submission_snapshot_path: Optional[str] = None


# ─── 生命周期事件 Schema ──────────────────────────────────────────────────────


class EvidenceEventSchema(BaseModel):
    """生命周期审计事件（用于教师端时间轴）"""
    id: int
    attempt_id: int
    event_type: str
    event_time_ms: int
    sequence_no: int
    source: str
    payload_json: dict
    created_at: datetime

    class Config:
        from_attributes = True

    @classmethod
    def from_orm(cls, event: Any) -> "EvidenceEventSchema":
        return cls(
            id=event.id,
            attempt_id=event.attempt_id,
            event_type=event.event_type.value,
            event_time_ms=event.event_time_ms,
            sequence_no=event.sequence_no,
            source=event.source,
            payload_json=event.payload_json,
            created_at=event.created_at,
        )


# ─── 分页响应通用结构 ─────────────────────────────────────────────────────────


class AttemptListResponse(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
