from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class ContainerMetricsBase(BaseModel):
    """容器性能指标基础模型"""
    cpu_percent: float
    memory_mb: int
    collection_status: str = "success"
    error_message: Optional[str] = None


class ContainerMetricsCreate(ContainerMetricsBase):
    """创建容器性能指标"""
    container_id: int


class ContainerMetricsInDB(ContainerMetricsBase):
    """数据库中的容器性能指标"""
    id: int
    container_id: int
    timestamp: datetime

    class Config:
        from_attributes = True
