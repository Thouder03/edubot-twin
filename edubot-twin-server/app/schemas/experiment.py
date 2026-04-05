"""
实验相关 Pydantic Schemas（10-S1 同步更新）

变更说明：
- 10-S1-1/3: 移除 is_visible/startup_script_ref 字段
- 10-S1-2: 新增 FileBundleCreate/Response/ListItem
- 10-S1-4: 新增 EnvBundleCreate/Response/ListItem
- 10-S1-5: ExperimentVersion 新增 env_bundle_id
- 10-S1-9: 新增实验状态切换 Schema
- 10-S1-10: 新增版本发布状态切换 Schema
- 10-S1-11: 新增 VersionValidateResponse
"""
from datetime import datetime
from typing import Optional, Literal

from pydantic import BaseModel, Field


# ─── 文件清单 ──────────────────────────────────────────────────────────────────

class FileManifestItem(BaseModel):
    """文件清单中的单个文件项"""
    relative_path: str
    chmod_mode: str = "0755"


# ─── 实验 CRUD Schema ──────────────────────────────────────────────────────────

class ExperimentCreate(BaseModel):
    """创建实验请求体"""
    name: str = Field(..., min_length=1, max_length=128, description="实验名称")
    code: str = Field(..., min_length=1, max_length=64, description="实验唯一编码")
    description: Optional[str] = Field(default=None, max_length=512, description="实验描述")


class ExperimentStatusSwitchRequest(BaseModel):
    """切换实验状态请求体（10-S1-9）"""
    status: Literal["draft", "active", "archived"] = Field(..., description="目标状态")


class ExperimentVersionBase(BaseModel):
    """实验版本基础字段（10-S1: 移除 is_visible/startup_script_ref，新增 env_bundle_id）"""
    version_name: str = Field(..., min_length=1, max_length=64, description="版本号，如 v1.0.0")
    environment_key: str = Field(..., min_length=1, max_length=128, description="环境标识")
    image_name: str = Field(default="gzweb_sim:v1", min_length=1, max_length=200, description="Docker镜像名")
    launch_file_path: str = Field(..., min_length=1, max_length=255, description="ROS launch文件路径")
    launch_args_template: dict = Field(default_factory=dict, description="参数模板JSON")
    file_bundle_id: Optional[int] = None
    env_bundle_id: Optional[int] = None  # 10-S1-5: 新增


class ExperimentVersionCreate(ExperimentVersionBase):
    """创建实验版本请求体"""


class ExperimentVersionUpdate(ExperimentVersionBase):
    """更新实验版本请求体（仅草稿可更新）"""


class ExperimentVersionPublishStatusRequest(BaseModel):
    """切换版本发布状态请求体（10-S1-10）"""
    publish_status: Literal["published", "deprecated"] = Field(..., description="目标发布状态")
    publish_note: Optional[str] = Field(default=None, max_length=512, description="发布/废弃备注")


class ExperimentVersionResponse(BaseModel):
    """实验版本响应体（10-S1: 移除 is_visible/startup_script_ref，新增 env_bundle_id）"""
    version_id: int
    experiment_id: int
    version_name: str
    environment_key: str
    image_name: str
    launch_file_path: str
    launch_args_template: dict
    file_bundle_id: Optional[int] = None
    env_bundle_id: Optional[int] = None  # 10-S1-5
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
    """发布实验请求体（原有端点保留向后兼容）"""
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


# ─── 版本验证 Schema（10-S1-11）───────────────────────────────────────────────

class VersionValidateIssue(BaseModel):
    """版本验证问题项"""
    field: str = Field(..., description="问题所在字段")
    code: str = Field(..., description="错误码（如 missing_image, empty_bundle）")
    severity: Literal["blocking", "warning", "info"] = Field(..., description="严重程度")
    message: str = Field(..., description="问题描述")


class VersionValidateResponse(BaseModel):
    """版本配置验证响应（10-S1-11）"""
    valid: bool = Field(..., description="是否验证通过（无任何问题）")
    has_blocking: bool = Field(..., description="是否存在阻断项（阻止发布）")
    issues: list[VersionValidateIssue] = Field(default_factory=list)


# ─── 文件包 Schema（10-S1-2 新增）────────────────────────────────────────────

class FileBundleCreate(BaseModel):
    """创建文件包请求体"""
    name: str = Field(..., min_length=1, max_length=128, description="文件包名称")


class FileBundleResponse(BaseModel):
    """文件包详情响应体"""
    bundle_id: int
    name: str
    storage_root: str
    file_count: int
    total_size_bytes: int
    file_manifest: list
    validate_status: str
    created_at: datetime
    created_by: int


class FileBundleListItem(BaseModel):
    """文件包列表项（简略）"""
    bundle_id: int
    name: str
    file_count: int
    total_size_bytes: int
    validate_status: str
    created_at: datetime


class FileBundleListResponse(BaseModel):
    """文件包分页列表响应体"""
    total: int
    list: list[FileBundleListItem]


class FileBundleRenameRequest(BaseModel):
    """重命名文件包请求体"""
    name: str = Field(..., min_length=1, max_length=128, description="新名称")


class FileBundleRenameResponse(BaseModel):
    """重命名响应（含引用影响说明）"""
    bundle_id: int
    name: str
    affected_versions: list[dict]  # [{version_id, experiment_name, version_name}]


class FileUploadResponse(BaseModel):
    """文件上传响应体"""
    file_count: int
    total_size_bytes: int


