from typing import List, Optional, Tuple

import bcrypt
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.student import ROLE_CODE_BY_ID, ROLE_ID_BY_CODE, User
from app.schemas.student import UserCreate, UserUpdate


def hash_password(password: str) -> str:
    """使用 bcrypt 哈希密码。"""
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def _resolve_role_fields(role_id: Optional[str], role_code: Optional[str]) -> tuple[str, str]:
    """统一 role_id / role_code，允许任一侧驱动另一侧。"""
    if role_id and role_code:
        expected_role_code = ROLE_CODE_BY_ID.get(role_id)
        if expected_role_code and expected_role_code != role_code:
            return role_id, expected_role_code
        expected_role_id = ROLE_ID_BY_CODE.get(role_code)
        if expected_role_id:
            return expected_role_id, role_code
        return role_id, role_code

    if role_id:
        return role_id, ROLE_CODE_BY_ID.get(role_id, "student")

    if role_code:
        return ROLE_ID_BY_CODE.get(role_code, "10"), role_code

    return "10", "student"


async def get_users(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    keyword: Optional[str] = None,
) -> Tuple[List[User], int]:
    """获取用户列表（分页 + 可选关键词过滤，排除 Shadow 账号）。"""
    base_query = select(User).where(User.is_shadow == False)  # noqa: E712
    count_query = select(func.count()).select_from(User).where(User.is_shadow == False)  # noqa: E712

    if keyword:
        like_expr = f"%{keyword}%"
        filter_cond = or_(
            User.username.like(like_expr),
            User.real_name.like(like_expr),
        )
        base_query = base_query.where(filter_cond)
        count_query = count_query.where(filter_cond)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    result = await db.execute(base_query.offset(skip).limit(limit))
    return list(result.scalars().all()), total


async def get_students(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    keyword: Optional[str] = None,
) -> Tuple[List[User], int]:
    """兼容学生语义的用户列表查询。"""
    return await get_users(db, skip=skip, limit=limit, keyword=keyword)


async def get_user(db: AsyncSession, user_id: int) -> Optional[User]:
    """根据 ID 获取用户。"""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_student(db: AsyncSession, student_id: int) -> Optional[User]:
    """兼容学生语义的单个用户查询。"""
    return await get_user(db, student_id)


async def get_student_by_id(db: AsyncSession, student_id: int) -> Optional[User]:
    """兼容学生语义的按 ID 查询。"""
    return await get_user(db, student_id)


async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
    """根据用户名获取用户。"""
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def get_student_by_username(db: AsyncSession, username: str) -> Optional[User]:
    """兼容学生语义的按用户名查询。"""
    return await get_user_by_username(db, username)


async def create_user(db: AsyncSession, user_data: UserCreate) -> User:
    """创建用户。"""
    hashed_password = hash_password(user_data.password)
    role_id, role_code = _resolve_role_fields(user_data.role_id, user_data.role_code)

    db_user = User(
        username=user_data.username,
        password_hash=hashed_password,
        real_name=user_data.real_name,
        email=user_data.email,
        role_id=role_id,
        role_code=role_code,
    )

    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user


async def create_student(db: AsyncSession, student_data: UserCreate) -> User:
    """兼容学生语义的创建接口。"""
    return await create_user(db, student_data)


async def update_user(
    db: AsyncSession,
    user_id: int,
    user_data: UserUpdate,
) -> Optional[User]:
    """更新用户信息。"""
    db_user = await get_user(db, user_id)
    if not db_user:
        return None

    update_data = user_data.model_dump(exclude_unset=True)

    if "password" in update_data:
        update_data["password_hash"] = hash_password(update_data.pop("password"))

    role_id = update_data.get("role_id", db_user.role_id)
    role_code = update_data.get("role_code", db_user.role_code)
    resolved_role_id, resolved_role_code = _resolve_role_fields(role_id, role_code)
    update_data["role_id"] = resolved_role_id
    update_data["role_code"] = resolved_role_code

    for key, value in update_data.items():
        setattr(db_user, key, value)

    await db.commit()
    await db.refresh(db_user)
    return db_user


async def update_student(
    db: AsyncSession,
    student_id: int,
    student_data: UserUpdate,
) -> Optional[User]:
    """兼容学生语义的更新接口。"""
    return await update_user(db, student_id, student_data)


async def delete_user(db: AsyncSession, user_id: int) -> bool:
    """删除用户。"""
    db_user = await get_user(db, user_id)
    if not db_user:
        return False

    await db.delete(db_user)
    await db.commit()
    return True


async def delete_student(db: AsyncSession, student_id: int) -> bool:
    """兼容学生语义的删除接口。"""
    return await delete_user(db, student_id)
