from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.student import DEFAULT_ROLE_CODE, DEFAULT_ROLE_ID


class UserBase(BaseModel):
    """统一用户基础字段。"""

    username: str = Field(..., min_length=3, max_length=50, description="学号/用户名")
    real_name: Optional[str] = Field(None, max_length=50, description="真实姓名")
    email: Optional[EmailStr] = Field(None, description="邮箱")
    role_id: str = Field(default=DEFAULT_ROLE_ID, min_length=1, max_length=20, description="角色稳定主键")
    role_code: str = Field(default=DEFAULT_ROLE_CODE, min_length=1, max_length=50, description="角色代码")


class UserCreate(UserBase):
    """创建用户时的请求模型。"""

    password: str = Field(..., min_length=6, max_length=50, description="明文密码")


class UserUpdate(BaseModel):
    """更新用户时的请求模型（所有字段可选）。"""

    username: Optional[str] = Field(None, min_length=3, max_length=50)
    real_name: Optional[str] = Field(None, max_length=50)
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=6, max_length=50)
    is_active: Optional[bool] = None
    role_id: Optional[str] = Field(None, min_length=1, max_length=20)
    role_code: Optional[str] = Field(None, min_length=1, max_length=50)


class UserResponse(UserBase):
    """统一用户响应模型（不包含密码）。"""

    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserListResponse(BaseModel):
    """用户列表分页响应。"""

    total: int
    list: List[UserResponse]


StudentBase = UserBase
StudentCreate = UserCreate
StudentUpdate = UserUpdate
StudentResponse = UserResponse
StudentListResponse = UserListResponse


class ImportFailedRow(BaseModel):
    """批量导入中单行失败的详情。"""

    row: int = Field(..., description="数据行号（从 1 开始，不含标题行）")
    username: str
    error: str


class StudentImportResult(BaseModel):
    """批量导入结果。"""

    total: int
    success: int
    failed: List[ImportFailedRow]
