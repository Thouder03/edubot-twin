import os
from pydantic import BaseModel, computed_field
from typing import Optional
from datetime import datetime

from app.models.container import ContainerStatus


class ContainerCreate(BaseModel):
    """创建容器请求体"""
    student_id: int
    image_name: str = "gzweb_sim:v1"


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
