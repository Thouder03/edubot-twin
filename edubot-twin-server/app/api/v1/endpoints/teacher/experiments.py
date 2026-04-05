"""
教师端实验管理 API（10-S1 增强）

新增端点（10-S1-9/10/11）：
- DELETE /experiments/{id}：删除实验（无非 draft 版本时）
- PATCH /experiments/{id}/status：切换实验状态
- DELETE /experiments/{eid}/versions/{vid}：删除版本（仅 draft）
- PATCH /experiments/{eid}/versions/{vid}/publish-status：版本状态切换
- POST /experiments/{eid}/versions/{vid}/validate：版本配置验证
"""
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
    ExperimentStatusSwitchRequest,
    ExperimentVersionCreate,
    ExperimentVersionPublishStatusRequest,
    ExperimentVersionResponse,
    ExperimentVersionUpdate,
    VersionValidateIssue,
    VersionValidateResponse,
)

router = APIRouter()


# ─── 响应体转换辅助函数 ────────────────────────────────────────────────────────

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
    """（10-S1: 移除 is_visible/startup_script_ref，新增 env_bundle_id）"""
    return ExperimentVersionResponse(
        version_id=obj.id,
        experiment_id=obj.experiment_id,
        version_name=obj.version_name,
        environment_key=obj.environment_key,
        image_name=obj.image_name,
        launch_file_path=obj.launch_file_path,
        launch_args_template=obj.launch_args_template,
        file_bundle_id=obj.file_bundle_id,
        env_bundle_id=obj.env_bundle_id,
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


# ─── 实验 CRUD ─────────────────────────────────────────────────────────────────

@router.get("", response_model=ApiResponse[ExperimentListResponse], summary="实验列表")
async def list_experiments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = Query(default=None, description="按名称或编码搜索"),
    status_filter: Optional[str] = Query(default=None, alias="status", description="按状态过滤"),
    db: AsyncSession = Depends(get_db),
    _: int = Depends(get_current_teacher),
):
    """分页查询所有实验列表"""
    experiments, total = await crud_experiment.list_experiments(
        db, page=page, page_size=page_size, keyword=keyword, status=status_filter,
    )
    items: list[ExperimentListItem] = []
    for exp in experiments:
        versions = await crud_experiment.list_versions_by_experiment(db, exp.id)
        latest = versions[0] if versions else None
        items.append(ExperimentListItem(
            experiment_id=exp.id,
            name=exp.name,
            code=exp.code,
            status=exp.status.value,
            latest_version=latest.version_name if latest else None,
            published_at=latest.published_at if latest else None,
        ))
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
    """创建实验主记录（初始状态为 draft）"""
    existing = await crud_experiment.get_experiment_by_code(db, data.code)
    if existing:
        raise HTTPException(status_code=409, detail="实验编码已存在")
    exp = await crud_experiment.create_experiment(
        db, name=data.name, code=data.code, description=data.description, created_by=teacher_id,
    )
    return ApiResponse(data=_to_experiment_response(exp))


@router.get("/{experiment_id}", response_model=ApiResponse[ExperimentDetailResponse], summary="实验详情")
async def get_experiment_detail(
    experiment_id: int,
    db: AsyncSession = Depends(get_db),
    _: int = Depends(get_current_teacher),
):
    """查询实验详情，包括其下所有版本和历史发布记录"""
    exp = await crud_experiment.get_experiment(db, experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="实验不存在")
    versions = await crud_experiment.list_versions_by_experiment(db, experiment_id)
    logs = await crud_experiment.list_publish_logs(db, experiment_id)
    return ApiResponse(data=ExperimentDetailResponse(
        base_info=_to_experiment_response(exp),
        versions=[_to_version_response(v) for v in versions],
        publish_logs=[_to_publish_log_item(log) for log in logs],
    ))


