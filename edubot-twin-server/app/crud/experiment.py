from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.experiment import (
    Experiment,
    ExperimentPublishLog,
    ExperimentStatus,
    ExperimentVersion,
    PublishStatus,
)


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
    :param db: 数据库会话
    :param name: 实验名称
    :param code: 实验唯一编码
    :param description: 实验描述
    :param created_by: 创建教师 ID
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
    """
    通过 ID 获取实验详情
    """
    result = await db.execute(select(Experiment).where(Experiment.id == experiment_id))
    return result.scalar_one_or_none()


async def get_experiment_by_code(db: AsyncSession, code: str) -> Optional[Experiment]:
    """
    通过编码获取实验详情
    """
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
    """
    分页查询实验列表
    :param keyword: 搜索关键词（名称或编码）
    :param status: 状态过滤
    """
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


async def create_version(
    db: AsyncSession,
    *,
    experiment_id: int,
    version_name: str,
    environment_key: str,
    image_name: str,
    launch_file_path: str,
    launch_args_template: dict,
    startup_script_ref: Optional[str],
    file_bundle_id: Optional[int],
    is_visible: bool,
) -> ExperimentVersion:
    """
    为指定实验创建新版本
    """
    version = ExperimentVersion(
        experiment_id=experiment_id,
        version_name=version_name,
        environment_key=environment_key,
        image_name=image_name,
        launch_file_path=launch_file_path,
        launch_args_template=launch_args_template,
        startup_script_ref=startup_script_ref,
        file_bundle_id=file_bundle_id,
        is_visible=is_visible,
        publish_status=PublishStatus.DRAFT,
    )
    db.add(version)
    await db.commit()
    await db.refresh(version)
    return version


async def get_version(db: AsyncSession, version_id: int) -> Optional[ExperimentVersion]:
    """
    获取单个版本详情
    """
    result = await db.execute(select(ExperimentVersion).where(ExperimentVersion.id == version_id))
    return result.scalar_one_or_none()


async def list_versions_by_experiment(db: AsyncSession, experiment_id: int) -> list[ExperimentVersion]:
    """
    获取指定实验下的所有版本
    """
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
    发布实验版本。将状态改为已发布，并记录发布日志。
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


async def list_publish_logs(db: AsyncSession, experiment_id: int) -> list[ExperimentPublishLog]:
    """
    获取实验的发布记录
    """
    result = await db.execute(
        select(ExperimentPublishLog)
        .where(ExperimentPublishLog.experiment_id == experiment_id)
        .order_by(ExperimentPublishLog.created_at.desc())
    )
    return list(result.scalars().all())


async def list_student_available_versions(db: AsyncSession) -> list[ExperimentVersion]:
    """
    列出学生可见的已发布实验版本（第10期核心：首页可选列表）
    """
    result = await db.execute(
        select(ExperimentVersion)
        .where(
            ExperimentVersion.is_visible == True,  # noqa: E712
            ExperimentVersion.publish_status == PublishStatus.PUBLISHED,
        )
        .order_by(ExperimentVersion.published_at.desc(), ExperimentVersion.id.desc())
    )
    return list(result.scalars().all())

