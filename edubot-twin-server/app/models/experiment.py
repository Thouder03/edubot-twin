from datetime import datetime
import enum
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
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

    10-S1 变更：
    - 删除 is_visible（语义与 publish_status + Experiment.status 重叠）
    - 删除 startup_script_ref（由环境包根目录下 startup.sh 文件替代）
    - 新增 env_bundle_id（关联环境文件包）

    学生可见性规则（替代原 is_visible）：
        Experiment.status = 'active' AND ExperimentVersion.publish_status = 'published'
    """
    __tablename__ = "experiment_versions"
    __table_args__ = (UniqueConstraint("experiment_id", "version_name", name="uk_exp_version_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False, index=True, comment="所属实验ID"
    )
    version_name: Mapped[str] = mapped_column(String(64), nullable=False, comment="版本号，如 v1.0")
    # 10-S1-1: 删除 is_visible（可见性统一由 publish_status + Experiment.status 决定）
    environment_key: Mapped[str] = mapped_column(String(128), nullable=False, comment="只读环境标识，用于前端展示")
    image_name: Mapped[str] = mapped_column(String(200), default="gzweb_sim:v1", nullable=False, comment="使用的Docker镜像")
    launch_file_path: Mapped[str] = mapped_column(String(255), nullable=False, comment="ROS launch 文件路径")
    launch_args_template: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False, comment="launch 参数模板 JSON")
    # 10-S1-3: 删除 startup_script_ref（由环境包根目录下 startup.sh 文件替代）
    file_bundle_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="关联的实验文件包ID")
    # 10-S1-5: 新增 env_bundle_id（外键引用环境文件包）
    env_bundle_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("experiment_env_bundles.id", ondelete="SET NULL"),
        nullable=True, comment="关联环境文件包ID"
    )
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


class FileBundleStatus(str, enum.Enum):
    """实验文件包校验状态"""
    PENDING = "pending"   # 上传后待校验
    VALID = "valid"       # 已通过校验，可分发
    INVALID = "invalid"   # 校验失败，不可分发


class ExperimentFileBundle(Base):
    """
    实验文件包表（S1 重构：文件包与实验解耦）

    10-S1 变更：
    - 删除 experiment_id（文件包独立于实验，通过版本外键引用）
    - 删除 checksum（无实际校验流程，移除）
    - 新增 name（文件包显示名称，创建教师内唯一）
    - 新增 storage_root（服务器存储根目录）
    - 新增 file_count（文件数量，上传时自动计算）
    - 新增 total_size_bytes（文件包总大小）

    保留字段变更：
    - file_manifest: 保留 JSON 数组，上传后由后端扫描 storage_root 自动重建
    - validate_status: 上传后自动设为 valid；storage_root 为空时设为 invalid
    """
    __tablename__ = "experiment_file_bundles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 10-S1-2: 新增 name（每个教师内唯一，唯一约束 per created_by）
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="文件包显示名称")
    # 10-S1-2: 新增 storage_root（自动生成，格式 /data/file_bundles/{id}）
    storage_root: Mapped[str] = mapped_column(String(512), nullable=False, comment="服务器存储根目录")
    # 10-S1-2: 新增 file_count（上传时自动计算）
    file_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="文件数量")
    # 10-S1-2: 新增 total_size_bytes（上传时自动计算）
    total_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False, comment="文件包总大小（字节）")
    file_manifest: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False,
        comment="文件清单 JSON 数组，元素格式：{relative_path, chmod_mode}"
    )
    validate_status: Mapped[FileBundleStatus] = mapped_column(
        Enum(FileBundleStatus), default=FileBundleStatus.PENDING, nullable=False, comment="校验状态"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, comment="上传时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, comment="更新时间"
    )
    created_by: Mapped[int] = mapped_column(Integer, nullable=False, comment="上传教师ID")


class EnvBundleAccessLevel(str, enum.Enum):
    """环境文件包学生访问级别"""
    READONLY = "readonly"    # 学生只读
    READWRITE = "readwrite"  # 学生可读写
    HIDDEN = "hidden"        # 学生不可见


class ExperimentEnvBundle(Base):
    """
    实验环境文件包表（S1-4 新增）

    存储教师配置的环境文件（launch 文件、config 文件等）以及启动脚本。
    启动脚本以文件形式存储在 {storage_root}/startup.sh，不存入数据库。
    创建环境包时后端自动生成 startup.sh 模板文件。
    """
    __tablename__ = "experiment_env_bundles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="环境包名称")
    storage_root: Mapped[str] = mapped_column(String(512), nullable=False, comment="环境文件存储根目录")
    container_target_dir: Mapped[str] = mapped_column(
        String(255), default="/home/ubuntu20/catkin_ws", nullable=False,
        comment="环境文件在容器中的挂载目标目录"
    )
    access_level: Mapped[EnvBundleAccessLevel] = mapped_column(
        Enum(EnvBundleAccessLevel), default=EnvBundleAccessLevel.READONLY,
        nullable=False, comment="学生对环境文件的访问权限"
    )
    file_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="环境文件数量")
    total_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False, comment="总大小（字节）")
    created_by: Mapped[int] = mapped_column(Integer, nullable=False, comment="创建教师ID")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, comment="更新时间"
    )


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
