"""
教师 API 端点模块

包含教师相关的所有 API 功能:
- containers: 容器集群管理（已实现）
- basic: 基本 CRUD (增删改查教师信息，待实现)
- auth: 教师登录（待实现）
- exams: 考试管理（待实现）
- students: 学生管理（待实现）
- resources: 教学资源分发（待实现）
"""

from fastapi import APIRouter
from . import containers, students

# 创建教师路由聚合器
router = APIRouter()

# 容器管理（第二期已实现）
router.include_router(containers.router, prefix="/containers", tags=["教师-容器管理"])

# 学生管理（第五期）
router.include_router(students.router, prefix="/students", tags=["教师-学生管理"])

# 后续添加教师模块路由:
# from . import basic, auth, exams, students, resources
# router.include_router(basic.router, tags=["教师-基本信息"])
# router.include_router(auth.router, prefix="/auth", tags=["教师-认证"])
# router.include_router(exams.router, prefix="/exams", tags=["教师-考试管理"])
# router.include_router(students.router, prefix="/students", tags=["教师-学生管理"])
# router.include_router(resources.router, prefix="/resources", tags=["教师-资源分发"])
