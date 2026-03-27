from pydantic import BaseModel, EmailStr, Field, ConfigDict
from datetime import datetime
from typing import Optional


class StudentBase(BaseModel):
    """学生基础字段"""
    username: str = Field(..., min_length=3, max_length=50, description="学号/用户名")
    real_name: Optional[str] = Field(None, max_length=50, description="真实姓名")
    email: Optional[EmailStr] = Field(None, description="邮箱")


class StudentCreate(StudentBase):
    """创建学生时的请求模型"""
    password: str = Field(..., min_length=6, max_length=50, description="明文密码")


class StudentUpdate(BaseModel):
    """更新学生时的请求模型(所有字段可选)"""
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    real_name: Optional[str] = Field(None, max_length=50)
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=6, max_length=50)
    is_active: Optional[bool] = None


class StudentResponse(StudentBase):
    """学生响应模型(不包含密码)"""
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
