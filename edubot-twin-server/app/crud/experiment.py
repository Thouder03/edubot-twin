"""
实验相关 CRUD 操作（10-S1 重构）

主要变更：
- 10-S1-2: ExperimentFileBundle CRUD 适配新字段（name/storage_root/file_count/total_size_bytes）
- 10-S1-4: ExperimentEnvBundle CRUD（新增）
- 10-S1-9: 实验状态切换与删除
- 10-S1-10: 版本发布状态切换与删除
- 10-S1-11: 版本验证
- 10-S1-12: 学生端可见性过滤（改为 Experiment.status=active + publish_status=published）
"""
from datetime import datetime
from typing import Optional
import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.experiment import (
    EnvBundleAccessLevel,
    Experiment,
    ExperimentEnvBundle,
    ExperimentFileBundle,
    ExperimentPublishLog,
    ExperimentStatus,
    ExperimentVersion,
    FileBundleStatus,
    PublishStatus,
)


logger = logging.getLogger(__name__)


# ─── Experiment CRUD ───────────────────────────────────────────────────────────

async def create_experiment(
    db: AsyncSession,
    *,
    name: str,
    code: str,
    description: Optional[str],
    created_by: int,
) -> Experiment:
    """
    创建实验主记录
    """
    obj = Experiment(
        name=name,
        code=code,
        description=description,
        created_by=created_by,
        status=ExperimentStatus.DRAFT,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


async def get_experiment(db: AsyncSession, experiment_id: int) -> Optional[Experiment]:
    """通过 ID 获取实验详情"""
    result = await db.execute(select(Experiment).where(Experiment.id == experiment_id))
    return result.scalar_one_or_none()


async def get_experiment_by_code(db: AsyncSession, code: str) -> Optional[Experiment]:
    """通过编码获取实验详情"""
    result = await db.execute(select(Experiment).where(Experiment.code == code))
    return result.scalar_one_or_none()


async def list_experiments(
    db: AsyncSession,
    *,
    page: int,
    page_size: int,
    keyword: Optional[str],
    status: Optional[str],
):
    """分页查询实验列表"""
    query = select(Experiment)
    count_query = select(func.count()).select_from(Experiment)

    if keyword:
        like = f"%{keyword}%"
        query = query.where((Experiment.name.like(like)) | (Experiment.code.like(like)))
        count_query = count_query.where((Experiment.name.like(like)) | (Experiment.code.like(like)))

    if status:
        query = query.where(Experiment.status == status)
        count_query = count_query.where(Experiment.status == status)

    total = (await db.execute(count_query)).scalar_one()
    rows = (
        await db.execute(
            query.order_by(Experiment.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return list(rows), int(total)


async def switch_experiment_status(
    db: AsyncSession,
    *,
    experiment: Experiment,
    new_status: str,
) -> Experiment:
    """
    切换实验状态（10-S1-9）

    状态机规则（SDD §5.4）：
        draft → active → archived → active
        draft → 删除（无版本时）
    """
    valid_transitions = {
        "draft": {"active"},
        "active": {"draft", "archived"},
        "archived": {"active"},
    }
    current = experiment.status.value
    allowed = valid_transitions.get(current, set())
    logger.info(
        "[experiment_status_switch] experiment_id=%s current=%s target=%s allowed=%s",
        experiment.id,
        current,
        new_status,
        sorted(list(allowed)),
    )
    if new_status not in allowed:
        logger.warning(
            "[experiment_status_switch_invalid] experiment_id=%s current=%s target=%s allowed=%s",
            experiment.id,
            current,
            new_status,
            sorted(list(allowed)),
        )
        raise ValueError(f"INVALID_STATUS_TRANSITION: {current} → {new_status}")

    experiment.status = ExperimentStatus(new_status)
    experiment.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(experiment)
    logger.info(
        "[experiment_status_switch_done] experiment_id=%s new_status=%s",
        experiment.id,
        experiment.status.value,
    )
    return experiment


async def delete_experiment(db: AsyncSession, *, experiment: Experiment) -> None:
    """
    删除实验（10-S1-9）

    约束：仅当所有版本均为 draft 或无版本时才允许删除。
    """
    # 检查是否有非 draft 版本
    result = await db.execute(
        select(ExperimentVersion).where(
            ExperimentVersion.experiment_id == experiment.id,
            ExperimentVersion.publish_status != PublishStatus.DRAFT,
        ).limit(1)
    )
    if result.scalar_one_or_none():
        raise ValueError("EXPERIMENT_HAS_NON_DRAFT_VERSIONS")

    await db.delete(experiment)
    await db.commit()


# ─── ExperimentVersion CRUD ────────────────────────────────────────────────────

async def create_version(
    db: AsyncSession,
    *,
    experiment_id: int,
    version_name: str,
    environment_key: str,
    image_name: str,
    launch_file_path: str,
    launch_args_template: dict,
    file_bundle_id: Optional[int],
    env_bundle_id: Optional[int] = None,
) -> ExperimentVersion:
    """
    为指定实验创建新版本（10-S1: 移除 is_visible/startup_script_ref，新增 env_bundle_id）
    """
    version = ExperimentVersion(
        experiment_id=experiment_id,
        version_name=version_name,
        environment_key=environment_key,
        image_name=image_name,
        launch_file_path=launch_file_path,
        launch_args_template=launch_args_template,
        file_bundle_id=file_bundle_id,
        env_bundle_id=env_bundle_id,
        publish_status=PublishStatus.DRAFT,
    )
    db.add(version)
    await db.commit()
    await db.refresh(version)
    return version


async def update_version(
    db: AsyncSession,
    *,
    version: ExperimentVersion,
    version_name: str,
    environment_key: str,
    image_name: str,
    launch_file_path: str,
    launch_args_template: dict,
    file_bundle_id: Optional[int],
    env_bundle_id: Optional[int] = None,
) -> ExperimentVersion:
    """
    更新实验版本配置（仅用于草稿版本）（10-S1: 移除 is_visible/startup_script_ref）
    """
    version.version_name = version_name
    version.environment_key = environment_key
    version.image_name = image_name
    version.launch_file_path = launch_file_path
    version.launch_args_template = launch_args_template
    version.file_bundle_id = file_bundle_id
    version.env_bundle_id = env_bundle_id
    version.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(version)
    return version


async def get_version(db: AsyncSession, version_id: int) -> Optional[ExperimentVersion]:
    """获取单个版本详情"""
    result = await db.execute(select(ExperimentVersion).where(ExperimentVersion.id == version_id))
    return result.scalar_one_or_none()


async def list_versions_by_experiment(db: AsyncSession, experiment_id: int) -> list[ExperimentVersion]:
    """获取指定实验下的所有版本"""
    result = await db.execute(
        select(ExperimentVersion)
        .where(ExperimentVersion.experiment_id == experiment_id)
        .order_by(ExperimentVersion.created_at.desc())
    )
    return list(result.scalars().all())


async def publish_version(
    db: AsyncSession,
    *,
    experiment_id: int,
    version: ExperimentVersion,
    operator_id: int,
    note: Optional[str],
) -> ExperimentPublishLog:
    """
    发布实验版本（draft → published）。将状态改为已发布，并记录发布日志。
    """
    version.publish_status = PublishStatus.PUBLISHED
    version.published_at = datetime.utcnow()
    version.updated_at = datetime.utcnow()

    log = ExperimentPublishLog(
        experiment_id=experiment_id,
        version_id=version.id,
        operator_id=operator_id,
        publish_note=note,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log


async def switch_version_publish_status(
    db: AsyncSession,
    *,
    version: ExperimentVersion,
    new_status: str,
    operator_id: int,
    publish_note: Optional[str] = None,
) -> ExperimentVersion:
    """
    切换版本发布状态（10-S1-10）

    状态机规则（SDD §5.5）：
        draft → published（需先 validate 无 blocking issue）
        published → deprecated
        deprecated → published
    """
    valid_transitions = {
        "draft": {"published"},
        "published": {"deprecated"},
        "deprecated": {"published"},
    }
    current = version.publish_status.value
    if new_status not in valid_transitions.get(current, set()):
        raise ValueError(f"INVALID_STATUS_TRANSITION: {current} → {new_status}")

    version.publish_status = PublishStatus(new_status)
    version.updated_at = datetime.utcnow()
    if new_status == "published":
        version.published_at = datetime.utcnow()
        # 同时创建发布日志
        log = ExperimentPublishLog(
            experiment_id=version.experiment_id,
            version_id=version.id,
            operator_id=operator_id,
            publish_note=publish_note,
        )
        db.add(log)

    await db.commit()
    await db.refresh(version)
    return version


async def delete_version(db: AsyncSession, *, version: ExperimentVersion) -> None:
    """
    删除版本（10-S1-10）

    约束：仅 draft 版本可删除。
    """
    if version.publish_status != PublishStatus.DRAFT:
        raise ValueError("VERSION_NOT_DRAFT")

    await db.delete(version)
    await db.commit()


async def validate_version(
    db: AsyncSession,
    *,
    version: ExperimentVersion,
) -> dict:
    """
    版本配置验证（10-S1-11）

    检查：镜像名、file_bundle、env_bundle、startup.sh 是否存在。
    返回：{valid: bool, issues: [{field, code, severity, message}]}

    issues 中 severity=blocking 的问题将阻止版本发布。
    """
    import os
    from pathlib import Path

    issues = []

    # 检查镜像名（简单非空校验；实际镜像是否存在由容器创建时 Docker 返回错误）
    if not version.image_name or not version.image_name.strip():
        issues.append({
            "field": "image_name",
            "code": "missing_image",
            "severity": "blocking",
            "message": "Docker 镜像名称不能为空",
        })

    # 检查 file_bundle
    if version.file_bundle_id:
        bundle = await get_bundle(db, version.file_bundle_id)
        if not bundle:
            issues.append({
                "field": "file_bundle_id",
                "code": "missing_bundle",
                "severity": "blocking",
                "message": f"文件包 ID={version.file_bundle_id} 不存在",
            })
        elif bundle.file_count == 0:
            issues.append({
                "field": "file_bundle_id",
                "code": "empty_bundle",
                "severity": "warning",
                "message": "文件包为空，请上传实验文件",
            })

    # 检查 env_bundle
    if version.env_bundle_id:
        env_bundle = await get_env_bundle(db, version.env_bundle_id)
        if not env_bundle:
            issues.append({
                "field": "env_bundle_id",
                "code": "missing_env_bundle",
                "severity": "blocking",
                "message": f"环境包 ID={version.env_bundle_id} 不存在",
            })
        else:
            # 检查 startup.sh 是否存在
            startup_path = Path(env_bundle.storage_root) / "startup.sh"
            if not startup_path.exists():
                issues.append({
                    "field": "env_bundle_id",
                    "code": "missing_startup_script",
                    "severity": "blocking",
                    "message": "环境包中 startup.sh 不存在，请修复环境包",
                })

    has_blocking = any(i["severity"] == "blocking" for i in issues)
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "has_blocking": has_blocking,
    }


async def list_publish_logs(db: AsyncSession, experiment_id: int) -> list[ExperimentPublishLog]:
    """获取实验的发布记录"""
    result = await db.execute(
        select(ExperimentPublishLog)
        .where(ExperimentPublishLog.experiment_id == experiment_id)
        .order_by(ExperimentPublishLog.created_at.desc())
    )
    return list(result.scalars().all())


# ─── ExperimentFileBundle CRUD（10-S1-2 重构）──────────────────────────────────

async def create_bundle(
    db: AsyncSession,
    *,
    name: str,
    storage_root: str,
    created_by: int,
) -> ExperimentFileBundle:
    """创建实验文件包记录（10-S1-2: 新增 name/storage_root，移除 experiment_id/checksum）"""
    bundle = ExperimentFileBundle(
        name=name,
        storage_root=storage_root,
        file_count=0,
        total_size_bytes=0,
        file_manifest=[],
        validate_status=FileBundleStatus.PENDING,
        created_by=created_by,
    )
    db.add(bundle)
    await db.commit()
    await db.refresh(bundle)
    return bundle


async def get_bundle(db: AsyncSession, bundle_id: int) -> Optional[ExperimentFileBundle]:
    """通过 ID 获取文件包"""
    result = await db.execute(select(ExperimentFileBundle).where(ExperimentFileBundle.id == bundle_id))
    return result.scalar_one_or_none()


async def list_bundles(
    db: AsyncSession,
    *,
    created_by: int,
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
) -> tuple[list[ExperimentFileBundle], int]:
    """分页查询文件包列表（当前教师创建的）"""
    query = select(ExperimentFileBundle).where(ExperimentFileBundle.created_by == created_by)
    count_query = select(func.count()).select_from(ExperimentFileBundle).where(
        ExperimentFileBundle.created_by == created_by
    )
    if keyword:
        like = f"%{keyword}%"
        query = query.where(ExperimentFileBundle.name.like(like))
        count_query = count_query.where(ExperimentFileBundle.name.like(like))

    total = (await db.execute(count_query)).scalar_one()
    rows = (
        await db.execute(
            query.order_by(ExperimentFileBundle.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return list(rows), int(total)


async def rename_bundle(
    db: AsyncSession,
    *,
    bundle: ExperimentFileBundle,
    new_name: str,
) -> tuple[ExperimentFileBundle, list[dict]]:
    """
    重命名文件包，返回受影响的版本列表。
    注意：重命名不改变 bundle_id，不影响外键引用，仅影响显示名称。
    """
    bundle.name = new_name
    bundle.updated_at = datetime.utcnow()

    # 查询引用该文件包的版本
    result = await db.execute(
        select(ExperimentVersion).where(ExperimentVersion.file_bundle_id == bundle.id)
    )
    affected_versions = result.scalars().all()
    affected = []
    for v in affected_versions:
        exp = await get_experiment(db, v.experiment_id)
        affected.append({
            "version_id": v.id,
            "experiment_name": exp.name if exp else "未知",
            "version_name": v.version_name,
        })

    await db.commit()
    await db.refresh(bundle)
    return bundle, affected


async def delete_bundle(db: AsyncSession, *, bundle: ExperimentFileBundle) -> None:
    """
    删除文件包（10-S1）

    约束：被版本引用时不可删除（返回 BUNDLE_IN_USE）。
    """
    result = await db.execute(
        select(ExperimentVersion).where(
            ExperimentVersion.file_bundle_id == bundle.id
        ).limit(1)
    )
    if result.scalar_one_or_none():
        raise ValueError("BUNDLE_IN_USE")

    await db.delete(bundle)
    await db.commit()


async def update_bundle_stats(
    db: AsyncSession,
    *,
    bundle: ExperimentFileBundle,
    file_count: int,
    total_size_bytes: int,
    file_manifest: list,
) -> ExperimentFileBundle:
    """上传文件后更新文件包统计信息并重建 manifest"""
    bundle.file_count = file_count
    bundle.total_size_bytes = total_size_bytes
    bundle.file_manifest = file_manifest
    bundle.validate_status = FileBundleStatus.VALID if file_count > 0 else FileBundleStatus.INVALID
    bundle.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(bundle)
    return bundle


# ─── ExperimentEnvBundle CRUD（10-S1-4 新增）──────────────────────────────────

async def create_env_bundle(
    db: AsyncSession,
    *,
    name: str,
    storage_root: str,
    container_target_dir: str,
    access_level: str,
    created_by: int,
) -> ExperimentEnvBundle:
    """创建环境文件包记录（10-S1-4）"""
    bundle = ExperimentEnvBundle(
        name=name,
        storage_root=storage_root,
        container_target_dir=container_target_dir,
        access_level=EnvBundleAccessLevel(access_level),
        file_count=0,
        total_size_bytes=0,
        created_by=created_by,
    )
    db.add(bundle)
    await db.commit()
    await db.refresh(bundle)
    return bundle


async def get_env_bundle(db: AsyncSession, env_bundle_id: int) -> Optional[ExperimentEnvBundle]:
    """通过 ID 获取环境包"""
    result = await db.execute(
        select(ExperimentEnvBundle).where(ExperimentEnvBundle.id == env_bundle_id)
    )
    return result.scalar_one_or_none()


async def list_env_bundles(
    db: AsyncSession,
    *,
    created_by: int,
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
) -> tuple[list[ExperimentEnvBundle], int]:
    """分页查询环境包列表（当前教师创建的）"""
    query = select(ExperimentEnvBundle).where(ExperimentEnvBundle.created_by == created_by)
    count_query = select(func.count()).select_from(ExperimentEnvBundle).where(
        ExperimentEnvBundle.created_by == created_by
    )
    if keyword:
        like = f"%{keyword}%"
        query = query.where(ExperimentEnvBundle.name.like(like))
        count_query = count_query.where(ExperimentEnvBundle.name.like(like))

    total = (await db.execute(count_query)).scalar_one()
    rows = (
        await db.execute(
            query.order_by(ExperimentEnvBundle.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return list(rows), int(total)


async def update_env_bundle(
    db: AsyncSession,
    *,
    env_bundle: ExperimentEnvBundle,
    name: Optional[str] = None,
    container_target_dir: Optional[str] = None,
    access_level: Optional[str] = None,
) -> ExperimentEnvBundle:
    """更新环境包基础设置"""
    if name is not None:
        env_bundle.name = name
    if container_target_dir is not None:
        env_bundle.container_target_dir = container_target_dir
    if access_level is not None:
        env_bundle.access_level = EnvBundleAccessLevel(access_level)
    env_bundle.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(env_bundle)
    return env_bundle


async def delete_env_bundle(db: AsyncSession, *, env_bundle: ExperimentEnvBundle) -> None:
    """
    删除环境包（10-S1）

    约束：被版本引用时不可删除（返回 BUNDLE_IN_USE）。
    """
    result = await db.execute(
        select(ExperimentVersion).where(
            ExperimentVersion.env_bundle_id == env_bundle.id
        ).limit(1)
    )
    if result.scalar_one_or_none():
        raise ValueError("BUNDLE_IN_USE")

    await db.delete(env_bundle)
    await db.commit()


async def update_env_bundle_stats(
    db: AsyncSession,
    *,
    env_bundle: ExperimentEnvBundle,
    file_count: int,
    total_size_bytes: int,
) -> ExperimentEnvBundle:
    """上传文件后更新环境包统计信息"""
    env_bundle.file_count = file_count
    env_bundle.total_size_bytes = total_size_bytes
    env_bundle.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(env_bundle)
    return env_bundle


# ─── 学生可见性查询（10-S1-12）────────────────────────────────────────────────

async def list_student_available_versions(db: AsyncSession) -> list[ExperimentVersion]:
    """
    列出学生可见的已发布实验版本（10-S1-12）

    可见性规则（替代原 is_visible 字段）：
        Experiment.status = 'active'
        AND ExperimentVersion.publish_status = 'published'
    """
    result = await db.execute(
        select(ExperimentVersion)
        .join(Experiment, ExperimentVersion.experiment_id == Experiment.id)
        .where(
            Experiment.status == ExperimentStatus.ACTIVE,
            ExperimentVersion.publish_status == PublishStatus.PUBLISHED,
        )
        .order_by(ExperimentVersion.published_at.desc(), ExperimentVersion.id.desc())
    )
    return list(result.scalars().all())
