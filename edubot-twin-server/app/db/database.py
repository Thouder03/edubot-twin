from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from typing import AsyncGenerator

# SQLite 异步数据库 URL
DATABASE_URL = "sqlite+aiosqlite:///./edubot.db"

# 创建异步引擎
engine = create_async_engine(
    DATABASE_URL,
    echo=True,  # 开发环境打印 SQL 日志
    future=True,
    pool_size=20,  # 连接池大小
    max_overflow=10,  # 超出 pool_size 后最多创建的连接数
    pool_timeout=30,  # 获取连接的超时时间（秒）
    pool_recycle=3600,  # 连接回收时间（秒），防止连接过期
)

# 创建异步会话工厂
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# 依赖注入函数:为每个请求提供数据库会话
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