class FileListItem(BaseModel):
    """文件列表项"""
    name: str
    type: Literal["file", "dir"]
    size: Optional[int] = None
    modified_at: Optional[float] = None


class FileListResponse(BaseModel):
    """目录文件列表响应体"""
    items: list[FileListItem]


class FileReadResponse(BaseModel):
    """文件内容读取响应体"""
    content: str
    encoding: str
    modified_at: Optional[float] = None  # 文件修改时间戳（用于客户端冲突检测）


class FileSaveRequest(BaseModel):
    """文件保存请求体"""
    path: str = Field(..., description="文件相对路径")
    content: str = Field(..., description="文件内容")
    modified_at: Optional[float] = Field(default=None, description="客户端持有的修改时间戳（用于冲突检测）")


# ─── 环境包 Schema（10-S1-4 新增）────────────────────────────────────────────

class EnvBundleCreate(BaseModel):
    """创建环境包请求体"""
    name: str = Field(..., min_length=1, max_length=128, description="环境包名称")
    container_target_dir: str = Field(
        default="/home/ubuntu20/catkin_ws",
        max_length=255,
        description="环境文件在容器中的挂载目标目录",
    )
    access_level: Literal["readonly", "readwrite", "hidden"] = Field(
        default="readonly",
        description="学生对环境文件的访问权限",
    )


class EnvBundleResponse(BaseModel):
    """环境包详情响应体"""
    env_bundle_id: int
    name: str
    storage_root: str
    container_target_dir: str
    access_level: str
    file_count: int
    total_size_bytes: int
    created_at: datetime
    created_by: int
    updated_at: datetime


class EnvBundleListItem(BaseModel):
    """环境包列表项（简略）"""
    env_bundle_id: int
    name: str
    container_target_dir: str
    access_level: str
    file_count: int
    created_at: datetime


class EnvBundleListResponse(BaseModel):
    """环境包分页列表响应体"""
    total: int
    list: list[EnvBundleListItem]


class EnvBundleUpdateRequest(BaseModel):
    """更新环境包请求体"""
    name: Optional[str] = Field(default=None, max_length=128)
    container_target_dir: Optional[str] = Field(default=None, max_length=255)
    access_level: Optional[Literal["readonly", "readwrite", "hidden"]] = None


class EnvBundleDryRunByVersionRequest(BaseModel):
    """环境包 Dry Run 请求体（SDD §6.2，按 version_id 读取启动配置）"""
    version_id: int = Field(..., description="关联的实验版本 ID，从中读取 image_name、launch_args 等配置")


class EnvBundleDryRunByVersionResponse(BaseModel):
    """环境包 Dry Run 响应体（SDD §6.2）"""
    container_id: str = Field(..., description="Dry Run 容器 ID（用于停止时传入 DELETE 端点）")
    simulation_url: str = Field(..., description="GzWeb 仿真地址，前端直接跳转复用学生仿真页面")
    rosbridge_url: str = Field(..., description="ROS bridge WebSocket 地址，供仿真页面 ROS3D 接入")


# ── 兼容旧实现（内部使用，后续清理） ─────────────────────────────────────────
class EnvBundleDryRunRequest(BaseModel):
    """环境包 Dry Run 请求体（旧版，已被 EnvBundleDryRunByVersionRequest 替代）"""
    image_name: str = Field(default="gzweb_sim:v1", min_length=1, max_length=200)
    launch_file_path: Optional[str] = Field(default=None, max_length=255)
    launch_args: dict[str, str] = Field(default_factory=dict)
    readiness_timeout_seconds: float = Field(default=20.0, ge=3.0, le=120.0)


class EnvBundleDryRunResponse(BaseModel):
    """环境包 Dry Run 响应体（旧版，已被 EnvBundleDryRunByVersionResponse 替代）"""
    container_id: str
    gzbridge_port: int
    rosbridge_port: int
    gzbridge_url: str
    rosbridge_url: str


# ─── 学生端 Schema ─────────────────────────────────────────────────────────────

class StudentAvailableVersionItem(BaseModel):
    """学生首页可见的实验版本项"""
    version_id: int
    experiment_id: int
    experiment_name: str
    version_name: str
    environment_key: str
    summary: Optional[str] = None


class StudentSimulationStartRequest(BaseModel):
    """开始仿真请求体（10-S1 更新：版本可见性规则已改变）"""
    version_id: int
    force_recreate: bool = False


class StudentSimulationStartResponse(BaseModel):
    """开始仿真响应体"""
    task_id: Optional[str] = None
    container_status: str
    experiment_context: dict


class FileDistributeRequest(BaseModel):
    """文件分发请求体"""
    version_id: int
    selected_paths: list[str] = Field(default_factory=list, description="空数组表示全选清单所有文件")
    mode: Literal["pull", "refresh", "retry"] = "pull"


class FileDistributeResponse(BaseModel):
    """文件分发响应体，202 Accepted"""
    task_id: str
    task_status: str
    accepted_at: str
    target_dir: str


class SimulationTaskStageStatusItem(BaseModel):
    stage: str
    status: Literal["PENDING", "IN_PROGRESS", "SUCCEEDED", "FAILED"]
    elapsed_ms: int


class StudentSimulationTaskResponse(BaseModel):
    task_id: str
    task_status: Literal["PENDING", "IN_PROGRESS", "SUCCEEDED", "FAILED"]
    current_stage: Optional[str] = None
    elapsed_ms: int
    retryable: bool
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    stage_statuses: list[SimulationTaskStageStatusItem]
