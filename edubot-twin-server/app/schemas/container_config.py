from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ContainerDefaultConfigRead(BaseModel):
    id: int
    cpu_limit: float
    memory_limit_mb: int
    shm_size_mb: int
    updated_at: datetime

    model_config = {"from_attributes": True}


class ContainerDefaultConfigUpdate(BaseModel):
    cpu_limit: Optional[float] = Field(None, ge=0.1, le=4.0, description="CPU 核心数 (0.1-4.0)")
    memory_limit_mb: Optional[int] = Field(None, ge=256, le=8192, description="内存限额 (MB)")
    shm_size_mb: Optional[int] = Field(None, ge=128, le=2048, description="共享内存大小 (MB)")
