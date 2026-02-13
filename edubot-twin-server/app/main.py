from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.api import api_router
from app.db.database import engine
from app.db.base import Base

# 创建 FastAPI 实例
app = FastAPI(
    title="Edubot Twin API",
    description="数字孪生机器人实训平台后端 API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite 开发服务器
        "http://localhost:3000",  # 备用端口
        "http://localhost:4000",  # 新增前端端口
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载 API 路由
app.include_router(api_router, prefix="/api/v1")


# 注意: 健康检查端点已移至 /api/v1/health


# 应用启动事件
@app.on_event("startup")
async def startup_event():
    """应用启动时的初始化操作"""
    print("🚀 Edubot Twin API 启动中...")
    print(f"📚 API 文档: http://localhost:8000/docs")
    print(f"🔄 异步数据库引擎已初始化")


# 应用关闭事件
@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时的清理操作"""
    await engine.dispose()
    print("👋 Edubot Twin API 已关闭")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
