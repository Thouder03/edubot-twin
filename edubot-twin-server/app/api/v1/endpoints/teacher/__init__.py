"""
教师 API 端点模块 (待实现)

包含教师相关的所有 API 功能:
- basic: 基本 CRUD (增删改查教师信息)
- auth: 教师登录
- exams: 考试管理 (教师视角：创建、批改)
- containers: 容器集群管理
- students: 学生管理 (查看学情、分配资源)
- resources: 教学资源分发
"""

from fastapi import APIRouter

# 创建教师路由聚合器
router = APIRouter()

# 后续添加教师模块路由:
# from . import basic, auth, exams, containers, students, resources
# router.include_router(basic.router, tags=["教师-基本信息"])
# router.include_router(auth.router, prefix="/auth", tags=["教师-认证"])
# router.include_router(exams.router, prefix="/exams", tags=["教师-考试管理"])
# router.include_router(containers.router, prefix="/containers", tags=["教师-容器管理"])
# router.include_router(students.router, prefix="/students", tags=["教师-学生管理"])
# router.include_router(resources.router, prefix="/resources", tags=["教师-资源分发"])

# 临时健康检查端点
@router.get("/", tags=["教师-占位"])
async def teacher_placeholder():
    """教师 API 占位符,待实现"""
    return {"message": "Teacher API - Coming soon"}
