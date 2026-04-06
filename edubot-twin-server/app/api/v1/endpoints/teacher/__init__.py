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
from . import containers, students, monitor, experiments, file_bundles, env_bundles, dry_run_tools, container_files

# 创建教师路由聚合器
router = APIRouter()

# ⚠️ 注册顺序关键：/containers/monitor 必须在 /containers/{container_id} 之前注册
# 否则 FastAPI 会把字符串 "monitor" 当作整型 container_id 解析，返回 422

# 实验管理（第10期新增）
router.include_router(experiments.router, prefix="/experiments", tags=["教师-实验管理"])

# 文件包管理（10-S1-6 新增）
router.include_router(file_bundles.router, prefix="/file-bundles", tags=["教师-文件包管理"])

# 环境包管理（10-S1-4 新增）
router.include_router(env_bundles.router, prefix="/env-bundles", tags=["教师-环境包管理"])

# Dry Run 工具（Docker Logs / 失败回顾，仅 Shadow 学生可用）
router.include_router(dry_run_tools.router, prefix="/dry-run-tools", tags=["教师-DryRun工具"])

# Dry Run ROOT 文件操作（容器内文件系统，仅 Shadow 学生可用）
router.include_router(container_files.router, prefix="/dry-run-tools/files", tags=["教师-DryRun文件"])

# 容器监控（第五期）—— 具体路径，优先注册
router.include_router(monitor.router, prefix="/containers/monitor", tags=["教师-容器监控"])


# 容器管理（第二期）—— 含 /{container_id} 参数路径，必须在具体路径之后注册
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
