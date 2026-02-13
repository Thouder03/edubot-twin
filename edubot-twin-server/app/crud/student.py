from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.models.student import Student
from app.schemas.student import StudentCreate, StudentUpdate
import bcrypt
from typing import Optional


def hash_password(password: str) -> str:
    """使用 bcrypt 哈希密码"""
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


async def get_students(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100
) -> list[Student]:
    """
    获取学生列表(分页)
    
    Args:
        db: 数据库会话
        skip: 跳过的记录数
        limit: 返回的最大记录数
    
    Returns:
        学生列表
    """
    result = await db.execute(
        select(Student).offset(skip).limit(limit)
    )
    return list(result.scalars().all())


async def get_student_by_id(db: AsyncSession, student_id: int) -> Optional[Student]:
    """
    根据 ID 获取学生
    
    Args:
        db: 数据库会话
        student_id: 学生 ID
    
    Returns:
        学生对象或 None
    """
    result = await db.execute(
        select(Student).where(Student.id == student_id)
    )
    return result.scalar_one_or_none()


async def get_student_by_username(db: AsyncSession, username: str) -> Optional[Student]:
    """
    根据用户名获取学生
    
    Args:
        db: 数据库会话
        username: 用户名
    
    Returns:
        学生对象或 None
    """
    result = await db.execute(
        select(Student).where(Student.username == username)
    )
    return result.scalar_one_or_none()


async def create_student(db: AsyncSession, student_data: StudentCreate) -> Student:
    """
    创建学生
    
    Args:
        db: 数据库会话
        student_data: 学生创建数据
    
    Returns:
        创建的学生对象
    
    Raises:
        IntegrityError: 用户名或邮箱重复
    """
    # 哈希密码
    hashed_password = hash_password(student_data.password)
    
    # 创建学生对象
    db_student = Student(
        username=student_data.username,
        password_hash=hashed_password,
        real_name=student_data.real_name,
        email=student_data.email,
    )
    
    db.add(db_student)
    await db.commit()
    await db.refresh(db_student)
    return db_student


async def update_student(
    db: AsyncSession,
    student_id: int,
    student_data: StudentUpdate
) -> Optional[Student]:
    """
    更新学生信息
    
    Args:
        db: 数据库会话
        student_id: 学生 ID
        student_data: 更新数据
    
    Returns:
        更新后的学生对象或 None
    """
    db_student = await get_student_by_id(db, student_id)
    if not db_student:
        return None
    
    # 更新字段
    update_data = student_data.model_dump(exclude_unset=True)
    
    # 如果更新密码,需要哈希
    if "password" in update_data:
        update_data["password_hash"] = hash_password(update_data.pop("password"))
    
    for key, value in update_data.items():
        setattr(db_student, key, value)
    
    await db.commit()
    await db.refresh(db_student)
    return db_student


async def delete_student(db: AsyncSession, student_id: int) -> bool:
    """
    删除学生
    
    Args:
        db: 数据库会话
        student_id: 学生 ID
    
    Returns:
        是否成功删除
    """
    db_student = await get_student_by_id(db, student_id)
    if not db_student:
        return False
    
    await db.delete(db_student)
    await db.commit()
    return True
