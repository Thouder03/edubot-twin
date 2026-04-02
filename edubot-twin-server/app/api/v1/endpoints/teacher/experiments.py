from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_teacher
from app.crud import experiment as crud_experiment
from app.db.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.experiment import (
    ExperimentCreate,
    ExperimentDetailResponse,
    ExperimentListItem,
    ExperimentListResponse,
    ExperimentPublishLogItem,
    ExperimentPublishLogListResponse,
    ExperimentPublishRequest,
    ExperimentPublishResponse,
    ExperimentResponse,
    ExperimentVersionCreate,
    ExperimentVersionResponse,
)

router = APIRouter()


def _to_experiment_response(obj) -> ExperimentResponse:
    return ExperimentResponse(
        experiment_id=obj.id,
        name=obj.name,
        code=obj.code,
        description=obj.description,
        status=obj.status.value,
        created_by=obj.created_by,
        created_at=obj.created_at,
        updated_at=obj.updated_at,
    )


def _to_version_response(obj) -> ExperimentVersionResponse:
    return ExperimentVersionResponse(
        version_id=obj.id,
        experiment_id=obj.experiment_id,
        version_name=obj.version_name,
        is_visible=obj.is_visible,
        environment_key=obj.environment_key,
        image_name=obj.image_name,
        launch_file_path=obj.launch_file_path,
        launch_args_template=obj.launch_args_template,
        startup_script_ref=obj.startup_script_ref,
        file_bundle_id=obj.file_bundle_id,
        publish_status=obj.publish_status.value,
        published_at=obj.published_at,
        created_at=obj.created_at,
        updated_at=obj.updated_at,
    )


def _to_publish_log_item(obj) -> ExperimentPublishLogItem:
    return ExperimentPublishLogItem(
        publish_id=obj.id,
        experiment_id=obj.experiment_id,
        version_id=obj.version_id,
        operator=obj.operator_id,
        note=obj.publish_note,
        created_at=obj.created_at,
    )


@router.get("", response_model=ApiResponse[ExperimentListResponse], summary="实验列表")
async def list_experiments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = Query(default=None, description="按名称或编码搜索"),
    status_filter: Optional[str] = Query(default=None, alias="status", description="按状态过滤"),
    db: AsyncSession = Depends(get_db),
    _: int = Depends(get_current_teacher),
):
    """
    分页查询所有实验列表（第10期：教师管理首页）
    """
    experiments, total = await crud_experiment.list_experiments(
        db,
        page=page,
        page_size=page_size,
        keyword=keyword,
        status=status_filter,
    )

    items: list[ExperimentListItem] = []
    for exp in experiments:
        versions = await crud_experiment.list_versions_by_experiment(db, exp.id)
        latest = versions[0] if versions else None
        items.append(
            ExperimentListItem(
                experiment_id=exp.id,
                name=exp.name,
                code=exp.code,
                status=exp.status.value,
                latest_version=latest.version_name if latest else None,
                published_at=latest.published_at if latest else None,
            )
        )

    return ApiResponse(data=ExperimentListResponse(total=total, list=items))


@router.post(
    "",
    response_model=ApiResponse[ExperimentResponse],
    status_code=status.HTTP_201_CREATED,
    summary="创建实验",
)
async def create_experiment(
    data: ExperimentCreate,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """
    创建实验主记录（初始状态为 draft）
    """
    existing = await crud_experiment.get_experiment_by_code(db, data.code)
    if existing:
        raise HTTPException(status_code=409, detail="实验编码已存在")

    exp = await crud_experiment.create_experiment(
        db,
        name=data.name,
        code=data.code,
        description=data.description,
        created_by=teacher_id,
    )
    return ApiResponse(data=_to_experiment_response(exp))


@router.get("/{experiment_id}", response_model=ApiResponse[ExperimentDetailResponse], summary="实验详情")
async def get_experiment_detail(
    experiment_id: int,
    db: AsyncSession = Depends(get_db),
    _: int = Depends(get_current_teacher),
):
    """
    查询实验详情，包括其下所有版本和历史发布记录
    """
    exp = await crud_experiment.get_experiment(db, experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="实验不存在")

    versions = await crud_experiment.list_versions_by_experiment(db, experiment_id)
    logs = await crud_experiment.list_publish_logs(db, experiment_id)

    return ApiResponse(
        data=ExperimentDetailResponse(
            base_info=_to_experiment_response(exp),
            versions=[_to_version_response(v) for v in versions],
            publish_logs=[_to_publish_log_item(log) for log in logs],
        )
    )


@router.post(
    "/{experiment_id}/versions",
    response_model=ApiResponse[ExperimentVersionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="创建实验版本",
)
async def create_version(
    experiment_id: int,
    data: ExperimentVersionCreate,
    db: AsyncSession = Depends(get_db),
    _: int = Depends(get_current_teacher),
):
    """
    为指定实验添加新版本（如 v1.0, v2.0）
    """
    exp = await crud_experiment.get_experiment(db, experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="实验不存在")

    version = await crud_experiment.create_version(
        db,
        experiment_id=experiment_id,
        version_name=data.version_name,
        environment_key=data.environment_key,
        image_name=data.image_name,
        launch_file_path=data.launch_file_path,
        launch_args_template=data.launch_args_template,
        startup_script_ref=data.startup_script_ref,
        file_bundle_id=data.file_bundle_id,
        is_visible=data.is_visible,
    )
    return ApiResponse(data=_to_version_response(version))


@router.post(
    "/{experiment_id}/versions/{version_id}/publish",
    response_model=ApiResponse[ExperimentPublishResponse],
    summary="发布实验版本",
)
async def publish_version(
    experiment_id: int,
    version_id: int,
    data: ExperimentPublishRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """
    发布实验版本。只有发布后，学生才在首页可见并可加载该环境。
    """
    exp = await crud_experiment.get_experiment(db, experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="实验不存在")

    version = await crud_experiment.get_version(db, version_id)
    if not version or version.experiment_id != experiment_id:
        raise HTTPException(status_code=404, detail="实验版本不存在")

    if version.publish_status.value != "draft":
        raise HTTPException(status_code=409, detail="仅草稿版本允许发布")

    log = await crud_experiment.publish_version(
        db,
        experiment_id=experiment_id,
        version=version,
        operator_id=teacher_id,
        note=data.publish_note,
    )

    return ApiResponse(
        data=ExperimentPublishResponse(
            publish_id=log.id,
            published_at=log.created_at,
            operator=teacher_id,
        )
    )


@router.get(
    "/{experiment_id}/publish-logs",
    response_model=ApiResponse[ExperimentPublishLogListResponse],
    summary="发布记录",
)
async def publish_logs(
    experiment_id: int,
    db: AsyncSession = Depends(get_db),
    _: int = Depends(get_current_teacher),
):
    """
    获取指定实验的历史发布日志
    """
    exp = await crud_experiment.get_experiment(db, experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="实验不存在")

    logs = await crud_experiment.list_publish_logs(db, experiment_id)
    items = [_to_publish_log_item(log) for log in logs]
    return ApiResponse(data=ExperimentPublishLogListResponse(total=len(items), list=items))

