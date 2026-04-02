from datetime import datetime
import enum
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ExperimentStatus(str, enum.Enum):
    """
    实验状态枚举
    """
    DRAFT = "draft"        # 草稿：仅教师可见，不可分发
    ACTIVE = "active"      # 激活：实验正常运行中
    ARCHIVED = "archived"  # 归档：历史实验，不再使用


class PublishStatus(str, enum.Enum):
    """
    实验版本发布状态枚举
    """
    DRAFT = "draft"            # 草稿：编辑中，不可选
    PUBLISHED = "published"    # 已发布：学生可见并可启动仿真
    DEPRECATED = "deprecated"  # 已废弃：旧版本，建议切换


class Experiment(Base):
    """
    实验主表（第10期新增：实验环境版本化与容器重建主链路）
    用于管理实验的基础元信息，一个实验可以拥有多个版本。
    """
    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="实验名称")
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True, comment="实验唯一编码")
    description: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment="实验描述")
    status: Mapped[ExperimentStatus] = mapped_column(
        Enum(ExperimentStatus), default=ExperimentStatus.DRAFT, nullable=False, comment="实验状态(draft/active/archived)"
    )
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="创建教师ID")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, comment="更新时间"
    )

    # 关联的版本列表
    versions: Mapped[list["ExperimentVersion"]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan", lazy="selectin"
    )


class ExperimentVersion(Base):
    """
    实验版本表
    定义了具体的仿真环境配置，如镜像、启动文件、参数模板等。
    """
    __tablename__ = "experiment_versions"
    __table_args__ = (UniqueConstraint("experiment_id", "version_name", name="uk_exp_version_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False, index=True, comment="所属实验ID"
    )
    version_name: Mapped[str] = mapped_column(String(64), nullable=False, comment="版本号，如 v1.0")
    is_visible: Mapped[bool] = mapped_column(default=True, nullable=False, comment="学生是否可见")
    environment_key: Mapped[str] = mapped_column(String(128), nullable=False, comment="只读环境标识，用于前端展示")
    image_name: Mapped[str] = mapped_column(String(200), default="gzweb_sim:v1", nullable=False, comment="使用的Docker镜像")
    launch_file_path: Mapped[str] = mapped_column(String(255), nullable=False, comment="ROS launch 文件路径")
    launch_args_template: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False, comment="launch 参数模板 JSON")
    startup_script_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="启动脚本引用标识")
    file_bundle_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="关联的实验文件包ID")
    publish_status: Mapped[PublishStatus] = mapped_column(
        Enum(PublishStatus), default=PublishStatus.DRAFT, nullable=False, index=True, comment="发布状态"
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="发布时间")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, comment="更新时间"
    )

    # 关联的实验对象
    experiment: Mapped["Experiment"] = relationship(back_populates="versions", lazy="selectin")


class ExperimentPublishLog(Base):
    """
    实验发布日志表
    记录每次版本发布的详细信息，用于审计和追溯。
    """
    __tablename__ = "experiment_publish_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False, index=True, comment="关联实验ID"
    )
    version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("experiment_versions.id", ondelete="CASCADE"), nullable=False, index=True, comment="关联版本ID"
    )
    operator_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="发布操作人ID")
    publish_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="发布备注")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, comment="发布时间")

