"""
考试域 Pydantic Schemas（第11期）

覆盖：考试定义 / 环境快照 / 文件快照 / 测评脚本 的全部 CRUD 请求与响应。
"""
from datetime import datetime
from typing import Optional, Literal

from pydantic import BaseModel, Field


# ─── 考试定义 Schema ──────────────────────────────────────────────────────────


class ExamCreateRequest(BaseModel):
    """创建考试请求体"""
    name: str = Field(..., min_length=1, max_length=128, description="考试显示名")
    code: str = Field(..., min_length=1, max_length=64, description="唯一编码，创建后不可改")
    description: Optional[str] = Field(default=None, max_length=512, description="考试说明")
    exam_mode: Literal["result_run", "process_run", "multi_stage_run"] = Field(
        ..., description="考试模式"
    )


class ExamUpdateRequest(BaseModel):
    """更新考试请求体（全部可选，按字段级更新）"""
    name: Optional[str] = Field(default=None, max_length=128)
    description: Optional[str] = Field(default=None, max_length=512)
    exam_mode: Optional[Literal["result_run", "process_run", "multi_stage_run"]] = None
    env_snapshot_id: Optional[int] = None
    file_snapshot_id: Optional[int] = None
    eval_script_id: Optional[int] = None
    runtime_policy: Optional[dict] = None
    panel_policy: Optional[dict] = None
    scoring_policy: Optional[dict] = None
    sidecar_policy: Optional[dict] = None
    teacher_comment_template: Optional[str] = None
    updated_at: Optional[str] = Field(default=None, description="乐观锁：客户端持有的 updated_at ISO 字符串")


class ExamResponse(BaseModel):
    """考试详情响应体"""
    id: int
    name: str
    code: str
    description: Optional[str] = None
    exam_mode: str
    status: str
    env_snapshot_id: Optional[int] = None
    file_snapshot_id: Optional[int] = None
    eval_script_id: Optional[int] = None
    runtime_policy_json: dict = Field(default_factory=dict)
    panel_policy_json: dict = Field(default_factory=dict)
    scoring_policy_json: dict = Field(default_factory=dict)
    sidecar_policy_json: dict = Field(default_factory=dict)
    teacher_comment_template: Optional[str] = None
    created_by: int
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None


class ExamListItem(BaseModel):
    """考试列表项"""
    id: int
    name: str
    code: str
    exam_mode: str
    status: str
    env_snapshot_id: Optional[int] = None
    file_snapshot_id: Optional[int] = None
    eval_script_id: Optional[int] = None
    created_at: datetime
    published_at: Optional[datetime] = None


class ExamListResponse(BaseModel):
    """考试分页列表响应体"""
    total: int
    items: list[ExamListItem]


# ─── 考试环境快照 Schema ──────────────────────────────────────────────────────


class ExamEnvSnapshotCreateRequest(BaseModel):
    """创建空快照请求体"""
    name: str = Field(..., min_length=1, max_length=128, description="快照名")
    container_target_dir: str = Field(
        default="/home/ubuntu20/catkin_ws",
        max_length=255,
        description="容器内挂载目标目录",
    )


class ExamEnvSnapshotCopyRequest(BaseModel):
    """从实验环境复制请求体"""
    source_env_bundle_id: int = Field(..., description="源实验环境包 ID")
    name: str = Field(..., min_length=1, max_length=128, description="新快照名")


class ExamEnvSnapshotResponse(BaseModel):
    """考试环境快照响应体"""
    id: int
    name: str
    source_env_bundle_id: Optional[int] = None
    storage_root: str
    container_target_dir: str
    file_count: int
    total_size_bytes: int
    created_by: int
    created_at: datetime
    updated_at: datetime


class ExamEnvSnapshotListItem(BaseModel):
    """环境快照简略列表项"""
    id: int
    name: str
    container_target_dir: str
    file_count: int
    total_size_bytes: int
    created_at: datetime


class ExamEnvSnapshotListResponse(BaseModel):
    """环境快照分页列表"""
    total: int
    items: list[ExamEnvSnapshotListItem]


class ExamEnvSnapshotUpdateRequest(BaseModel):
    """更新快照请求体"""
    name: Optional[str] = Field(default=None, max_length=128)
    container_target_dir: Optional[str] = Field(default=None, max_length=255)


# ─── 考试文件快照 Schema ──────────────────────────────────────────────────────


class ExamFileSnapshotCreateRequest(BaseModel):
    """创建空文件快照"""
    name: str = Field(..., min_length=1, max_length=128, description="快照名")


class ExamFileSnapshotCopyRequest(BaseModel):
    """从实验文件复制"""
    source_file_bundle_id: int = Field(..., description="源实验文件包 ID")
    name: str = Field(..., min_length=1, max_length=128, description="新快照名")


class ExamFileSnapshotResponse(BaseModel):
    """考试文件快照响应体"""
    id: int
    name: str
    source_file_bundle_id: Optional[int] = None
    storage_root: str
    file_count: int
    total_size_bytes: int
    file_manifest: list
    created_by: int
    created_at: datetime
    updated_at: datetime


class ExamFileSnapshotListItem(BaseModel):
    """文件快照简略列表项"""
    id: int
    name: str
    file_count: int
    total_size_bytes: int
    created_at: datetime


class ExamFileSnapshotListResponse(BaseModel):
    """文件快照分页列表"""
    total: int
    items: list[ExamFileSnapshotListItem]


class ExamFileSnapshotUpdateRequest(BaseModel):
    """更新文件快照"""
    name: Optional[str] = Field(default=None, max_length=128)


# ─── 测评脚本包 Schema ───────────────────────────────────────────────────────


class ExamEvalScriptCreateRequest(BaseModel):
    """创建测评脚本包"""
    name: str = Field(..., min_length=1, max_length=128, description="脚本包名")
    description: Optional[str] = Field(default=None, max_length=512, description="说明")
    entry_point: str = Field(default="evaluate.sh", max_length=128, description="入口脚本相对路径")


class ExamEvalScriptResponse(BaseModel):
    """测评脚本包响应体"""
    id: int
    name: str
    description: Optional[str] = None
    storage_root: str
    entry_point: str
    file_count: int
    total_size_bytes: int
    validate_status: str
    created_by: int
    created_at: datetime
    updated_at: datetime


class ExamEvalScriptListItem(BaseModel):
    """脚本包简略列表项"""
    id: int
    name: str
    description: Optional[str] = None
    entry_point: str
    file_count: int
    total_size_bytes: int
    validate_status: str
    created_at: datetime


class ExamEvalScriptListResponse(BaseModel):
    """脚本包分页列表"""
    total: int
    items: list[ExamEvalScriptListItem]


class ExamEvalScriptUpdateRequest(BaseModel):
    """更新脚本包"""
    name: Optional[str] = Field(default=None, max_length=128)
    description: Optional[str] = Field(default=None, max_length=512)
    entry_point: Optional[str] = Field(default=None, max_length=128)
