# Edubot Twin - 面向移动机器人实训的数字孪生评测平台

**Edubot Twin** 是一个基于 Web 的机器人仿真教学与自动化评测平台。它通过**数字孪生技术**，将 ROS (Robot Operating System) 仿真环境搬进浏览器，为学生提供无需本地配置的沉浸式实训体验，同时为教师提供可视化的容器集群管理与学情分析工具。

🎓 **毕设题目**：面向移动机器人实训的数字孪生评测平台设计与实现

## ✨ 核心功能

### 👨‍🏫 教师端 (Admin Portal)

- **容器集群管理**：基于 Docker SDK 的学生仿真容器动态创建、启停、监控与销毁，支持端口自动分配与心跳检测
- **性能遥测**：每 10 秒自动采集容器 CPU、内存占用，历史数据保留 7 天
- **在线考试评测**：教师可创建考试、配置面板锁定策略、定义自动化评分脚本；支持考试环境快照与回放
- **学生管理**：学生账号 CRUD，工作区目录管理，实验进度跟踪
- **资源分发**：环境资源包 (EnvBundle) 与文件资源包 (FileBundle) 管理，一键分发至学生容器
- **孤儿容器自愈**：三阶段 reconcile 机制（僵死回收 → DB-Docker 校准 → 反向清洗），自动清理异常容器

### 👨‍🎓 学生端 (Student Workbench)

- **Web 3D 可视化**：基于 Lichtblick Renderer-Extension 架构的 Three.js 渲染引擎，实时显示激光雷达点云、TF 坐标系、机器人模型、栅格地图、Marker 标记等
- **仿真交互**：嵌入 GzWeb iframe 物理仿真场景，支持键盘控制机器人运动
- **云端开发工具**：内置 Web 终端 (`xterm.js`) 与代码编辑器 (Monaco)，直接在浏览器中调试 ROS 程序
- **双模式切换**：支持"自由练习模式"与"考试评测模式"，考试期间可锁定面板
- **可定制工作台**：基于 Golden Layout 2.6 的面板系统，支持拖拽、拆分、堆叠，7 种功能面板自由组合

## 🛠️ 技术栈

| 模块              | 技术选型 |
| ----------------- | -------- |
| **前端框架**      | Vue 3.5, Vite 6, TypeScript, Pinia |
| **UI 组件库**     | Element Plus 2.9, UnoCSS, Less (BEM) |
| **机器人 Web**    | roslibjs (WebSocket), Three.js (WebGL), xterm.js |
| **3D 渲染**       | 自研 Renderer-Extension 架构（移植自 Lichtblick） |
| **布局系统**      | Golden Layout 2.6.0 |
| **后端框架**      | Python 3.9+, FastAPI (Async), Uvicorn |
| **ORM / 数据库**  | SQLAlchemy 2.0 (Async) + SQLite（生产建议切换 PostgreSQL） |
| **数据验证**      | Pydantic V2 |
| **认证**          | JWT (python-jose) + bcrypt |
| **容器管理**      | Docker SDK for Python |
| **反向代理**      | Nginx |
| **仿真环境**      | ROS Noetic, Gazebo, Ubuntu 20.04 Containers |

## 📂 目录结构

```text
edubot-twin/
├── edubot-twin-web/            # 前端项目 (基于 vue-element-plus-admin)
│   ├── src/
│   │   ├── views/
│   │   │   ├── Simulation/     # ★ 核心仿真工作台（Golden Layout + 面板系统）
│   │   │   ├── Student/        # 学生端页面
│   │   │   ├── Teacher/        # 教师端页面
│   │   │   └── Authorization/  # 权限管理
│   │   ├── api/                # HTTP 请求模块（按业务拆分）
│   │   ├── components/Ros/     # ROS 通用组件
│   │   ├── router/             # 动态路由配置
│   │   └── hooks/web/          # useRos, useTerminal 等组合式函数
│   └── mock/                   # 前端 Mock 数据（开发环境）
├── edubot-twin-server/         # 后端项目
│   ├── app/
│   │   ├── main.py             # FastAPI 入口（含 lifespan 后台任务）
│   │   ├── api/v1/endpoints/   # 按角色分模块的 API 端点
│   │   ├── core/               # 容器管理、安全、日志、评分等核心模块
│   │   ├── services/           # 业务逻辑层
│   │   ├── models/             # SQLAlchemy ORM 模型
│   │   ├── schemas/            # Pydantic Schema
│   │   ├── crud/               # 数据库操作层
│   │   └── db/                 # 数据库配置与迁移
│   ├── tests/                  # pytest 异步测试
│   └── data/                   # 运行时数据（学生工作区、考试产物等）
├── scripts/                    # 启停、测试、迁移等 .sh 脚本
├── nginx/                      # Nginx 反向代理配置
├── data/                       # 共享数据目录
├── logs/                       # 统一日志输出
└── docs/                       # 项目文档
```

## 🚀 快速开始

### 环境要求

- Node.js >= 18.0.0, pnpm >= 8.1.0
- Python >= 3.9, 虚拟环境位于项目根目录 `.venv/`
- Docker (运行仿真容器)

### 启动开发环境

```bash
# 1. 安装后端依赖并初始化数据库
cd edubot-twin-server
../.venv/bin/pip install -r requirements.txt
../.venv/bin/python init_db.py

# 2. 启动后端 API 服务（端口 8000）
bash scripts/start_server.sh

# 3. 安装前端依赖并启动开发服务器（端口 4000）
cd edubot-twin-web
pnpm install
pnpm run dev

# 4.（可选）启动 Nginx 反向代理
bash scripts/start_nginx_dev.sh
```

### 运行测试

```bash
# 前端类型检查
bash scripts/ts_check_web.sh

# 后端全部测试
cd edubot-twin-server && ../.venv/bin/python -m pytest tests/ -v

# 运行单个测试文件
cd edubot-twin-server && ../.venv/bin/python -m pytest tests/test_exam_domain.py -v

# 接口集成测试
bash scripts/test_server_phase10.sh
```

## 📖 开发指南

详细开发文档见：

- **CLAUDE.md** — AI 辅助开发完整指引（架构、规范、常见任务）
- **`.claude/rules/`** — 扩展开发、面板开发、路由配置等专项规范
- **`edubot-twin-server/API_ARCHITECTURE.md`** — API 架构设计文档
- **`edubot-twin-web/src/views/Simulation/panels/ROS3DViewer/CLAUDE.md`** — 3D 渲染扩展开发指南

## 📄 许可证

MIT License © 2026 Edubot Twin Team