@router.delete(
    "/{experiment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除实验（10-S1-9）",
)
async def delete_experiment(
    experiment_id: int,
    db: AsyncSession = Depends(get_db),
    _: int = Depends(get_current_teacher),
):
    """
    删除实验（10-S1-9）。
    约束：仅当所有版本均为 draft 或无版本时才允许删除。
    含非 draft 版本时返回 409 EXPERIMENT_HAS_NON_DRAFT_VERSIONS。
    """
    exp = await crud_experiment.get_experiment(db, experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="实验不存在")
    try:
        await crud_experiment.delete_experiment(db, experiment=exp)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.patch(
    "/{experiment_id}/status",
    response_model=ApiResponse[dict],
    summary="切换实验状态（10-S1-9）",
)
async def switch_experiment_status(
    experiment_id: int,
    data: ExperimentStatusSwitchRequest,
    db: AsyncSession = Depends(get_db),
    _: int = Depends(get_current_teacher),
):
    """
    切换实验状态（10-S1-9）。
    状态机：draft ↔ active → archived → active；draft 可删除。
    非法转换返回 400 INVALID_STATUS_TRANSITION。
    """
    exp = await crud_experiment.get_experiment(db, experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="实验不存在")
    try:
        updated = await crud_experiment.switch_experiment_status(
            db, experiment=exp, new_status=data.status
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ApiResponse(data={
        "experiment_id": updated.id,
        "status": updated.status.value,
        "updated_at": updated.updated_at.isoformat(),
    })


# ─── 版本 CRUD ─────────────────────────────────────────────────────────────────

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
    """为指定实验添加新版本（10-S1: 移除 is_visible/startup_script_ref，新增 env_bundle_id）"""
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
        file_bundle_id=data.file_bundle_id,
        env_bundle_id=data.env_bundle_id,
    )
    return ApiResponse(data=_to_version_response(version))


@router.put(
    "/{experiment_id}/versions/{version_id}",
    response_model=ApiResponse[ExperimentVersionResponse],
    summary="更新实验版本",
)
async def update_version(
    experiment_id: int,
    version_id: int,
    data: ExperimentVersionUpdate,
    db: AsyncSession = Depends(get_db),
    _: int = Depends(get_current_teacher),
):
    """更新实验版本配置（仅草稿版本允许编辑）"""
    exp = await crud_experiment.get_experiment(db, experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="实验不存在")
    version = await crud_experiment.get_version(db, version_id)
    if not version or version.experiment_id != experiment_id:
        raise HTTPException(status_code=404, detail="实验版本不存在")
    if version.publish_status.value != "draft":
        raise HTTPException(status_code=409, detail="仅草稿版本允许编辑")
    updated = await crud_experiment.update_version(
        db,
        version=version,
        version_name=data.version_name,
        environment_key=data.environment_key,
        image_name=data.image_name,
        launch_file_path=data.launch_file_path,
        launch_args_template=data.launch_args_template,
        file_bundle_id=data.file_bundle_id,
        env_bundle_id=data.env_bundle_id,
    )
    return ApiResponse(data=_to_version_response(updated))


