"""
考试域 ORM 模型（第11期：考试域数据基座与教师端资源管理）

包含：
- Exam：考试定义主表（含 6 段式配置 JSON 字段）
- ExamEnvSnapshot：考试环境快照
- ExamFileSnapshot：考试文件快照
- ExamEvalScript：测评脚本包
- ExamMode / ExamStatus / ExamEvalScriptValidateStatus 枚举
"""

from datetime import datetime
import enum
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


# ─── 枚举 ─────────────────────────────────────────────────────────────────────


class ExamMode(str, enum.Enum):
    """考试模式枚举"""
    RESULT_RUN = "result_run"            # 结果型自动评测
    PROCESS_RUN = "process_run"          # 过程型操作评测
    MULTI_STAGE_RUN = "multi_stage_run"  # 多阶段编排评测


class ExamStatus(str, enum.Enum):
    """考试发布状态枚举"""
    DRAFT = "draft"          # 草稿：教师端完全可编辑；学生端不可见
    PUBLISHED = "published"  # 已发布：冻结字段写保护；学生端可见并可参加
    ARCHIVED = "archived"    # 已归档：学生端不可见；教师仍可查看；可重新发布


class ExamEvalScriptValidateStatus(str, enum.Enum):
    """测评脚本校验状态枚举"""
    PENDING = "pending"    # 上传后待验证
    VALID = "valid"        # 存在 entry_point 文件且可读
    INVALID = "invalid"    # 未找到 entry_point 或读取失败


# ─── 考试定义主表 ──────────────────────────────────────────────────────────────


class Exam(Base):
    """
    考试定义主表（SDD §6.1）

    包含考试的基础信息和 4 段式策略配置（runtime / panel / scoring / sidecar）。
    考试一旦发布，关键配置字段冻结（由 API 层实施写保护）。
    """
    __tablename__ = "exams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="考试显示名")
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True, comment="唯一编码")
    description: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment="考试说明")
    exam_mode: Mapped[ExamMode] = mapped_column(
        Enum(ExamMode), default=ExamMode.RESULT_RUN, nullable=False, comment="考试模式"
    )
    status: Mapped[ExamStatus] = mapped_column(
        Enum(ExamStatus), default=ExamStatus.DRAFT, nullable=False, index=True, comment="发布状态"
    )

    # 资源引用（可选，草稿阶段可为空）
    env_snapshot_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("exam_env_snapshots.id", ondelete="SET NULL"),
        nullable=True, comment="FK → exam_env_snapshots.id"
    )
    file_snapshot_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("exam_file_snapshots.id", ondelete="SET NULL"),
        nullable=True, comment="FK → exam_file_snapshots.id"
    )
    eval_script_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("exam_eval_scripts.id", ondelete="SET NULL"),
        nullable=True, comment="FK → exam_eval_scripts.id"
    )

    # 4 段式策略配置 JSON
    runtime_policy_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False, comment="运行策略")
    panel_policy_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False, comment="面板策略")
    scoring_policy_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False, comment="评分策略")
    sidecar_policy_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False, comment="Sidecar 策略")

    # 教师评语模板
    teacher_comment_template: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="教师评语模板")

    # 审计字段
    created_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True, comment="创建教师 ID"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, comment="更新时间"
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="首次发布时间")


# ─── 考试环境快照 ──────────────────────────────────────────────────────────────


class ExamEnvSnapshot(Base):
    """
    考试环境快照表（SDD §6.2）

    从实验环境包（ExperimentEnvBundle）物理复制而来，
    存储结构与实验环境包一致，但生命周期完全独立。
    """
    __tablename__ = "exam_env_snapshots"
    __table_args__ = (
        UniqueConstraint("name", "created_by", name="uk_exam_env_snapshot_name_by_creator"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="快照名")
    source_env_bundle_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="来源实验环境包 ID（可追溯，非外键）"
    )
    storage_root: Mapped[str] = mapped_column(String(512), nullable=False, comment="存储根目录")
    container_target_dir: Mapped[str] = mapped_column(
        String(255), default="/home/ubuntu20/catkin_ws", nullable=False,
        comment="容器内挂载目标目录"
    )
    file_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="文件数")
    total_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False, comment="总大小（字节）")
    created_by: Mapped[int] = mapped_column(Integer, nullable=False, comment="创建教师 ID")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, comment="更新时间"
    )


# ─── 考试文件快照 ──────────────────────────────────────────────────────────────


class ExamFileSnapshot(Base):
    """
    考试文件快照表（SDD §6.3）

    从实验文件包（ExperimentFileBundle）物理复制而来。
    """
    __tablename__ = "exam_file_snapshots"
    __table_args__ = (
        UniqueConstraint("name", "created_by", name="uk_exam_file_snapshot_name_by_creator"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="快照名")
    source_file_bundle_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="来源实验文件包 ID（可追溯）"
    )
    storage_root: Mapped[str] = mapped_column(String(512), nullable=False, comment="存储根目录")
    file_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="文件数")
    total_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False, comment="总大小（字节）")
    file_manifest: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False,
        comment="文件清单 JSON 数组：[{relative_path, chmod_mode}]"
    )
    created_by: Mapped[int] = mapped_column(Integer, nullable=False, comment="创建教师 ID")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, comment="更新时间"
    )


# ─── 测评脚本包 ───────────────────────────────────────────────────────────────


class ExamEvalScript(Base):
    """
    测评脚本包表（SDD §6.4）

    供 Sidecar 执行引擎使用的测评脚本合集。
    files 子协议与环境快照/文件快照共用统一的 BundleFileService。
    """
    __tablename__ = "exam_eval_scripts"
    __table_args__ = (
        UniqueConstraint("name", "created_by", name="uk_exam_eval_script_name_by_creator"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="脚本包名")
    description: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment="说明")
    storage_root: Mapped[str] = mapped_column(String(512), nullable=False, comment="存储根目录")
    entry_point: Mapped[str] = mapped_column(
        String(128), default="evaluate.sh", nullable=False, comment="平台调用入口脚本相对路径"
    )
    file_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="文件数")
    total_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False, comment="总大小（字节）")
    validate_status: Mapped[ExamEvalScriptValidateStatus] = mapped_column(
        Enum(ExamEvalScriptValidateStatus), default=ExamEvalScriptValidateStatus.PENDING,
        nullable=False, comment="校验状态"
    )
    created_by: Mapped[int] = mapped_column(Integer, nullable=False, comment="创建教师 ID")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, comment="更新时间"
    )
