from datetime import datetime
from typing import Optional, Literal

from pydantic import BaseModel, Field


class FileManifestItem(BaseModel):
    """文件清单中的单个文件项"""
    relative_path: str
    chmod_mode: str = "0755"


class ExperimentCreate(BaseModel):
    """创建实验请求体"""
    name: str = Field(..., min_length=1, max_length=128, description="实验名称")
    code: str = Field(..., min_length=1, max_length=64, description="实验唯一编码")
    description: Optional[str] = Field(default=None, max_length=512, description="实验描述")


class ExperimentVersionBase(BaseModel):
    """实验版本基础字段"""
    version_name: str = Field(..., min_length=1, max_length=64, description="版本号，如 v1.0.0")
    environment_key: str = Field(..., min_length=1, max_length=128, description="环境标识")
    image_name: str = Field(default="gzweb_sim:v1", min_length=1, max_length=200, description="Docker镜像名")
    launch_file_path: str = Field(..., min_length=1, max_length=255, description="ROS launch文件路径")
    launch_args_template: dict = Field(default_factory=dict, description="参数模板JSON")
    startup_script_ref: Optional[str] = Field(default=None, max_length=255, description="启动脚本引用标识")
    file_bundle_id: Optional[int] = None
    is_visible: bool = True


class ExperimentVersionCreate(ExperimentVersionBase):
    """创建实验版本请求体"""


class ExperimentVersionUpdate(ExperimentVersionBase):
    """更新实验版本请求体（仅草稿可更新）"""


class ExperimentVersionResponse(BaseModel):
    """实验版本响应体"""
    version_id: int
    experiment_id: int
    version_name: str
    is_visible: bool
    environment_key: str
    image_name: str
    launch_file_path: str
    launch_args_template: dict
    startup_script_ref: Optional[str] = None
    file_bundle_id: Optional[int] = None
    publish_status: str
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ExperimentResponse(BaseModel):
    """实验基础信息响应体"""
    experiment_id: int
    name: str
    code: str
    description: Optional[str]
    status: str
    created_by: int
    created_at: datetime
    updated_at: datetime


class ExperimentListItem(BaseModel):
    """实验列表项（简略信息）"""
    experiment_id: int
    name: str
    code: str
    status: str
    latest_version: Optional[str] = None
    published_at: Optional[datetime] = None


class ExperimentListResponse(BaseModel):
    """实验分页列表响应体"""
    total: int
    list: list[ExperimentListItem]


class ExperimentPublishRequest(BaseModel):
    """发布实验请求体"""
    publish_note: Optional[str] = Field(default=None, max_length=512, description="发布备注")


class ExperimentPublishResponse(BaseModel):
    """发布操作成功响应"""
    publish_id: int
    published_at: datetime
    operator: int


class ExperimentPublishLogItem(BaseModel):
    """发布日志项"""
    publish_id: int
    experiment_id: int
    version_id: int
    operator: int
    note: Optional[str]
    created_at: datetime


class ExperimentPublishLogListResponse(BaseModel):
    """发布日志列表响应体"""
    total: int
    list: list[ExperimentPublishLogItem]


class ExperimentDetailResponse(BaseModel):
    """实验完整详情响应体（含版本和日志）"""
    base_info: ExperimentResponse
    versions: list[ExperimentVersionResponse]
    publish_logs: list[ExperimentPublishLogItem]


class StudentAvailableVersionItem(BaseModel):
    """学生首页可见的实验版本项"""
    version_id: int
    experiment_id: int
    experiment_name: str
    version_name: str
    environment_key: str
    summary: Optional[str] = None


class StudentSimulationStartRequest(BaseModel):
    """开始仿真请求体（第10期新增：需传入版本ID）"""
    version_id: int
    force_recreate: bool = False


class StudentSimulationStartResponse(BaseModel):
    """开始仿真响应体"""
    task_id: Optional[str] = None
    container_status: str
    experiment_context: dict


class FileDistributeRequest(BaseModel):
    """文件分发请求体（SDD §6: POST /students/simulation/files/distribute）"""
    version_id: int
    selected_paths: list[str] = Field(default_factory=list, description="空数组表示全选清单所有文件")
    mode: Literal["pull", "refresh", "retry"] = "pull"


class FileDistributeResponse(BaseModel):
    """文件分发响应体，202 Accepted"""
    task_id: str
    task_status: str
    accepted_at: str          # ISO 8601 字符串，避免 JSONResponse 序列化问题
    target_dir: str


class SimulationTaskStageStatusItem(BaseModel):
    stage: str
    status: Literal["PENDING", "IN_PROGRESS", "SUCCEEDED", "FAILED"]
    elapsed_ms: int


class StudentSimulationTaskResponse(BaseModel):
    task_id: str
    task_status: Literal["PENDING", "IN_PROGRESS", "SUCCEEDED", "FAILED"]
    elapsed_ms: int
    retryable: bool
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    stage_statuses: list[SimulationTaskStageStatusItem]

