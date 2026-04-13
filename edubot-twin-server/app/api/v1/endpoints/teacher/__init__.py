"""
教师 API 端点模块

包含教师相关的所有 API 功能:
- containers: 容器集群管理（已实现）
- basic: 基本 CRUD (增删改查教师信息，待实现)
- auth: 教师登录（待实现）
- exams: 考试管理（第11期新增）
- students: 学生管理（待实现）
- resources: 教学资源分发（待实现）
"""

from fastapi import APIRouter
from . import (
    containers, students, monitor, experiments, file_bundles, env_bundles,
    dry_run_tools, container_files, container_proxy,
    exams, exam_env_snapshots, exam_file_snapshots, exam_eval_scripts,
    exam_attempts,
)

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

# 考试管理（第11期新增）
router.include_router(exams.router, prefix="/exams", tags=["教师-考试管理"])

# 考试环境快照（第11期新增）
router.include_router(exam_env_snapshots.router, prefix="/exam-env-snapshots", tags=["教师-考试环境快照"])

# 考试文件快照（第11期新增）
router.include_router(exam_file_snapshots.router, prefix="/exam-file-snapshots", tags=["教师-考试文件快照"])

# 测评脚本包（第11期新增）
router.include_router(exam_eval_scripts.router, prefix="/exam-eval-scripts", tags=["教师-测评脚本"])

# Dry Run 工具（Docker Logs / 失败回顾，仅 Shadow 学生可用）
router.include_router(dry_run_tools.router, prefix="/dry-run-tools", tags=["教师-DryRun工具"])

# Dry Run ROOT 文件操作（旧 docker exec 方案，保留兼容）
router.include_router(container_files.router, prefix="/dry-run-tools/files", tags=["教师-DryRun文件(旧)"])

# Dry Run 容器文件系统 Sidecar 代理（新方案，替代 docker exec）
router.include_router(container_proxy.router, prefix="/dry-run-tools/container-files", tags=["教师-DryRun文件代理"])

# 容器监控（第五期）—— 具体路径，优先注册
router.include_router(monitor.router, prefix="/containers/monitor", tags=["教师-容器监控"])


# 容器管理（第二期）—— 含 /{container_id} 参数路径，必须在具体路径之后注册
router.include_router(containers.router, prefix="/containers", tags=["教师-容器管理"])

# 学生管理（第五期）
router.include_router(students.router, prefix="/students", tags=["教师-学生管理"])

# 考试运行记录（第12期）
router.include_router(exam_attempts.router, tags=["教师-考试运行记录"])
