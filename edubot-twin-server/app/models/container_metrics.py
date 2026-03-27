from sqlalchemy import String, Integer, Float, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from typing import Optional
from app.db.base import Base


class ContainerMetrics(Base):
    """容器性能指标历史数据"""
    __tablename__ = "container_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    container_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sim_containers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cpu_percent: Mapped[float] = mapped_column(Float, nullable=False)
    memory_mb: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )
    collection_status: Mapped[str] = mapped_column(
        String(20), default="success", nullable=False
    )
    error_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Relationships
    container: Mapped["SimContainer"] = relationship(lazy='selectin')

    def __repr__(self) -> str:
        return (
            f"<ContainerMetrics(id={self.id}, container_id={self.container_id}, "
            f"cpu={self.cpu_percent}%, mem={self.memory_mb}MB)>"
        )
