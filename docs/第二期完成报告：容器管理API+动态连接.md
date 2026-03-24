# 第二期完成报告：容器管理 API + 动态连接

## 完成内容

### 后端新增文件

| 文件 | 说明 |
|---|---|
| [models/container.py](file:///home/ubuntu20/code/edubot-twin/edubot-twin-server/app/models/container.py) | SimContainer + ContainerStatus 枚举 |
| [schemas/container.py](file:///home/ubuntu20/code/edubot-twin/edubot-twin-server/app/schemas/container.py) | 3 个 Pydantic Schema，含 gzbridge_url 计算字段 |
| [core/port_allocator.py](file:///home/ubuntu20/code/edubot-twin/edubot-twin-server/app/core/port_allocator.py) | 端口分配器（9000-9499 / 9500-9999），防冲突 |
| [crud/container.py](file:///home/ubuntu20/code/edubot-twin/edubot-twin-server/app/crud/container.py) | 7 个 CRUD 函数，Docker 调用以 TODO 占位 |
| [teacher/containers.py](file:///home/ubuntu20/code/edubot-twin/edubot-twin-server/app/api/v1/endpoints/teacher/containers.py) | 教师端 6 个端点 |
| [student/container.py](file:///home/ubuntu20/code/edubot-twin/edubot-twin-server/app/api/v1/endpoints/student/container.py) | 学生端 2 个端点 |

### 前端新增/修改文件

| 文件 | 操作 | 说明 |
|---|---|---|
| [src/api/container/types.ts](file:///home/ubuntu20/code/edubot-twin/edubot-twin-web/src/api/container/types.ts) | 新建 | TS 类型定义 |
| [src/api/container/index.ts](file:///home/ubuntu20/code/edubot-twin/edubot-twin-web/src/api/container/index.ts) | 新建 | 8 个 API 封装函数 |
| [GzWebViewer/index.vue](file:///home/ubuntu20/code/edubot-twin/edubot-twin-web/src/views/Simulation/panels/GzWebViewer/index.vue) | 修改 | onMounted 新增 fetchAndApplyContainerUrl() |

---

## 数据库存储格式

### 1. 数据库表：`sim_containers`

| 字段名 (Field) | 数据库类型 | 约束 (Constraints) | 说明 (Description) |
| :--- | :--- | :--- | :--- |
| **id** | `Integer` | `PRIMARY KEY`, `AUTOINCREMENT` | 记录主键。 |
| **container_id** | `String(64)` | `UNIQUE`, `NULLABLE` | Docker 容器 ID（通常存储 sha256 的前 12 位）。 |
| **student_id** | `Integer` | `ForeignKey("students.id")`, `NOT NULL`, `INDEX` | 关联的学生 ID，用于标识容器的所有权。 |
| **image_name** | `String(200)` | `NOT NULL`, 默认: `edubot/gazebo-ros:latest` | 启动容器所使用的 Docker 镜像。 |
| **status** | `Enum` | `NOT NULL`, 默认: `creating` | 容器生命周期状态（见下文）。 |
| **gzbridge_port** | `Integer` | `NULLABLE` | Gzbridge (Web Gazebo) 映射到宿主机的端口 (9000-9499)。 |
| **rosbridge_port** | `Integer` | `NULLABLE` | Rosbridge (ROS WebSocket) 映射到宿主机的端口 (9500-9999)。 |
| **created_at** | `DateTime` | `NOT NULL`, 默认: `utcnow` | 记录创建时间。 |
| **updated_at** | `DateTime` | `NOT NULL`, 默认: `utcnow` | 记录最后的更新时间（如状态变更）。 |

### 2. 枚举类型：`ContainerStatus`

*   **`creating`**: 正在由 Docker 引擎创建中。
*   **`running`**: 容器运行正常，仿真桥接服务可用。
*   **`stopped`**: 容器已停止，宿主机端口已释放。
*   **`error`**: 创建失败或运行过程中发生错误。
*   **`removing`**: 正在执行销毁/清理操作。

---

## curl 验证结果

列出容器: `[]` -> 创建后返回含 gzbridge_url/rosbridge_url 完整列表

停止容器: `{"id": 1, "status": "stopped"}`

学生查询: `{"id": 2, "status": "running", "gzbridge_url": "http://localhost:9001"}`

学生自动创建: 无容器时自动创建并端口递增分配

---

> [!IMPORTANT]
> Docker 实际调用以 Mock 占位（crud/container.py 中 # TODO: DOCKER 注释处），接入真实 Docker 环境时按注释替换即可。

> [!NOTE]
> GzWebViewer 中 studentId 临时硬编码为 1，接入 JWT 后改从 userStore 读取。
