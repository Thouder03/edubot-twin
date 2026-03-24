import asyncio
from app.db.database import engine
from app.db.base import Base
from app.models.student import Student
from app.models.container import SimContainer  # 确保 sim_containers 表被 metadata 发现
from app.crud.student import create_student
from app.schemas.student import StudentCreate
from app.db.database import AsyncSessionLocal


async def init_database():
    """初始化数据库:创建表并插入示例数据"""
    print("🔨 开始创建数据库表...")
    
    # 创建所有表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    print("✅ 数据库表创建完成!")
    
    # 插入示例学生数据
    print("\n📝 插入示例学生数据...")
    
    sample_students = [
        StudentCreate(
            username="student001",
            password="123456",
            real_name="张三",
            email="zhangsan@example.com"
        ),
        StudentCreate(
            username="student002",
            password="123456",
            real_name="李四",
            email="lisi@example.com"
        ),
        StudentCreate(
            username="student003",
            password="123456",
            real_name="王五",
            email=None
        ),
        StudentCreate(
            username="student004",
            password="123456",
            real_name="赵六",
            email="zhaoliu@example.com"
        ),
    ]
    
    async with AsyncSessionLocal() as db:
        created_count = 0
        for student_data in sample_students:
            try:
                student = await create_student(db, student_data)
                created_count += 1
                print(f"  ✓ 创建学生: {student.username} ({student.real_name})")
            except Exception as e:
                print(f"  ✗ 创建学生失败 ({student_data.username}): {e}")
    
    print(f"\n🎉 数据库初始化完成! 共创建 {created_count} 个示例学生")
    print(f"📊 数据库文件: edubot.db")


if __name__ == "__main__":
    asyncio.run(init_database())