@router.delete(
    "/{experiment_id}/versions/{version_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除版本（10-S1-10，仅 draft）",
)
async def delete_version(
    experiment_id: int,
    version_id: int,
    db: AsyncSession = Depends(get_db),
    _: int = Depends(get_current_teacher),
):
    """删除版本（10-S1-10）。仅 draft 版本可删除，否则返回 409 VERSION_NOT_DRAFT。"""
    version = await crud_experiment.get_version(db, version_id)
    if not version or version.experiment_id != experiment_id:
        raise HTTPException(status_code=404, detail="实验版本不存在")
    try:
        await crud_experiment.delete_version(db, version=version)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.patch(
    "/{experiment_id}/versions/{version_id}/publish-status",
    response_model=ApiResponse[dict],
    summary="切换版本发布状态（10-S1-10）",
)
async def switch_version_publish_status(
    experiment_id: int,
    version_id: int,
    data: ExperimentVersionPublishStatusRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """
    切换版本发布状态（10-S1-10）。
    目标 published 时必须先通过 validate 无 blocking 问题，
    否则返回 409 VALIDATION_BLOCKING_ISSUE。
    """
    version = await crud_experiment.get_version(db, version_id)
    if not version or version.experiment_id != experiment_id:
        raise HTTPException(status_code=404, detail="实验版本不存在")

    # 发布前强制校验（10-S1-11 约束：发布必须复用 validate blocking 逻辑）
    if data.publish_status == "published":
        validate_result = await crud_experiment.validate_version(db, version=version)
        if validate_result["has_blocking"]:
            raise HTTPException(
                status_code=409,
                detail="VALIDATION_BLOCKING_ISSUE",
            )

    try:
        updated = await crud_experiment.switch_version_publish_status(
            db,
            version=version,
            new_status=data.publish_status,
            operator_id=teacher_id,
            publish_note=data.publish_note,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ApiResponse(data={
        "version_id": updated.id,
        "publish_status": updated.publish_status.value,
        "updated_at": updated.updated_at.isoformat(),
    })


@router.post(
    "/{experiment_id}/versions/{version_id}/validate",
    response_model=ApiResponse[VersionValidateResponse],
    summary="版本配置验证（10-S1-11）",
)
async def validate_version(
    experiment_id: int,
    version_id: int,
    db: AsyncSession = Depends(get_db),
    _: int = Depends(get_current_teacher),
):
    """
    验证版本配置完整性（10-S1-11）。
    检查：镜像名、file_bundle、env_bundle、startup.sh 是否存在。
    存在 severity=blocking 的问题将阻止版本发布。
    """
    version = await crud_experiment.get_version(db, version_id)
    if not version or version.experiment_id != experiment_id:
        raise HTTPException(status_code=404, detail="实验版本不存在")

    result = await crud_experiment.validate_version(db, version=version)
    return ApiResponse(data=VersionValidateResponse(
        valid=result["valid"],
        has_blocking=result["has_blocking"],
        issues=[VersionValidateIssue(**i) for i in result["issues"]],
    ))


# ─── 兼容旧的发布端点（保留向后兼容）─────────────────────────────────────────────

@router.post(
    "/{experiment_id}/versions/{version_id}/publish",
    response_model=ApiResponse[ExperimentPublishResponse],
    summary="发布实验版本（兼容旧端点）",
)
async def publish_version(
    experiment_id: int,
    version_id: int,
    data: ExperimentPublishRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """
    发布实验版本（保留向后兼容）。
    内部复用 switch_version_publish_status 逻辑，含 blocking 校验。
    """
    exp = await crud_experiment.get_experiment(db, experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="实验不存在")
    version = await crud_experiment.get_version(db, version_id)
    if not version or version.experiment_id != experiment_id:
        raise HTTPException(status_code=404, detail="实验版本不存在")
    if version.publish_status.value != "draft":
        raise HTTPException(status_code=409, detail="仅草稿版本允许发布")

    # 发布前 blocking 校验
    validate_result = await crud_experiment.validate_version(db, version=version)
    if validate_result["has_blocking"]:
        raise HTTPException(status_code=409, detail="VALIDATION_BLOCKING_ISSUE")

    log = await crud_experiment.publish_version(
        db, experiment_id=experiment_id, version=version,
        operator_id=teacher_id, note=data.publish_note,
    )
    return ApiResponse(data=ExperimentPublishResponse(
        publish_id=log.id,
        published_at=log.created_at,
        operator=teacher_id,
    ))


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
    """获取指定实验的历史发布日志"""
    exp = await crud_experiment.get_experiment(db, experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="实验不存在")
    logs = await crud_experiment.list_publish_logs(db, experiment_id)
    items = [_to_publish_log_item(log) for log in logs]
    return ApiResponse(data=ExperimentPublishLogListResponse(total=len(items), list=items))
