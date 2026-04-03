import enum
from typing import Optional
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
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
    last_heartbeat_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
        comment="前端最后一次心跳时间，用于超时检测"
    )
    purpose: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True,
        comment="容器用途说明（实验名称等）"
    )
    current_version_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="当前绑定实验版本ID（第10期）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship(lazy="selectin", back_populates="containers")

    @property
    def student_id(self) -> int:
        """兼容旧接口中的 student_id 读取。"""
        return self.user_id

    def __repr__(self) -> str:
        return (
            f"<SimContainer(id={self.id}, user_id={self.user_id}, "
            f"status='{self.status}', gzbridge_port={self.gzbridge_port})>"
        )
