import asyncio
import logging
from app.db.database import engine
from app.db.base import Base
from app.models.student import Student
from app.models.container import SimContainer  # 确保 sim_containers 表被 metadata 发现
from app.crud.student import create_student
from app.schemas.student import StudentCreate
from app.db.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def init_database():
    """初始化数据库:创建表并插入示例数据"""
    print("🔨 开始创建数据库表...")
    
    # 创建所有表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    print("✅ 数据库表创建完成!")
    
    # 插入示例数据
    print("\n📝 插入示例数据...")
    
    sample_students = [
        # 教师测试账号
        StudentCreate(
            username="teacher",
            password="teacher123",
            real_name="教师测试账号",
            email="teacher@example.com",
            role_id="20",
            role_code="teacher",
        ),
        StudentCreate(
            username="admin",
            password="admin123",
            real_name="管理员测试账号",
            email="admin@example.com",
            role_id="30",
            role_code="admin",
        ),
        # 学生账号
        StudentCreate(
            username="student001",
            password="123456",
            real_name="张三",
            email="zhangsan@example.com",
            role_id="10",
            role_code="student",
        ),
        StudentCreate(
            username="student002",
            password="123456",
            real_name="李四",
            email="lisi@example.com",
            role_id="10",
            role_code="student",
        ),
        StudentCreate(
            username="student003",
            password="123456",
            real_name="王五",
            email=None,
            role_id="10",
            role_code="student",
        ),
        StudentCreate(
            username="student004",
            password="123456",
            real_name="赵六",
            email="zhaoliu@example.com",
            role_id="10",
            role_code="student",
        ),
    ]
    
    async with AsyncSessionLocal() as db:
        created_count = 0
        for student_data in sample_students:
            try:
                logger.info(
                    "[init_db][pre-create] username=%s role_id=%s role_code=%s",
                    student_data.username,
                    getattr(student_data, "role_id", None),
                    getattr(student_data, "role_code", None),
                )
                student = await create_student(db, student_data)
                created_count += 1
                logger.info(
                    "[init_db][post-create] username=%s role_id=%s role_code=%s",
                    student.username,
                    getattr(student, "role_id", None),
                    getattr(student, "role_code", None),
                )
                print(f"  ✓ 创建学生: {student.username} ({student.real_name})")
            except Exception as e:
                logger.exception(
                    "[init_db][create-failed] username=%s error=%s",
                    student_data.username,
                    e,
                )
                print(f"  ✗ 创建学生失败 ({student_data.username}): {e}")
    
    print(f"\n🎉 数据库初始化完成! 共创建 {created_count} 个示例学生")
    print(f"📊 数据库文件: edubot.db")


if __name__ == "__main__":
    asyncio.run(init_database())
