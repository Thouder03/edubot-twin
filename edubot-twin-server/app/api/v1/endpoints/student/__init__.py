"""
学生 API 端点模块

包含学生相关的所有 API 功能:
- basic: 基本 CRUD (增删改查学生信息)
- container: 容器操作——查询分配的容器、请求分配（第二期已实现）
- auth: 学生登录、注册 (待实现)
- exams: 考试相关 (学生视角, 待实现)
- learning: 学习记录、时长统计 (待实现)
- homework: 作业提交、查询 (待实现)
"""

from fastapi import APIRouter
from . import basic, container, terminal, files, experiments, simulation

# 创建学生路由聚合器
router = APIRouter()

# 挂载基本 CRUD 路由
router.include_router(basic.router, tags=["学生-基本信息"])

# 挂载容器路由（第二期已实现）
router.include_router(container.router, prefix="/container", tags=["学生-容器"])

# 挂载终端 WebSocket 路由（第六期新增）
router.include_router(terminal.router, prefix="/terminal", tags=["学生-终端"])

# 挂载文件管理路由（第七期新增）
router.include_router(files.router, prefix="/files", tags=["学生-文件管理"])

# 第10期：实验版本与仿真启动主链路
router.include_router(experiments.router, prefix="/experiments", tags=["学生-实验版本"])
router.include_router(simulation.router, prefix="/simulation", tags=["学生-仿真启动"])

# 后续添加其他模块路由:
# from . import exams, learning, homework
# router.include_router(exams.router, prefix="/exams", tags=["学生-考试"])
# router.include_router(learning.router, prefix="/learning", tags=["学生-学习记录"])
# router.include_router(homework.router, prefix="/homework", tags=["学生-作业"])
