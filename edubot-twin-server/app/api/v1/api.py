"""
API v1 版本路由聚合器

按角色和功能模块组织路由:
- /students: 学生相关 API
- /teachers: 教师相关 API  
- /common: 公共功能 API
"""

from fastapi import APIRouter
from app.api.v1.endpoints import student, teacher, common

api_router = APIRouter()

# 挂载学生路由 (已完成基本 CRUD)
api_router.include_router(
    student.router, 
    prefix="/students"
)

# 挂载教师路由 (待实现)
api_router.include_router(
    teacher.router, 
    prefix="/teachers"
)

# 挂载公共路由
api_router.include_router(
    common.router
)
