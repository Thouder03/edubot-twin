"""
成绩预览相关 Schema（第16期）

职责边界：本文件存放涉及跨表 JOIN 聚合视图的响应 Schema，
与 exam_attempt.py 中以单 ORM 对象为中心的 Schema 职责分离。

- GradePreviewItem / GradePreviewListResponse: 教师端成绩预览列表
- StudentGradeSummaryItem: 学生端我的成绩列表（每考试最高分摘要）
- StudentAttemptGradeDetailItem: 学生端某考试所有尝试详情
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.schemas.exam_attempt import AttemptStudentInfo


# ─── 教师端成绩预览 ──────────────────────────────────────────────────────────


class GradePreviewItem(BaseModel):
    """教师成绩预览列表条目（含 result_json_display、custom_fields）"""
    attempt_id: int
    exam_id: int
    exam_name: str
    student: AttemptStudentInfo
    status: str
    objective_score: Optional[float] = None
    manual_score: Optional[float] = None
    final_score: Optional[float] = None
    pass_: Optional[bool] = Field(None, alias="pass")
    summary: Optional[str] = None
    teacher_comment: Optional[str] = None
    review_status: str
    # result_json 去掉 artifacts 键后的完整内容（后端负责剔除，禁止前端自行过滤）
    result_json_display: Optional[dict[str, Any]] = None
    custom_fields: Optional[dict[str, Any]] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    created_at: datetime

    class Config:
        populate_by_name = True


class GradePreviewListResponse(BaseModel):
    """教师成绩预览分页响应"""
    items: list[GradePreviewItem]
    total: int
    page: int
    page_size: int


# ─── 学生端成绩汇总 ──────────────────────────────────────────────────────────


class StudentGradeSummaryItem(BaseModel):
    """学生端：每考试最高分摘要（来自 my-grade-summary 接口）"""
    exam_id: int
    exam_name: str
    exam_code: str
    best_attempt_id: int
    objective_score: Optional[float] = None
    final_score: Optional[float] = None
    pass_: Optional[bool] = Field(None, alias="pass")
    # summary 截断 200 字（后端截断，不在 Schema 层处理）
    summary: Optional[str] = None
    teacher_comment: Optional[str] = None
    status: str
    ended_at: Optional[datetime] = None

    class Config:
        populate_by_name = True


class StudentAttemptGradeDetailItem(BaseModel):
    """学生端：某考试单次尝试的成绩详情（含评语 + 代码快照标记）"""
    attempt_id: int
    status: str
    objective_score: Optional[float] = None
    final_score: Optional[float] = None
    pass_: Optional[bool] = Field(None, alias="pass")
    summary: Optional[str] = None
    teacher_comment: Optional[str] = None
    custom_fields: Optional[dict[str, Any]] = None
    # 前端根据此字段决定是否显示"查看代码"按钮
    has_code_snapshot: bool
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    created_at: datetime

    class Config:
        populate_by_name = True
