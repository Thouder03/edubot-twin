"""
教师端 - 学生管理 API
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.core.security import get_current_teacher
from app.schemas.common import ApiResponse
from app.schemas.student import (
    StudentCreate, StudentUpdate, StudentResponse, StudentListResponse
)
from app.crud import student as student_crud
from app.crud import container as container_crud
from app.core.docker_client import get_docker_client

router = APIRouter()


@router.get(
    "",
    response_model=ApiResponse[StudentListResponse],
    summary="获取学生列表"
)
async def list_students(
    pageIndex: int = Query(default=1, ge=1, description="页码"),
    pageSize: int = Query(default=20, ge=1, le=200, description="每页数量"),
    keyword: Optional[str] = Query(default=None, description="搜索关键词（用户名或姓名）"),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_teacher)
):
    """教师查看所有学生（支持分页和关键词搜索）"""
    skip = (pageIndex - 1) * pageSize
    students, total = await student_crud.get_students(
        db, skip=skip, limit=pageSize, keyword=keyword
    )
    return ApiResponse(data=StudentListResponse(total=total, list=students))


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
    """删除学生（级联删除容器记录，容错清理 Docker）"""
    student = await student_crud.get_student(db, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")
    
    containers = await container_crud.get_containers_by_student(db, student_id)
    docker_errors = []
    
    # 容错清理 Docker 容器
    try:
        docker_client = get_docker_client()
        for container in containers:
            if container.container_id:
                try:
                    docker_container = docker_client.containers.get(container.container_id)
                    docker_container.remove(force=True)
                except Exception as e:
                    docker_errors.append(f"容器 {container.container_id}: {str(e)}")
    except Exception as e:
        docker_errors.append(f"Docker 连接失败: {str(e)}")
    
    # 数据库删除（级联删除容器记录）
    await student_crud.delete_student(db, student_id)
    
    result = {
        "deleted": True,
        "student_id": student_id,
        "containers_deleted": len(containers)
    }
    if docker_errors:
        result["docker_warnings"] = docker_errors
    
    return ApiResponse(data=result)
