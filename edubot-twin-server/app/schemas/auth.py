"""
认证相关的 Pydantic Schema
"""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """登录请求"""
    username: str = Field(..., min_length=1, max_length=50, description="用户名")
    password: str = Field(..., min_length=1, description="密码")


class LoginData(BaseModel):
    """登录用户信息"""
    username: str = Field(..., description="用户名")
    role: str = Field(..., description="角色")
    roleId: str = Field(..., description="角色ID")


class TokenData(BaseModel):
    """Token 数据"""
    access_token: str = Field(..., description="JWT Token")
    token_type: str = Field(default="Bearer", description="Token 类型")
