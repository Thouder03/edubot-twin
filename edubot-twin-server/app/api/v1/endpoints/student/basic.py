from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from app.db.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.student import StudentCreate, StudentUpdate, StudentResponse
from app.crud import student as crud_student
from typing import List

router = APIRouter()


@router.get("/", response_model=ApiResponse[List[StudentResponse]], summary="获取学生列表")
async def get_students(
    skip: int = Query(0, ge=0, description="跳过的记录数"),
    limit: int = Query(100, ge=1, le=500, description="返回的最大记录数"),
    db: AsyncSession = Depends(get_db)
):
    """
    获取学生列表,支持分页
    
    - **skip**: 跳过的记录数(用于分页)
    - **limit**: 返回的最大记录数
    """
    students = await crud_student.get_students(db, skip=skip, limit=limit)
    return ApiResponse(code=0, data=students)


@router.get("/{student_id}", response_model=ApiResponse[StudentResponse], summary="获取单个学生")
async def get_student(
    student_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    根据 ID 获取学生信息
    
    - **student_id**: 学生 ID
    """
    student = await crud_student.get_student_by_id(db, student_id)
    if not student:
        return JSONResponse(
            status_code=200,
            content={"code": 404, "message": f"学生 ID {student_id} 不存在", "data": None}
        )
    return ApiResponse(code=0, data=student)


@router.post("/", response_model=ApiResponse[StudentResponse], summary="创建学生")
async def create_student(
    student_data: StudentCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    创建新学生
    
    - **username**: 学号/用户名(唯一)
    - **password**: 明文密码(将自动哈希)
    - **real_name**: 真实姓名(可选)
    - **email**: 邮箱(可选,唯一)
    """
    # 检查用户名是否已存在
    existing_student = await crud_student.get_student_by_username(db, student_data.username)
    if existing_student:
        return JSONResponse(
            status_code=200,
            content={"code": 400, "message": "用户名已被注册", "data": None}
        )
    
    try:
        student = await crud_student.create_student(db, student_data)
        return ApiResponse(code=0, data=student)
    except IntegrityError:
        return JSONResponse(
            status_code=200,
            content={"code": 400, "message": "邮箱已被注册", "data": None}
        )


@router.put("/{student_id}", response_model=ApiResponse[StudentResponse], summary="更新学生信息")
async def update_student(
    student_id: int,
    student_data: StudentUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    更新学生信息
    
    - **student_id**: 学生 ID
    - 所有字段均为可选
    """
    student = await crud_student.update_student(db, student_id, student_data)
    if not student:
        return JSONResponse(
            status_code=200,
            content={"code": 404, "message": f"学生 ID {student_id} 不存在", "data": None}
        )
    return ApiResponse(code=0, data=student)


@router.delete("/{student_id}", response_model=ApiResponse[None], summary="删除学生")
async def delete_student(
    student_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    删除学生
    
    - **student_id**: 学生 ID
    """
    success = await crud_student.delete_student(db, student_id)
    if not success:
        return JSONResponse(
            status_code=200,
            content={"code": 404, "message": f"学生 ID {student_id} 不存在", "data": None}
        )
    return ApiResponse(code=0, message="学生删除成功", data=None)
