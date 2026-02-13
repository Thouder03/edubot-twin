"""
公共 API 端点模块

包含跨角色的公共功能:
- auth: 统一认证 (登录、Token、用户信息)
- health: 健康检查
- upload: 文件上传 (待实现)
- download: 文件下载 (待实现)
"""

from fastapi import APIRouter
from . import auth

router = APIRouter()

# 挂载认证路由
router.include_router(auth.router, prefix="/auth", tags=["系统-认证"])


@router.get("/health", summary="健康检查", tags=["系统-健康检查"])
async def health_check():
    """系统健康检查端点"""
    return {"status": "healthy", "service": "edubot-twin-api"}
