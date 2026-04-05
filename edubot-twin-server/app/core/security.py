"""
JWT Token 安全工具模块

提供 JWT Token 的创建和验证功能
"""

from datetime import datetime, timedelta
from jose import jwt, JWTError
from typing import Optional
from fastapi import Header, HTTPException, status as http_status

# JWT 配置
# 生产环境请修改为随机强密码并使用环境变量
SECRET_KEY = "edubot-twin-secret-key-please-change-in-production-xxxxxxxxxxxxxxxx"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    创建 JWT access token
    
    Args:
        data: 需要编码到 token 中的数据 (通常包含 sub, user_id, role 等)
        expires_delta: 自定义过期时间,默认使用 ACCESS_TOKEN_EXPIRE_DAYS
    
    Returns:
        编码后的 JWT token 字符串
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[dict]:
    """
    验证 JWT token 并返回解码后的数据
    
    Args:
        token: JWT token 字符串
    
    Returns:
        解码后的数据字典,如果验证失败返回 None
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


async def get_current_user_id(
    authorization: str = Header(
        ...,
        description="Bearer token，格式: Bearer <jwt_token>"
    ),
) -> int:
    """从 Authorization Header 提取 user_id，不限角色（任何已登录用户可用）。"""
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header 格式错误，需要 'Bearer <token>'"
        )
    token = authorization[7:]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期"
        )
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Token 中缺少 user_id"
        )
    return user_id


async def get_current_student_id(
    authorization: str = Header(
        ...,
        description="Bearer token，格式: Bearer <jwt_token>"
    ),
) -> int:
    """
    从 Authorization Header 提取 student_id

    用法: student_id: int = Depends(get_current_student_id)

    Raises:
        HTTPException(401): Token 无效或角色不是学生
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header 格式错误，需要 'Bearer <token>'"
        )

    token = authorization[7:]  # 去掉 "Bearer " 前缀
    payload = verify_token(token)

    if not payload:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期"
        )

    user_id = payload.get("user_id")
    role = payload.get("role")

    if not user_id or role != "student":
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="仅学生可访问此接口"
        )

    return user_id


async def get_current_teacher(
    authorization: str = Header(
        ...,
        description="Bearer token，格式: Bearer <jwt_token>"
    ),
) -> int:
    """
    从 Authorization Header 提取 teacher user_id
    
    用法: teacher_id: int = Depends(get_current_teacher)
    
    Raises:
        HTTPException(401): Token 无效
        HTTPException(403): 角色不是教师或管理员
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header 格式错误，需要 'Bearer <token>'"
        )
    
    token = authorization[7:]
    payload = verify_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期"
        )
    
    user_id = payload.get("user_id")
    role = payload.get("role")
    
    if not user_id or role not in ["teacher", "admin"]:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="需要教师或管理员权限"
        )
    
    return user_id
