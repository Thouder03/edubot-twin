"""
学生 API 端点模块

包含学生相关的所有 API 功能:
- basic: 基本 CRUD (增删改查学生信息)
- auth: 学生登录、注册 (待实现)
- exams: 考试相关 (学生视角, 待实现)
- containers: 容器操作 (启动、停止、重置, 待实现)
- learning: 学习记录、时长统计 (待实现)
- homework: 作业提交、查询 (待实现)
"""

from fastapi import APIRouter
from . import basic

# 创建学生路由聚合器
router = APIRouter()

# 挂载基本 CRUD 路由 (根路径)
router.include_router(basic.router, tags=["学生-基本信息"])

# 后续添加其他模块路由:
# from . import exams, containers, learning, homework
# router.include_router(exams.router, prefix="/exams", tags=["学生-考试"])
# router.include_router(containers.router, prefix="/containers", tags=["学生-容器"])
# router.include_router(learning.router, prefix="/learning", tags=["学生-学习记录"])
# router.include_router(homework.router, prefix="/homework", tags=["学生-作业"])
