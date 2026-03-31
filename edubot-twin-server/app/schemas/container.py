import os
from datetime import datetime
from typing import List, Optional

from pydantic import AliasChoices, BaseModel, Field, computed_field

from app.models.container import ContainerStatus


class ContainerCreate(BaseModel):
    """创建容器请求体"""

    user_id: int = Field(validation_alias=AliasChoices("user_id", "student_id"))
    image_name: str = "gzweb_sim:v1"
    cpu_limit: float = Field(default=1.0, ge=0.1, le=4.0, description="CPU 配额 (核心数)")
    memory_limit: int = Field(default=2048, ge=256, le=8192, description="内存配额 (MB)")

    @property
    def student_id(self) -> int:
        """兼容旧代码中的 student_id 读取。"""
        return self.user_id


class ContainerResponse(BaseModel):
    """容器完整信息"""
    id: int
    container_id: Optional[str] = None
    student_id: int
    status: str
    image_name: str
    gzbridge_port: Optional[int] = None
    rosbridge_port: Optional[int] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # 计算字段：根据宿主机地址 + 端口拼接 URL
    @computed_field  # type: ignore[misc]
    @property
    def gzbridge_url(self) -> Optional[str]:
        if self.gzbridge_port is None:
            return None
        host = os.getenv("SERVER_HOST", "localhost")
        return f"http://{host}:{self.gzbridge_port}"

    @computed_field  # type: ignore[misc]
    @property
    def rosbridge_url(self) -> Optional[str]:
        if self.rosbridge_port is None:
            return None
        host = os.getenv("SERVER_HOST", "localhost")
        return f"ws://{host}:{self.rosbridge_port}"

    model_config = {"from_attributes": True}


class ContainerStatusResponse(BaseModel):
    """容器简要状态（学生端用）"""
    id: int
    status: str
    gzbridge_url: Optional[str] = None
    rosbridge_url: Optional[str] = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_with_host(cls, obj: object) -> "ContainerStatusResponse":
        """从 ORM 对象构建，自动计算 URL"""
        host = os.getenv("SERVER_HOST", "localhost")
        gzbridge_url = (
            f"http://{host}:{obj.gzbridge_port}"  # type: ignore[union-attr]
            if obj.gzbridge_port  # type: ignore[union-attr]
            else None
        )
        rosbridge_url = (
            f"ws://{host}:{obj.rosbridge_port}"  # type: ignore[union-attr]
            if obj.rosbridge_port  # type: ignore[union-attr]
            else None
        )
        return cls(
            id=obj.id,  # type: ignore[union-attr]
            status=obj.status,  # type: ignore[union-attr]
            gzbridge_url=gzbridge_url,
            rosbridge_url=rosbridge_url,
        )


class ContainerMonitorInfo(BaseModel):
    """容器实时监控信息（教师监控端专用）"""
    id: int
    container_id: Optional[str] = None
    student_id: int
    student_name: str
    student_username: str
    purpose: str = ""
    status: str
    image_name: str
    cpu_percent: float = 0.0
    memory_mb: int = 0
    memory_limit_mb: int = 2048
    uptime_seconds: int = 0
    created_at: datetime
    last_heartbeat_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ContainerMonitorListResponse(BaseModel):
    """容器监控列表响应"""
    total: int
    list: List[ContainerMonitorInfo]


class StopOnExitRequest(BaseModel):
    """页面退出时停止容器的请求体（供 sendBeacon 使用，Token 放 body）"""
    token: str


class BatchOperationRequest(BaseModel):
    """批量操作请求体"""
    container_ids: list[int]


class BatchOperationResult(BaseModel):
    """批量操作结果"""
    container_id: int
    success: bool
    message: str


class BatchOperationResponse(BaseModel):
    """批量操作响应"""
    total: int
    success_count: int
    failed_count: int
    results: list[BatchOperationResult]
