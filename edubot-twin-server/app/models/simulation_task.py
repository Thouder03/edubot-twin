from datetime import datetime
import enum
from typing import Optional

from sqlalchemy import DateTime, Enum, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SimulationTaskStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class SimulationTaskStage(str, enum.Enum):
    # 容器重建阶段
    PREPARING_CONFIG = "PREPARING_CONFIG"
    STOPPING_OLD_CONTAINER = "STOPPING_OLD_CONTAINER"
    CREATING_NEW_CONTAINER = "CREATING_NEW_CONTAINER"
    # 10-S1-8: 拆分 HEALTH_CHECKING 为两个细粒度阶段（前端可分阶段展示进度）
    CHECKING_GZWEB = "CHECKING_GZWEB"          # 等待 gzweb 端口（容器8080/宿主机gz_port）就绪
    CHECKING_ROSBRIDGE = "CHECKING_ROSBRIDGE"   # 等待 rosbridge 端口（容器9090/宿主机ros_port）就绪
    # 保留旧值向后兼容（新阶段顺序：CREATING_NEW_CONTAINER → CHECKING_GZWEB → CHECKING_ROSBRIDGE）
    HEALTH_CHECKING = "HEALTH_CHECKING"
    # 文件分发阶段
    VALIDATING_MANIFEST = "VALIDATING_MANIFEST"
    DISTRIBUTING_FILES = "DISTRIBUTING_FILES"
    SETTING_PERMISSIONS = "SETTING_PERMISSIONS"


class SimulationTask(Base):
    """第10期：仿真重建任务记录（最小任务化实现）"""

    __tablename__ = "simulation_tasks"

    task_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    student_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    container_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    target_version_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    status: Mapped[SimulationTaskStatus] = mapped_column(
        Enum(SimulationTaskStatus), default=SimulationTaskStatus.PENDING, nullable=False, index=True
    )
    current_stage: Mapped[SimulationTaskStage] = mapped_column(
        Enum(SimulationTaskStage), default=SimulationTaskStage.PREPARING_CONFIG, nullable=False
    )

    stage_statuses: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    retryable: Mapped[bool] = mapped_column(default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
