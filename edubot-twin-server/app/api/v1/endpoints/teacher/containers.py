"""
教师端容器管理 API

路由前缀：/api/v1/teachers/containers
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.schemas.container import (
    ContainerCreate, ContainerResponse,
    BatchOperationRequest, BatchOperationResponse, BatchOperationResult
)
from app.crud import container as crud_container
from app.core.port_allocator import PortExhaustedError
from app.core.security import get_current_teacher
from app.core.logger import log_container_event

router = APIRouter()


def _to_response(obj) -> ContainerResponse:
    """将 ORM 对象转为 ContainerResponse（触发 computed_field）"""
    return ContainerResponse.model_validate(obj)


@router.post(
    "/",
    response_model=ContainerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="为学生创建仿真容器",
)
async def create_container(
    data: ContainerCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    教师为指定学生创建仿真容器。

    - 自动分配 gzbridge / rosbridge 端口
    - Mock 模式：直接设置 status=RUNNING，不真实调用 Docker
    """
    try:
        container = await crud_container.create_container(db, data)
    except PortExhaustedError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
    return _to_response(container)


@router.get(
    "/",
    response_model=list[ContainerResponse],
    summary="列出所有容器",
)
async def list_containers(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """获取所有仿真容器列表（分页）"""
    containers = await crud_container.list_containers(db, skip=skip, limit=limit)
    return [_to_response(c) for c in containers]


@router.get(
    "/{container_id}",
    response_model=ContainerResponse,
    summary="获取容器详情",
)
async def get_container(
    container_id: int,
    db: AsyncSession = Depends(get_db),
):
    """根据 ID 获取容器详情"""
    container = await crud_container.get_container(db, container_id)
    if not container:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"容器 ID={container_id} 不存在",
        )
    return _to_response(container)


@router.post(
    "/{container_id}/start",
    response_model=ContainerResponse,
    summary="启动已停止的容器",
)
async def start_container(
    container_id: int,
    db: AsyncSession = Depends(get_db),
):
    """启动已停止的容器（Mock：直接修改状态为 RUNNING）"""
    container = await crud_container.get_container(db, container_id)
    if not container:
        raise HTTPException(status_code=404, detail=f"容器 ID={container_id} 不存在")

    from app.models.container import ContainerStatus
    if container.status == ContainerStatus.RUNNING:
        raise HTTPException(status_code=400, detail="容器已在运行中")

    container = await crud_container.start_container(db, container)
    return _to_response(container)


@router.post(
    "/{container_id}/stop",
    response_model=ContainerResponse,
    summary="停止运行中的容器",
)
async def stop_container(
    container_id: int,
    db: AsyncSession = Depends(get_db),
):
    """停止运行中的容器（Mock：直接修改状态为 STOPPED）"""
    container = await crud_container.get_container(db, container_id)
    if not container:
        raise HTTPException(status_code=404, detail=f"容器 ID={container_id} 不存在")

    from app.models.container import ContainerStatus
    if container.status != ContainerStatus.RUNNING:
        raise HTTPException(status_code=400, detail="容器未在运行中")

    container = await crud_container.stop_container(db, container)
    return _to_response(container)


@router.delete(
    "/{container_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除容器",
)
async def delete_container(
    container_id: int,
    db: AsyncSession = Depends(get_db),
):
    """删除容器记录（Mock：跳过真实 Docker 删除）"""
    container = await crud_container.get_container(db, container_id)
    if not container:
        raise HTTPException(status_code=404, detail=f"容器 ID={container_id} 不存在")

    await crud_container.delete_container(db, container)


@router.post(
    "/batch-start",
    response_model=BatchOperationResponse,
    summary="批量启动容器",
)
async def batch_start_containers(
    data: BatchOperationRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """批量启动容器（部分成功模式）"""
    results = []
    success_count = 0
    
    for container_id in data.container_ids:
        try:
            container = await crud_container.get_container(db, container_id)
            if not container:
                results.append(BatchOperationResult(
                    container_id=container_id,
                    success=False,
                    message="容器不存在"
                ))
                continue
            
            from app.models.container import ContainerStatus
            if container.status == ContainerStatus.RUNNING:
                results.append(BatchOperationResult(
                    container_id=container_id,
                    success=True,
                    message="容器已在运行中"
                ))
                success_count += 1
                continue
            
            await crud_container.start_container(db, container)
            results.append(BatchOperationResult(
                container_id=container_id,
                success=True,
                message="启动成功"
            ))
            success_count += 1
            log_container_event("batch_start", container_id, message="批量启动成功")
            
        except Exception as e:
            results.append(BatchOperationResult(
                container_id=container_id,
                success=False,
                message=str(e)
            ))
            log_container_event("batch_start", container_id, message=f"批量启动失败: {e}", level="ERROR")
    
    return BatchOperationResponse(
        total=len(data.container_ids),
        success_count=success_count,
        failed_count=len(data.container_ids) - success_count,
        results=results
    )


@router.post(
    "/batch-stop",
    response_model=BatchOperationResponse,
    summary="批量停止容器",
)
async def batch_stop_containers(
    data: BatchOperationRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """批量停止容器（部分成功模式）"""
    results = []
    success_count = 0
    
    for container_id in data.container_ids:
        try:
            container = await crud_container.get_container(db, container_id)
            if not container:
                results.append(BatchOperationResult(
                    container_id=container_id,
                    success=False,
                    message="容器不存在"
                ))
                continue
            
            from app.models.container import ContainerStatus
            if container.status != ContainerStatus.RUNNING:
                results.append(BatchOperationResult(
                    container_id=container_id,
                    success=True,
                    message="容器未在运行中"
                ))
                success_count += 1
                continue
            
            await crud_container.stop_container(db, container)
            results.append(BatchOperationResult(
                container_id=container_id,
                success=True,
                message="停止成功"
            ))
            success_count += 1
            log_container_event("batch_stop", container_id, message="批量停止成功")
            
        except Exception as e:
            results.append(BatchOperationResult(
                container_id=container_id,
                success=False,
                message=str(e)
            ))
            log_container_event("batch_stop", container_id, message=f"批量停止失败: {e}", level="ERROR")
    
    return BatchOperationResponse(
        total=len(data.container_ids),
        success_count=success_count,
        failed_count=len(data.container_ids) - success_count,
        results=results
    )


@router.post(
    "/batch-delete",
    response_model=BatchOperationResponse,
    summary="批量删除容器",
)
async def batch_delete_containers(
    data: BatchOperationRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher),
):
    """批量删除容器（部分成功模式）"""
    results = []
    success_count = 0
    
    for container_id in data.container_ids:
        try:
            container = await crud_container.get_container(db, container_id)
            if not container:
                results.append(BatchOperationResult(
                    container_id=container_id,
                    success=False,
                    message="容器不存在"
                ))
                continue
            
            await crud_container.delete_container(db, container)
            results.append(BatchOperationResult(
                container_id=container_id,
                success=True,
                message="删除成功"
            ))
            success_count += 1
            log_container_event("batch_delete", container_id, message="批量删除成功")
            
        except Exception as e:
            results.append(BatchOperationResult(
                container_id=container_id,
                success=False,
                message=str(e)
            ))
            log_container_event("batch_delete", container_id, message=f"批量删除失败: {e}", level="ERROR")
    
    return BatchOperationResponse(
        total=len(data.container_ids),
        success_count=success_count,
        failed_count=len(data.container_ids) - success_count,
        results=results
    )
