"""
Shadow 学生账号管理

每位教师对应唯一一个 Shadow 学生账号，用于 Dry Run 仿真。
Shadow 学生的 role_code = "student"，可直接复用所有学生端接口。
"""
import secrets
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.student import hash_password
from app.models.student import User


async def get_shadow_by_teacher(db: AsyncSession, teacher_id: int) -> Optional[User]:
    """查询教师的 Shadow 学生账号（不存在返回 None）。"""
    result = await db.execute(
        select(User).where(
            User.is_shadow == True,  # noqa: E712
            User.shadow_owner_id == teacher_id,
        )
    )
    return result.scalar_one_or_none()


async def get_or_create_shadow(db: AsyncSession, teacher_id: int) -> User:
    """
    幂等：查询或创建教师的 Shadow 学生账号。

    Shadow 学生特征：
    - username: _shadow_{teacher_id}
    - role_code: student（可直接使用所有学生 API）
    - is_shadow: True
    - shadow_owner_id: teacher_id
    """
    existing = await get_shadow_by_teacher(db, teacher_id)
    if existing:
        return existing

    shadow = User(
        username=f"_shadow_{teacher_id}",
        password_hash=hash_password(secrets.token_hex(32)),  # 随机密码，永不用于登录
        real_name=f"DryRun-{teacher_id}",
        email=None,
        is_active=True,
        role_id="10",
        role_code="student",
        is_shadow=True,
        shadow_owner_id=teacher_id,
    )
    db.add(shadow)
    await db.commit()
    await db.refresh(shadow)
    return shadow


async def is_shadow_user(db: AsyncSession, user_id: int) -> bool:
    """快速检查指定用户是否为 Shadow 学生。"""
    result = await db.execute(
        select(User.is_shadow).where(User.id == user_id)
    )
    val = result.scalar_one_or_none()
    return bool(val)
