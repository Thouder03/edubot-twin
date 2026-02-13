"""
JWT Token 安全工具模块

提供 JWT Token 的创建和验证功能
"""

from datetime import datetime, timedelta
from jose import jwt, JWTError
from typing import Optional

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
