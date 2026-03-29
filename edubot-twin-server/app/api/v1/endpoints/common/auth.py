"""
统一认证 API 端点

支持学生和教师使用同一个接口登录,自动识别角色
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.auth import LoginRequest, LoginData, TokenData
from app.schemas.student import StudentResponse
from app.crud import student as crud_student
from app.core.security import create_access_token, verify_token
# from app.crud import teacher as crud_teacher  # 未来添加
import bcrypt

router = APIRouter()


@router.post("/login", response_model=ApiResponse[LoginData], summary="统一登录")
async def unified_login(
    login_data: LoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    统一登录端点 (学生和教师)
    
    - **username**: 用户名
    - **password**: 明文密码
    
    自动识别用户角色并返回对应信息
    """
    # 统一错误响应
    error_response = ApiResponse(code=500, message="用户名或密码错误", data=None)

    # 1. 先在学生表中查找
    student = await crud_student.get_student_by_username(db, login_data.username)
    if student:
        # 验证密码
        password_bytes = login_data.password.encode('utf-8')
        stored_hash = student.password_hash.encode('utf-8')
        if not bcrypt.checkpw(password_bytes, stored_hash):
            return error_response
        
        # 检查账号状态
        if not student.is_active:
            return ApiResponse(code=403, message="账号已被禁用", data=None)
        
        # 根据用户名判断角色
        if student.username == "admin":
            role = "admin"
            roleId = "1"
        elif student.username == "teacher":
            role = "teacher"
            roleId = "2"
        else:
            role = "student"
            roleId = "3"
        
        # 返回角色信息
        return ApiResponse(
            code=0,
            data=LoginData(
                username=student.username,
                role=role,
                roleId=roleId
            )
        )
    
    # ...

    # 3. 用户不存在
    return error_response


@router.post("/token", response_model=ApiResponse[TokenData], summary="获取 JWT Token")
async def get_token(
    login_data: LoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    获取 JWT Token (统一接口)
    
    自动识别用户角色并生成对应 Token
    """
    # 统一错误响应
    error_response = ApiResponse(code=500, message="用户名或密码错误", data=None)

    # 1. 学生表查找
    student = await crud_student.get_student_by_username(db, login_data.username)
    if student:
        password_bytes = login_data.password.encode('utf-8')
        stored_hash = student.password_hash.encode('utf-8')
        if not bcrypt.checkpw(password_bytes, stored_hash):
            return error_response
        
        if not student.is_active:
            return ApiResponse(code=403, message="账号已被禁用", data=None)
        
        # 根据用户名判断角色
        if student.username == "admin":
            role = "admin"
        elif student.username == "teacher":
            role = "teacher"
        else:
            role = "student"
        
        # 生成 Token
        token_data = {
            "sub": student.username,
            "user_id": student.id,
            "role": role
        }
        access_token = create_access_token(token_data)
        return ApiResponse(
            code=0,
            data=TokenData(access_token=access_token, token_type="Bearer")
        )
    
    # 2. 教师表查找 (未来实现)
    # ...
    
    return error_response


@router.get("/me", response_model=ApiResponse[StudentResponse], summary="获取当前用户")
async def get_current_user(
    token: str,
    db: AsyncSession = Depends(get_db)
):
    """
    获取当前登录用户信息 (统一接口)
    
    - **token**: JWT Token (查询参数)
    """
    auth_error = ApiResponse(code=401, message="Token 无效或已过期", data=None)

    # 验证 Token
    payload = verify_token(token)
    if not payload:
        return auth_error
    
    username = payload.get("sub")
    role = payload.get("role")
    
    if not username or not role:
        return ApiResponse(code=401, message="Token 数据无效", data=None)
    
    # 根据角色查询对应表
    if role == "student":
        student = await crud_student.get_student_by_username(db, username)
        if not student:
            return ApiResponse(code=404, message="用户不存在", data=None)
        return ApiResponse(code=0, data=student)
    
    # 教师逻辑 (未来实现)
    # ...
    
    return ApiResponse(code=400, message="未知的用户角色", data=None)


@router.get("/routes", response_model=ApiResponse[list[str]], summary="获取用户路由权限")
async def get_user_routes(role: str):
    """
    根据用户角色返回可访问的路径列表（前端动态路由）
    
    - **role**: 用户角色 (student/teacher/admin)
    
    返回格式: { "code": 0, "data": ["/path1", "/path2", ...] }
    """
    # 定义角色路由映射
    role_routes = {
        "student": [
            "/student",
            "/student/home",
            "/student/files",
            "/student/editor"
        ],
        "teacher": [
            "/teacher",
            "/teacher/home",
            "/teacher/students",
            "/teacher/containers",
            "/teacher/containers/monitor"
        ],
        "admin": [
            "/dashboard",
            "/dashboard/analysis",
            "/dashboard/workplace",
            "/external-link",
            "https://element-plus-admin-doc.cn/",
            "/guide",
            "/guide/index",
            "/components",
            "/components/form",
            "/components/form/default-form",
            "/components/form/use-form",
            "/components/form/ref-form",
            "/components/table",
            "/components/table/default-table",
            "/components/table/use-table",
            "/student",
            "/student/home",
            "/teacher",
            "/teacher/home",
            "/teacher/students",
            "/teacher/containers",
            "/teacher/containers/monitor"
        ]
    }
    
    routes = role_routes.get(role, [])
    
    return ApiResponse(code=0, data=routes)

