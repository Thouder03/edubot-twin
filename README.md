# Edubot Twin - 面向移动机器人实训的数字孪生评测平台

**Edubot Twin** 是一个基于 Web 的机器人仿真教学与自动化评测平台。它通过**数字孪生技术**，将 ROS (Robot Operating System) 仿真环境搬进浏览器，为学生提供无需本地配置的沉浸式实训体验，同时为教师提供可视化的容器集群管理与学情分析工具。

🎓 **毕设题目**：面向移动机器人实训的数字孪生评测平台设计与实现

## ✨ 核心功能(待完善)

### 👨‍🏫 教师端 (Admin Portal)

- **容器集群管理**：基于 Docker 的学生实验环境动态创建、监控与销毁。
- **性能遥测**：实时监控容器 CPU、内存占用，以及通过 WebSocket 传输的 ROS 运行状态。
- **教学资源分发**：一键下发 ROS 节点代码、Launch 文件至所有在线学生容器。
- **数据可视化**：服务器负载监控与学生历史实训时长统计。
- **在线评测**：支持学生考试时的 ROS/Gazebo 录制与回放，便于教师进行人工打分或自动化评测。
- **学习行为分析(可能做)**：分析学生的学习行为，生成学习报告。

### 👨‍🎓 学生端 (Student Workbench)

- **Web 3D 可视化**：集成 `ros3djs`，在浏览器中实时渲染激光雷达点云、TF 坐标系、机器模型与栅格地图。
- **仿真交互**：嵌入 GzWeb/Iframe 物理仿真场景，支持键盘/虚拟摇杆控制。
- **云端开发工具**：内置 Web 终端 (`xterm.js`) 与代码编辑器，直接在网页调试 ROS 程序。
- **双模式切换**：支持“自由练习模式”与“考试评测模式”。

## 🛠️ 技术栈(待完善)

| 模块              | 技术选型                                                  |
| ----------------- | --------------------------------------------------------- |
| **前端 (Web)**    | Vue 3.5, Vite 6, Element Plus (Admin), UnoCSS, TypeScript |
| **机器人 Web**    | roslibjs (WebSocket), ros3djs (WebGL), xterm.js           |
| **后端 (Server)** | Python 3.9+, FastAPI (Async), SQLModel (ORM), Pydantic V2 |
| **基础设施**      | Docker SDK, WebSocket, PostgreSQL, Nginx                  |
| **仿真环境**      | ROS Noetic, Gazebo, Ubuntu 20.04 Containers               |

## 📂 目录结构(待完善)

项目采用 Monorepo 风格管理：

```text
edubot-twin/
├── edubot-twin-web/        # 前端项目 (基于 vue-element-plus-admin 架构)
│   ├── src/views/teacher/  # 教师端页面
│   └── src/views/student/  # 学生仿真工作台
├── edubot-twin-server/     # 后端项目
│   ├── app/                # FastAPI 核心代码
│   ├── docker/             # ROS 基础镜像 Dockerfile
│   └── main.py             # 启动入口
├── docker-compose.yml      # 开发环境编排 (DB, Redis 等)
└── README.md               # 项目说明文档

```

## 📄 许可证

MIT License © 2026 Edubot Twin Team
