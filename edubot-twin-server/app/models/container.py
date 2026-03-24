import enum
from typing import Optional
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ContainerStatus(str, enum.Enum):
    """容器生命周期状态"""
    CREATING = "creating"      # Docker 正在创建容器
    RUNNING = "running"        # 容器运行中，gzbridge 可用
    STOPPED = "stopped"        # 容器已停止
    ERROR = "error"            # 创建/运行出错
    REMOVING = "removing"      # 正在删除容器


class SimContainer(Base):
    """仿真容器记录"""
    __tablename__ = "sim_containers"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    container_id: Mapped[Optional[str]] = mapped_column(
        String(64), unique=True, nullable=True,
        comment="Docker 容器 ID (sha256 前 12 位)"
    )
    student_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("students.id"), nullable=False, index=True
    )
    image_name: Mapped[str] = mapped_column(
        String(200), nullable=False, default="edubot/gazebo-ros:latest"
    )
    status: Mapped[ContainerStatus] = mapped_column(
        Enum(ContainerStatus), default=ContainerStatus.CREATING, nullable=False
    )
    gzbridge_port: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
        comment="gzbridge WebSocket 宿主机映射端口"
    )
    rosbridge_port: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
        comment="rosbridge WebSocket 宿主机映射端口"
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True,
        comment="Docker 操作异常信息"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<SimContainer(id={self.id}, student_id={self.student_id}, "
            f"status='{self.status}', gzbridge_port={self.gzbridge_port})>"
        )
