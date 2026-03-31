from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

ROLE_ID_BY_CODE = {
    "student": "10",
    "teacher": "20",
    "admin": "30",
}
ROLE_CODE_BY_ID = {value: key for key, value in ROLE_ID_BY_CODE.items()}
DEFAULT_ROLE_CODE = "student"
DEFAULT_ROLE_ID = ROLE_ID_BY_CODE[DEFAULT_ROLE_CODE]


class User(Base):
    """统一用户数据模型（对外继续兼容 Student 语义）"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    real_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(100), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    role_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True, default=DEFAULT_ROLE_ID)
    role_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True, default=DEFAULT_ROLE_CODE)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    containers: Mapped[list["SimContainer"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def role(self) -> str:
        """兼容前端登录态中的 role 语义。"""
        return self.role_code

    @property
    def roleId(self) -> str:
        """兼容前端登录态中的 roleId 语义。"""
        return self.role_id

    def __repr__(self) -> str:
        return (
            f"<User(id={self.id}, username='{self.username}', "
            f"role_code='{self.role_code}', real_name='{self.real_name}')>"
        )


Student = User
