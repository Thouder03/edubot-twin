"""
通用响应 Schema

提供统一的 API 响应格式包装器
"""

from typing import Generic, TypeVar, Optional
from pydantic import BaseModel, Field

T = TypeVar('T')


class ApiResponse(BaseModel, Generic[T]):
    """统一 API 响应格式
    
    所有 API 端点应使用此格式返回数据，以便前端统一处理
    """
    code: int = Field(default=0, description="状态码，0=成功，非0=失败")
    data: Optional[T] = Field(default=None, description="响应数据")
    message: Optional[str] = Field(default=None, description="提示信息")

    class Config:
        json_schema_extra = {
            "example": {
                "code": 0,
                "data": {"key": "value"},
                "message": None
            }
        }
