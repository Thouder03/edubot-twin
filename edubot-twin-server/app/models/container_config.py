from datetime import datetime

from sqlalchemy import DateTime, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ContainerDefaultConfig(Base):
    """仿真容器全局默认资源配置（单例，id 永远为 1）"""
    __tablename__ = "container_default_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    cpu_limit: Mapped[float] = mapped_column(
        Float, nullable=False, default=2.0,
        comment="CPU 核心数限制，传给 Docker nano_cpus = cpu_limit * 1e9"
    )
    memory_limit_mb: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1024,
        comment="内存限制 (MB)，传给 Docker mem_limit"
    )
    shm_size_mb: Mapped[int] = mapped_column(
        Integer, nullable=False, default=512,
        comment="共享内存大小 (MB)，传给 Docker shm_size"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
