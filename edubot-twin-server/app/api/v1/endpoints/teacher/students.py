"""
教师端 - 学生管理 API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.core.security import get_current_teacher
from app.core.logger import log_container_event
from app.schemas.common import ApiResponse
from app.schemas.student import StudentCreate, StudentUpdate, StudentResponse
from app.crud import student as student_crud
from app.crud import container as container_crud
from app.core.docker_client import get_docker_client

router = APIRouter()


@router.get(
    "",
    response_model=ApiResponse[list[StudentResponse]],
    summary="获取学生列表"
)
async def list_students(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_teacher)
):
    """教师查看所有学生"""
    students = await student_crud.get_students(db, skip=skip, limit=limit)
    return ApiResponse(data=students)


@router.get(
    "/{student_id}",
    response_model=ApiResponse[StudentResponse],
    summary="获取学生详情"
)
async def get_student(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_teacher)
):
    """获取单个学生信息"""
    student = await student_crud.get_student(db, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")
    return ApiResponse(data=student)


@router.post(
    "",
    response_model=ApiResponse[StudentResponse],
    summary="创建学生"
)
async def create_student(
    student_in: StudentCreate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_teacher)
):
    """创建新学生"""
    existing = await student_crud.get_student_by_username(db, student_in.username)
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")
    
    student = await student_crud.create_student(db, student_in)
    return ApiResponse(data=student)


@router.put(
    "/{student_id}",
    response_model=ApiResponse[StudentResponse],
    summary="更新学生信息"
)
async def update_student(
    student_id: int,
    student_in: StudentUpdate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_teacher)
):
    """更新学生信息"""
    student = await student_crud.get_student(db, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")
    
    if student_in.username and student_in.username != student.username:
        existing = await student_crud.get_student_by_username(db, student_in.username)
        if existing:
            raise HTTPException(status_code=400, detail="用户名已存在")
    
    updated = await student_crud.update_student(db, student_id, student_in)
    return ApiResponse(data=updated)


@router.delete(
    "/{student_id}",
    response_model=ApiResponse[dict],
    summary="删除学生"
)
async def delete_student(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_teacher)
):
    """
    删除学生（带事务和容错）
    - 数据库是单一事实来源
    - Docker 失败时容错继续
    """
    student = await student_crud.get_student(db, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")
    
    # 获取学生的所有容器
    containers = await container_crud.get_containers_by_student(db, student_id)
    
    docker_errors = []
    docker_client = get_docker_client()
    
    # 尝试删除 Docker 容器（容错模式）
    for container in containers:
        if container.container_id:
            try:
                docker_container = docker_client.containers.get(container.container_id)
                docker_container.remove(force=True)
                log_container_event(
                    "container_deleted",
                    container_id=container.id,
                    student_id=student_id,
                    docker_container_id=container.container_id
                )
            except Exception as e:
                # Docker 失败不阻塞删除，记录错误
                error_msg = f"容器 {container.container_id} Docker删除失败: {str(e)}"
                docker_errors.append(error_msg)
                log_container_event(
                    "container_delete_failed",
                    container_id=container.id,
                    student_id=student_id,
                    error=str(e)
                )
    
    # 数据库删除（事务保证）
    try:
        await student_crud.delete_student(db, student_id)
        await db.commit()
        
        log_container_event(
            "student_deleted",
            student_id=student_id,
            username=student.username,
            containers_count=len(containers)
        )
        
        result = {
            "deleted": True,
            "student_id": student_id,
            "containers_deleted": len(containers)
        }
        
        if docker_errors:
            result["docker_warnings"] = docker_errors
        
        return ApiResponse(data=result)
        
    except Exception as e:
        await db.rollback()
        log_container_event(
            "student_delete_failed",
            student_id=student_id,
            error=str(e)
        )
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")
