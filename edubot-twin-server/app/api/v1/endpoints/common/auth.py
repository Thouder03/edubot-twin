"""
统一认证 API 端点

支持学生和教师使用同一个接口登录,自动识别角色
"""

import bcrypt
import logging
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, verify_token
from app.crud import student as crud_student
from app.db.database import get_db
from app.schemas.auth import LoginData, LoginRequest, TokenData
from app.schemas.common import ApiResponse
from app.schemas.student import StudentResponse

router = APIRouter()
logger = logging.getLogger(__name__)


def _verify_password(plain_password: str, password_hash: str) -> bool:
    """校验明文密码与 bcrypt 哈希。"""
    return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))


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

    user = await crud_student.get_user_by_username(db, login_data.username)
    if not user:
        return error_response

    if not _verify_password(login_data.password, user.password_hash):
        return error_response

    if not user.is_active:
        return ApiResponse(code=403, message="账号已被禁用", data=None)

    return ApiResponse(
        code=0,
        data=LoginData(
            username=user.username,
            role=user.role_code,
            roleId=user.role_id,
        ),
    )


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

    user = await crud_student.get_user_by_username(db, login_data.username)
    if not user:
        return error_response

    if not _verify_password(login_data.password, user.password_hash):
        return error_response

    if not user.is_active:
        return ApiResponse(code=403, message="账号已被禁用", data=None)

    token_data = {
        "sub": user.username,
        "user_id": user.id,
        "role": user.role_code,
        "role_id": user.role_id,
    }
    access_token = create_access_token(token_data)
    return ApiResponse(
        code=0,
        data=TokenData(access_token=access_token, token_type="Bearer"),
    )


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
        logger.warning("[auth.me] invalid-token")
        return auth_error

    username = payload.get("sub")
    role = payload.get("role")
    role_id = payload.get("role_id")
    user_id = payload.get("user_id")
    logger.info(
        "[auth.me] token-payload sub=%s user_id=%s role=%s role_id=%s",
        username,
        user_id,
        role,
        role_id,
    )

    if not username or not role:
        logger.warning("[auth.me] token-missing-required-fields sub=%s role=%s", username, role)
        return ApiResponse(code=401, message="Token 数据无效", data=None)

    user = await crud_student.get_user_by_username(db, username)
    if not user:
        logger.warning("[auth.me] user-not-found sub=%s", username)
        return ApiResponse(code=404, message="用户不存在", data=None)

    logger.info(
        "[auth.me] db-user username=%s user_id=%s role_code=%s role_id=%s",
        user.username,
        user.id,
        getattr(user, "role_code", None),
        getattr(user, "role_id", None),
    )

    if user.role_code != role:
        logger.warning(
            "[auth.me] role-mismatch token_role=%s db_role=%s username=%s",
            role,
            user.role_code,
            username,
        )
        return ApiResponse(code=401, message="Token 角色与用户数据不一致", data=None)

    return ApiResponse(code=0, data=user)


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
            "/teacher/containers/monitor",
            "/teacher/experiments",
            "/teacher/experiments/list",
            "/teacher/experiments/:id/detail",
            "/teacher/experiments/files",
            "/teacher/experiments/environments",
            "/teacher/exams",
            "/teacher/exams/list",
            "/teacher/exams/:id/detail",
            "/teacher/exams/envs",
            "/teacher/exams/files",
            "/teacher/exams/eval-scripts",
            "/teacher/exams/attempts/:attempt_id/review"
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
            "/teacher/containers/monitor",
            "/teacher/experiments",
            "/teacher/experiments/:id"
        ]
    }
    
    routes = role_routes.get(role, [])
    
    return ApiResponse(code=0, data=routes)

