# SDD-第10期补充：实验管理增强与资源管理体系

- **文档版本**：v1.2
- **创建日期**：2026-04-04
- **修订日期**：2026-04-04
- **负责人**：架构组
- **关联需求**：第10期主链路 SDD 遗留项补全、实验管理体验增强、教师资源管理体系建设
- **前置依赖**：第10期主链路 SDD v1.3（已冻结）
- **目标读者**：产品 / 前端 / 后端 / 测试

---

## 0) 分期总览表

本补充 SDD 内含两个子期次，彼此强关联（10-S2 依赖 10-S1 的模型与 API）。

| 子期次 | 目标 | 范围边界 | 依赖 | 风险 |
|---|---|---|---|---|
| **10-S1** 模型修正与核心链路补全 | 修复数据模型缺陷、补全缺失 API、注入容器启动配置、容器就绪检测 | 不含 UI 页面重构；不含 Dry Run 容器 | 第10期主链路已稳定 | 模型迁移需兼容已有数据；launch 注入引入新失败路径 |
| **10-S2** 教师资源管理页面 | 路由重构为二级菜单、新增实验文件管理页、新增实验环境管理页（含 Dry Run，复用学生仿真页面） | 不含评测联动；不含多租户配额 | 10-S1 模型与 API 已就绪 | 页面复用度高但交互复杂；Dry Run 容器停止后即清理 |

---

## 1) 执行摘要

### 1.1 问题

1. **文件包上传端点完全缺失**：第10期 API 契约表定义了 `POST /teachers/experiment-files/upload`，但后端无实现，教师无法上传实验资源。
2. **容器启动命令硬编码**：`container_manager.py` 中 `launch_file` 和 `entrypoint_cmd` 写死为固定路径，版本配置中的 `launch_args_template` 未注入。
3. **容器就绪检测缺失**：学生点击"开始仿真"后直接打开仿真页，但容器内 gzweb（8080）和 rosbridge（9090）可能尚未就绪，导致白屏或连接失败。
4. **数据模型冗余与语义冲突**：`is_visible` 与 `publish_status` 语义重叠；`ExperimentFileBundle.experiment_id` 约束了文件包只能绑定单个实验；`checksum` 字段无实际校验流程。
5. **实验/版本生命周期不完整**：缺少实验删除、实验状态切换、版本发布状态回退、版本删除等操作端点。
6. **教师端缺少资源管理 UI**：无实验文件管理页面、无环境配置管理页面，教师只能手动填写 ID 关联文件包。

### 1.2 目标结果

1. 教师可通过 UI 上传/管理实验文件包，通过编辑器管理环境文件和启动脚本（脚本以文件形式存储在环境包根目录）。
2. 容器启动时从版本配置动态读取 launch 路径和参数，不再硬编码；系统通过常驻启动脚本自动启动 rosbridge 和 gzweb，端口由容器启动时动态注入。
3. 仿真页打开前确保 gzweb 和 rosbridge 端口就绪，等待期间分阶段显示进度。
4. 数据模型消除冗余，文件包与实验解耦，支持跨实验复用。
5. 实验和版本具备完整生命周期管理（创建、编辑、发布、废弃、删除）。
6. 教师端路由重构为二级菜单，实验管理入口下辖列表、详情、文件、环境四个子页面。
7. Dry Run（试运行）复用学生端仿真页面，容器停止后立即自动清理。

### 1.3 成功指标

| 指标 | 目标值 |
|---|---|
| 文件包上传成功率（50MB 以内） | ≥ 99% |
| 容器就绪检测 P95 耗时（从容器 running 到双端口可用） | ≤ 20s |
| 就绪检测期间用户可见阶段提示率 | 100% |
| 容器启动命令来源为版本配置（非硬编码）覆盖率 | 100% |
| Dry Run 容器停止后立即自动清理率 | 100% |
| 教师端实验文件包上传→关联→学生分发全链路成功率 | ≥ 98% |

---

## 2) 范围定义

### 2.1 In Scope

**10-S1 模型修正与核心链路补全：**

| # | 工作项 | 说明 |
|---|---|---|
| S1-1 | 移除 `ExperimentVersion.is_visible` | 可见性统一由 `publish_status` + `Experiment.status` 决定 |
| S1-2 | 重构 `ExperimentFileBundle` | 移除 `experiment_id`、移除 `checksum`、新增 `name` 字段；文件包可跨实验复用 |
| S1-3 | 移除 `ExperimentVersion.startup_script_ref` | 由环境包根目录下 `startup.sh` 文件替代（创建环境包时自动生成，不可删除） |
| S1-4 | 新增 `ExperimentEnvBundle` 模型 | 环境文件包：容器目标目录、访问权限。启动脚本以文件形式存储在 `storage_root/startup.sh`，不存数据库 |
| S1-5 | `ExperimentVersion` 新增 `env_bundle_id` 外键 | 引用环境文件包 |
| S1-6 | 实现 `POST /teachers/file-bundles/upload` | 文件包上传端点（支持任意文件，上传后不自动解压；前端文件树组件已有解压功能） |
| S1-7 | 修复 `container_manager.create_container()` | 从版本配置读取 `launch_args_template`、教师启动脚本注入 |
| S1-7b | 新增常驻系统启动脚本 | 容器固定挂载一个系统级 entrypoint 脚本，负责启动 rosbridge 和 gzweb；容器启动时将宿主机映射端口以环境变量注入 |
| S1-8 | 容器就绪检测 | 在 HEALTH_CHECKING 阶段检测 gzweb 和 rosbridge 端口可用性 |
| S1-9 | 实验状态切换与删除 | `PATCH /experiments/{id}/status`、`DELETE /experiments/{id}` |
| S1-10 | 版本发布状态管理与删除 | `PATCH /versions/{vid}/publish-status`、`DELETE /versions/{vid}`（仅 draft） |
| S1-11 | 版本创建后端验证 | `POST /versions/{vid}/validate`：检查镜像、文件包、环境包是否存在 |
| S1-12 | 学生端可见性过滤 | 学生仅可见 `Experiment.status=active` 且 `publish_status=published` 的版本 |

**10-S2 教师资源管理页面：**

| # | 工作项 | 说明 |
|---|---|---|
| S2-1 | 教师端路由重构 | 实验管理改为二级菜单：实验列表、实验详情、实验文件、实验环境 |
| S2-2 | 实验文件管理页 | 左侧文件包列表（单击选中/双击进入文件树，含返回按钮）+ 右侧 Monaco 编辑器；文件操作复用现有文件树统一函数 |
| S2-3 | 实验环境管理页 | 左侧环境包列表（双击进入文件树）+ 基本设置（可拖拽调整占比）；右侧 Monaco 编辑器可打开任意文件；Dry Run 复用学生仿真页面，容器停止后即清理 |

### 2.2 Out of Scope

| 非本期项 | 不做原因 |
|---|---|
| 文件包版本历史（Git-like） | 过度工程化，当前教师直接覆盖上传即可满足需求 |
| 启动脚本沙箱执行 | 教师角色视为受信任用户，不做脚本审计 |
| 多租户资源配额 | 单集群教学场景，先保证功能可用 |
| 自动评测联动实验版本 | 评测域契约尚未冻结 |
| 容器快照预热 | 已拆至第10.1期独立文档 |
| 文件包大文件分片上传 | 当前教学场景文件包 ≤ 200MB，单次上传足够 |
| 实验模板市场（跨教师共享） | 功能边界过大，列入长期路线图 |

---

## 3) 前提挑战与方案比选

### 3.1 挑战 A：文件包与实验的关系模型

**现状**：`ExperimentFileBundle.experiment_id` 将文件包绑死到单个实验，不可跨实验复用。

**方案 A1（最小可行，本期采用）**：移除 `experiment_id`，文件包作为独立实体。通过 `ExperimentVersion.file_bundle_id` 建立多对一引用。

- **优点**：文件包可跨实验版本复用；模型简洁；删除实验不级联删除文件包。
- **风险**：孤儿文件包需定期清理。
- **迁移策略**：现有 bundle 保留数据，`experiment_id` 列标记 deprecated 后在下一次 DDL 变更中物理删除。

**方案 A2（长期最优）**：引入独立的 AssetLibrary 域，文件包、环境包统一管理。

- **优点**：最优架构，支持版本控制和权限细分。
- **风险**：引入新的聚合根和领域边界，改造面过大。
- **放弃原因**：超出本期范围，列入 Deferred。

**决策**：采用 A1。文件包独立化 + 外键引用。

### 3.2 挑战 B：容器启动命令注入方式

**现状**：`container_manager.py` 硬编码 `launch_file` 和 `entrypoint_cmd`。

**方案 B1（本期采用）**：[`create_container()`](edubot-twin-server/app/core/container_manager.py:131) 新增 `launch_args`、`startup_script_path` 等参数，但容器最终入口必须收敛为**统一前台守护入口**。该入口负责拉起教师 [`startup.sh`](docs/第10期/SDD-第10期补充：实验管理增强与资源管理体系.md:503)、rosbridge、gzweb，并定义任一关键进程退出时的失败语义和清理动作。

- **优点**：保留最小 diff，同时避免容器 running 但关键服务半故障的静默失败。
- **风险**：入口脚本职责更集中，需要把日志和退出码语义一次定义清楚。

**方案 B2**：引入 ContainerSpec 配置对象，将所有容器参数封装为结构化对象。

- **优点**：可扩展性更好。
- **风险**：需重构所有调用方。
- **放弃原因**：调用方少（仅 `simulation.py`），当前无需此抽象层。

**决策**：采用 B1。扩展函数参数，教师为受信任角色，launch_args 直接注入为环境变量。

**补充：统一前台守护入口（System Entrypoint）**

除教师自定义启动脚本外，每个容器还挂载一个**系统级前台守护入口** [`system_entrypoint.sh`](docs/第10期/SDD-第10期补充：实验管理增强与资源管理体系.md:859)。它不是“再起一个后台脚本”，而是容器唯一前台入口，负责统一拉起并监管：

- 教师自定义 [`startup.sh`](docs/第10期/SDD-第10期补充：实验管理增强与资源管理体系.md:503)
- `rosbridge_server`
- `gzweb`

容器启动时通过环境变量注入：

- `ROSBRIDGE_PORT` / `GZWEB_PORT`：宿主机映射端口 → 注入到统一前台守护入口
- `LAUNCH_ARGS`：版本配置中的 `launch_args_template` 格式化后的 roslaunch 参数字符串 → 注入到教师自定义脚本

执行语义：

1. 统一前台守护入口启动教师 [`startup.sh`](docs/第10期/SDD-第10期补充：实验管理增强与资源管理体系.md:503)，用于 source ROS 环境、拉起仿真节点。
2. 同一入口继续启动 `rosbridge_server` 与 `gzweb`。
3. 任一关键进程退出时，统一前台守护入口必须让容器进入失败态，并把错误暴露给上层任务流和清理路径。

参考 `/home/ubuntu20/gzweb/dev_entrypoint.sh` 的模式，但不接受“教师脚本后台运行，系统脚本再各自后台拉服务”的松耦合实现。

### 3.3 挑战 C：容器就绪检测策略

**方案 C1（本期采用）**：宿主机侧 TCP 端口探测，轮询 host-mapped 端口直到连接成功。

- **优点**：简单可靠，不依赖容器内工具。
- **策略**：每 2s 探测一次，超时 60s，分别检测 gzweb 和 rosbridge。

**方案 C2**：容器内健康检查脚本 + Docker HEALTHCHECK。

- **优点**：更精确（可检测应用层就绪而非仅端口监听）。
- **风险**：需修改镜像 Dockerfile，且 Docker HEALTHCHECK 间隔粒度有限。
- **放弃原因**：需修改镜像，影响面过大。

**决策**：采用 C1。宿主机 TCP 探测 + 超时兜底。

---

## 4) 现有资产复用

### 4.1 前端复用资产

| 资产 | 路径 | 复用方式 |
|---|---|---|
| MonacoEditor 组件 | `edubot-twin-web/src/components/Monaco/MonacoEditor.vue` | 教师文件编辑器、启动脚本编辑器直接复用 |
| 学生文件管理页 | `edubot-twin-web/src/views/Student/FileManager.vue` | 教师文件/环境管理页复用其文件树 + 上传 + 编辑交互模式 |
| 仿真工作台 WorkspacePanel | `edubot-twin-web/src/views/Simulation/panels/WorkspacePanel/` | 复用文件树组件和文件操作功能；抽取统一 `useFileOperations` composable |
| 仿真页面 | `edubot-twin-web/src/views/Simulation/Simulation.vue` | Dry Run 复用学生仿真工作台，教师可完整体验仿真环境 |
| 实验详情页 | `edubot-twin-web/src/views/Teacher/Experiments/ExperimentDetail.vue` | 保留版本列表+配置编辑区结构，移除 `is_visible`、`startup_script_ref` 字段 |
| 实验列表页 | `edubot-twin-web/src/views/Teacher/Experiments/Experiments.vue` | 保留列表+搜索+创建交互，新增状态切换和删除操作 |
| 教师端路由骨架 | `edubot-twin-web/src/router/index.ts` `/teacher` 节点 | 重构 `experiments` 为 `getParentLayout()` 二级菜单 |
| 学生首页 | `edubot-twin-web/src/views/Student/Home.vue` | 增强 loading 提示，增加就绪检测阶段展示 |

### 4.2 后端复用资产

| 资产 | 路径 | 复用方式 |
|---|---|---|
| 学生文件 API | `app/api/v1/endpoints/student/files.py` | 教师文件包文件操作复用路径安全校验、上传/读写逻辑 |
| 容器编排核心 | `app/core/container_manager.py` | 扩展 `create_container()` 参数签名 |
| 端口分配器 | `app/core/port_allocator.py` | Dry Run 容器复用端口分配逻辑 |
| 仿真任务 CRUD | `app/crud/simulation_task.py` | 就绪检测阶段复用任务状态记录 |
| 路径安全策略 | `app/core/path_policy.py` | 文件包存储路径校验复用 |
| ExperimentFileBundle 模型 | `app/models/experiment.py` | 结构化改造，保留表名和主键 |

---

## 5) 核心系统交互图

### 5.1 时序图：教师上传文件包并关联版本

```mermaid
sequenceDiagram
  autonumber
  participant T as 教师
  participant FE as Teacher/Files页
  participant BE as Teacher API
  participant FS as 文件系统

  T->>FE: 新建文件包(name)
  FE->>BE: POST /teachers/file-bundles {name}
  BE->>FS: 创建 /data/file_bundles/{bundle_id}/
  BE-->>FE: 201 {bundle_id, name}
  FE-->>T: 文件包列表刷新

  T->>FE: 选中文件包, 上传文件
  FE->>BE: POST /teachers/file-bundles/{id}/files/upload (multipart)
  BE->>FS: 保存文件到 /data/file_bundles/{bundle_id}/ (不自动解压)
  BE->>BE: 扫描目录生成 file_manifest
  BE-->>FE: 200 {file_count, total_size}
  FE-->>T: 文件树刷新显示 (压缩包文件可在文件树中手动解压)

  T->>FE: 切换到实验详情页, 填写 file_bundle_id
  FE->>BE: PUT /versions/{vid} {file_bundle_id: bundle_id}
  BE-->>FE: 200 版本更新成功
```

### 5.2 时序图：容器就绪检测与分阶段进度

```mermaid
sequenceDiagram
  autonumber
  participant S as 学生
  participant FE as Student/Home
  participant BE as Student API
  participant CM as ContainerManager
  participant Docker as Docker容器

  S->>FE: 点击开始仿真
  FE->>BE: POST /simulation/start {version_id}
  BE-->>FE: 202 {task_id}

  FE->>FE: 显示 "正在准备配置..."
  loop 轮询任务状态
    FE->>BE: GET /tasks/{task_id}
    BE-->>FE: {current_stage, stage_statuses}

    alt PREPARING_CONFIG
      FE->>FE: 显示 "正在准备配置..."
    else STOPPING_OLD_CONTAINER
      FE->>FE: 显示 "正在清理旧环境..."
    else CREATING_NEW_CONTAINER
      FE->>FE: 显示 "正在创建仿真容器..."
    else CHECKING_GZWEB
      FE->>FE: 显示 "等待 Gazebo 仿真引擎启动..."
    else CHECKING_ROSBRIDGE
      FE->>FE: 显示 "等待 ROS 通信桥启动..."
    else SUCCEEDED
      FE->>FE: 显示 "仿真环境就绪！"
      FE->>S: 打开仿真页面
    else FAILED
      FE->>S: 显示错误原因 + 重试按钮
    end
  end
```

### 5.3 流程图：container_manager 启动命令构建

```mermaid
flowchart TD
  A[接收版本配置参数] --> B{env_bundle 存在?}
  B -->|是| C[读取 env_bundle storage_root 下的 startup.sh]
  B -->|否| D[使用默认 entrypoint]
  C --> E{launch_args_template 非空?}
  E -->|是| G["格式化为 LAUNCH_ARGS 环境变量"]
  E -->|否| G2[LAUNCH_ARGS 为空]
  G --> H[挂载 startup.sh 到容器 /tmp/startup.sh]
  G2 --> H
  D --> H2[使用默认 entrypoint_cmd]
  H --> M["挂载系统常驻启动脚本 system_entrypoint.sh"]
  H2 --> M
  M --> M2["设置环境变量 ROSBRIDGE_PORT / GZWEB_PORT / LAUNCH_ARGS"]
  M2 --> N[创建并启动容器]
  N --> O[返回 container_id]
```

**执行顺序说明**：容器启动后的 entrypoint 执行链为：
1. 教师自定义 `startup.sh`（source 环境、通过 `$LAUNCH_ARGS` 启动 roslaunch 等）
2. 系统常驻 `system_entrypoint.sh`（读取 `$ROSBRIDGE_PORT`、`$GZWEB_PORT` 环境变量，启动 rosbridge_server 和 gzweb）

**launch_args 注入方式**：

`launch_args_template` 中的参数（如 `{"robot_model": "turtlebot3", "world": "maze"}`）直接格式化为 roslaunch 参数字符串并注入为容器环境变量 `LAUNCH_ARGS`：

```python
# 后端注入逻辑
launch_args = {"robot_model": "turtlebot3", "world": "maze"}
# 格式化为 roslaunch 参数: "robot_model:=turtlebot3 world:=maze"
launch_args_str = " ".join(f"{k}:={v}" for k, v in launch_args.items())

environment = {
    "ROSBRIDGE_PORT": str(ros_port),
    "GZWEB_PORT": str(gz_port),
    "LAUNCH_ARGS": launch_args_str,  # 教师 startup.sh 中通过 $LAUNCH_ARGS 引用
}
```

教师在 `startup.sh` 中这样使用：
```bash
# $LAUNCH_ARGS 由平台自动注入版本配置中的 launch_args_template 参数
roslaunch bingda_tutorials simulation_robot.launch $LAUNCH_ARGS &
```

### 5.4 状态机图：实验状态

```mermaid
stateDiagram-v2
  [*] --> draft : 创建实验
  draft --> active : 激活 (PATCH status=active)
  active --> draft : 取消激活 (PATCH status=draft)
  active --> archived : 归档 (PATCH status=archived)
  archived --> active : 恢复 (PATCH status=active)
  draft --> [*] : 删除 (DELETE，仅无版本时允许)
  note right of active : 学生可见条件：\nstatus=active AND\n至少有一个 published 版本
```

### 5.5 状态机图：版本发布状态

```mermaid
stateDiagram-v2
  [*] --> draft : 创建版本
  draft --> published : 发布 (POST publish)
  published --> deprecated : 废弃 (PATCH publish_status=deprecated)
  deprecated --> published : 重新发布 (PATCH publish_status=published)
  draft --> [*] : 删除 (DELETE，仅 draft 允许)
  note right of published : 学生可见条件：\npublish_status=published AND\n父实验 status=active
  note right of deprecated : 学生不可见\n已使用此版本的容器\n心跳感知到 deprecated 后\n展示橙色 banner
```

### 5.6 流程图：Dry Run 试运行

```mermaid
flowchart TD
  A[教师点击试运行] --> B[前端锁定按钮, 显示 '正在启动测试容器...']
  B --> C["POST /teachers/env-bundles/{id}/dry-run"]
  C --> D[后端分配临时端口]
  D --> E[创建测试容器, 挂载环境文件, 注入启动脚本+常驻脚本]
  E --> F[等待就绪检测]
  F --> G{gzweb + rosbridge 就绪?}
  G -->|是, ≤60s| H["返回 200 {container_id, simulation_url}"]
  H --> I["前端跳转到学生仿真页面（复用 Simulation 工作台）"]
  I --> J[教师在仿真页中验证环境]
  J --> K["教师点击'结束试运行'或关闭仿真页"]
  K --> L["DELETE /teachers/dry-run/{container_id}"]
  L --> M[容器停止后立即清理, 释放端口]
  G -->|否, >60s| N[返回超时错误 + 容器日志摘要]
  N --> O[自动清理测试容器]
  O --> P[教师根据日志修正配置]
```

**Dry Run 与正式仿真的区别**：
- Dry Run 复用学生端仿真工作台（`Simulation.vue`），教师可体验与学生完全一致的仿真环境。
- Dry Run 容器带有 `edubot.type: dry-run` 标签，**停止后立即自动清理**（不保留 30 分钟）。
- 仿真页顶部显示橙色提示条："试运行模式 — 该容器将在结束后立即清理"。

---

## 6) API 契约表

### 6.0 API 路径迁移说明

第10期主链路 SDD 定义了 `POST /api/v1/teachers/experiment-files/upload` 和 `POST /api/v1/teachers/experiment-files/{id}/validate` 两个端点，本期将其废弃并替换为更完整的文件包管理 API 体系：

| 原端点（废弃） | 新端点 | 变更原因 |
|---|---|---|
| `POST /teachers/experiment-files/upload` | `POST /teachers/file-bundles` + `POST /teachers/file-bundles/{id}/files/upload` | 文件包创建与文件上传拆分为两步；文件包不再绑定 experiment_id |
| `POST /teachers/experiment-files/{id}/validate` | 由 `validate_status` 字段自动维护 | 文件包上传时自动校验，无需独立端点 |

### 6.1 文件包管理 API（10-S1 新增）

| Endpoint | Method | 鉴权 | Request | Response | 状态码 |
|---|---|---|---|---|---|
| `/api/v1/teachers/file-bundles` | POST | Bearer(teacher) | `{name: str}` | `{bundle_id, name, storage_root, created_at}` | 201/400 |
| `/api/v1/teachers/file-bundles` | GET | Bearer(teacher) | `page, page_size, keyword?` | `{total, list: [{bundle_id, name, file_count, total_size, created_at}]}` | 200 |
| `/api/v1/teachers/file-bundles/{id}` | GET | Bearer(teacher) | 路径参数 | `{bundle_id, name, file_count, total_size, file_manifest, created_at}` | 200/404 |
| `/api/v1/teachers/file-bundles/{id}` | PATCH | Bearer(teacher) | `{name: str}` | `{bundle_id, name, affected_versions: [{version_id, experiment_name, version_name}]}` | 200/404/409 |
| `/api/v1/teachers/file-bundles/{id}` | DELETE | Bearer(teacher) | 路径参数 | `204 No Content` | 204/404/409(有版本引用时) |
| `/api/v1/teachers/file-bundles/{id}/files/upload` | POST | Bearer(teacher) | `multipart(file)` | `{file_count, total_size_bytes}` | 200/400/413 |
| `/api/v1/teachers/file-bundles/{id}/files` | GET | Bearer(teacher) | `path?: str(默认根)` | `{items: [{name, type: file\|dir, size?, modified_at}]}` | 200/404 |
| `/api/v1/teachers/file-bundles/{id}/files/read` | GET | Bearer(teacher) | `path: str` | `{content: str, encoding: str}` | 200/400/404 |
| `/api/v1/teachers/file-bundles/{id}/files/save` | POST | Bearer(teacher) | `{path: str, content: str}` | `200 OK` | 200/400/404 |
| `/api/v1/teachers/file-bundles/{id}/files/delete` | DELETE | Bearer(teacher) | `path: str` | `204 No Content` | 204/400/404 |

### 6.2 环境包管理 API（10-S1 新增）

| Endpoint | Method | 鉴权 | Request | Response | 状态码 |
|---|---|---|---|---|---|
| `/api/v1/teachers/env-bundles` | POST | Bearer(teacher) | `{name: str, container_target_dir: str, access_level: str}` | `{env_bundle_id, name, created_at}` | 201/400 |
| `/api/v1/teachers/env-bundles` | GET | Bearer(teacher) | `page, page_size, keyword?` | `{total, list: [{env_bundle_id, name, container_target_dir, created_at}]}` | 200 |
| `/api/v1/teachers/env-bundles/{id}` | GET | Bearer(teacher) | 路径参数 | `{env_bundle_id, name, container_target_dir, access_level, file_manifest, created_at}` | 200/404 |
| `/api/v1/teachers/env-bundles/{id}` | PATCH | Bearer(teacher) | `{name?, container_target_dir?, access_level?}` | `{env_bundle_id, name, updated_at}` | 200/400/404 |
| `/api/v1/teachers/env-bundles/{id}` | DELETE | Bearer(teacher) | 路径参数 | `204 No Content` | 204/404/409(有版本引用时) |
| `/api/v1/teachers/env-bundles/{id}/files/upload` | POST | Bearer(teacher) | `multipart(file)` | `{file_count, total_size_bytes}` | 200/400/413 |
| `/api/v1/teachers/env-bundles/{id}/files` | GET | Bearer(teacher) | `path?: str` | `{items: [{name, type, size?, modified_at}]}` | 200/404 |
| `/api/v1/teachers/env-bundles/{id}/files/read` | GET | Bearer(teacher) | `path: str` | `{content: str, encoding: str}` | 200/400/404 |
| `/api/v1/teachers/env-bundles/{id}/files/save` | POST | Bearer(teacher) | `{path: str, content: str}` | `200 OK` | 200/400/404 |
| `/api/v1/teachers/env-bundles/{id}/files/delete` | DELETE | Bearer(teacher) | `path: str` | `204 No Content`（`startup.sh` 禁止删除，返回 403） | 204/400/403/404 |
| `/api/v1/teachers/env-bundles/{id}/dry-run` | POST | Bearer(teacher) | `{version_id: int}` | `{container_id: str, simulation_url: str}` | 200/400/404/503 |
| `/api/v1/teachers/dry-run/{container_id}` | DELETE | Bearer(teacher) | 路径参数 | `204 No Content`（容器停止后立即清理） | 204/404 |

**环境包创建行为说明**：
- 创建环境包时，后端自动在 `storage_root` 下生成 `startup.sh` 文件，包含模板内容和注释提醒（见 §15.5）。
- `startup.sh` 通过文件读写 API 编辑，但**禁止通过 delete API 删除**（后端返回403）。
- 启动脚本内容不存储在数据库中，始终从文件系统读取。

### 6.3 实验/版本生命周期 API（10-S1 新增/修改）

| Endpoint | Method | 鉴权 | Request | Response | 状态码 |
|---|---|---|---|---|---|
| `/api/v1/teachers/experiments/{id}` | DELETE | Bearer(teacher) | 路径参数 | `204 No Content` | 204/404/409(有非 draft 版本时) |
| `/api/v1/teachers/experiments/{id}/status` | PATCH | Bearer(teacher) | `{status: "draft"\|"active"\|"archived"}` | `{experiment_id, status, updated_at}` | 200/400/404 |
| `/api/v1/teachers/experiments/{eid}/versions/{vid}` | DELETE | Bearer(teacher) | 路径参数 | `204 No Content` | 204/404/409(非 draft 不可删) |
| `/api/v1/teachers/experiments/{eid}/versions/{vid}/publish-status` | PATCH | Bearer(teacher) | `{publish_status: "published"\|"deprecated", publish_note?: str}` | `{version_id, publish_status, updated_at}` | 200/400/404/409；当目标为 `published` 且存在 blocking issues 时返回 `409 VALIDATION_BLOCKING_ISSUE` |
| `/api/v1/teachers/experiments/{eid}/versions/{vid}/validate` | POST | Bearer(teacher) | 路径参数 | `{valid: bool, issues: [{field, code, severity, message}]}` | 200/404 |

### 6.4 学生端修改（10-S1）

| Endpoint | 修改说明 |
|---|---|
| `GET /students/experiments/available` | 过滤条件变更：`Experiment.status=active AND ExperimentVersion.publish_status=published`；移除 `is_visible` 条件 |
| `POST /students/simulation/start` | 同上过滤条件；HEALTH_CHECKING 阶段细分为 `CHECKING_GZWEB` 和 `CHECKING_ROSBRIDGE` |

### 6.5 错误语义映射（新增）

| 错误码 | 语义 | 前端动作 |
|---|---|---|
| `BUNDLE_NAME_CONFLICT` | 文件包名称已存在 | 提示重命名 |
| `BUNDLE_IN_USE` | 文件包/环境包被版本引用，不可删除 | 提示先解除引用 |
| `EXPERIMENT_HAS_NON_DRAFT_VERSIONS` | 实验下有非 draft 版本，不可删除 | 提示先废弃或删除所有版本 |
| `VERSION_NOT_DRAFT` | 非 draft 版本不可删除 | 提示仅 draft 可删 |
| `INVALID_STATUS_TRANSITION` | 非法状态转换 | 提示当前状态不允许此操作 |
| `GZWEB_NOT_READY` | gzweb 端口超时未就绪 | 显示具体阶段 + 重试 |
| `ROSBRIDGE_NOT_READY` | rosbridge 端口超时未就绪 | 显示具体阶段 + 重试 |
| `DRY_RUN_RESOURCE_EXHAUSTED` | Dry Run 容器配额已满（上限 3） | 提示清理已有测试容器 |
| `STARTUP_SCRIPT_PROTECTED` | 启动脚本 startup.sh 不可删除 | 提示该文件受保护 |
| `UPLOAD_SIZE_EXCEEDED` | 上传文件超过 200MB 限制 | 提示减小文件包体积 |
| `FILE_UPLOAD_CONFLICT` | 同一路径重复上传且客户端声明禁止覆盖 | 提示选择覆盖或更名 |
| `FILE_SAVE_CONFLICT` | 保存时文件已被其他操作更新 | 提示刷新后重试，避免静默覆盖 |
| `VALIDATION_FAILED` | 版本配置验证失败 | 展示结构化 issues 列表 |
| `VALIDATION_BLOCKING_ISSUE` | 验证存在阻断项 | 阻止发布并高亮问题字段；发布接口必须复用 validate 的 blocking 结果 |

---

## 7) 数据字典表

### 7.1 ExperimentVersion（字段变更）

| 字段名 | 变更类型 | 数据类型 | 必填 | 默认值 | 业务说明 |
|---|---|---|---|---|---|
| ~~is_visible~~ | **删除** | - | - | - | 语义与 `publish_status` + `Experiment.status` 重叠 |
| ~~startup_script_ref~~ | **删除** | - | - | - | 由 `ExperimentEnvBundle.startup_script` 替代 |
| env_bundle_id | **新增** | int (nullable) | 否 | null | 关联环境文件包 ID |

**学生可见性规则**（替代原 `is_visible`）：
```
Experiment.status = 'active'
AND ExperimentVersion.publish_status = 'published'
```

### 7.2 ExperimentFileBundle（字段变更）

| 字段名 | 变更类型 | 数据类型 | 必填 | 默认值 | 业务说明 |
|---|---|---|---|---|---|
| ~~experiment_id~~ | **删除** | - | - | - | 文件包独立于实验，通过版本外键引用 |
| ~~checksum~~ | **删除** | - | - | - | 无实际校验流程，移除 |
| name | **新增** | string(128) | 是 | - | 文件包显示名称（唯一约束 per created_by） |
| storage_root | **新增** | string(512) | 是 | `/data/file_bundles/{id}` | 服务器存储根目录（自动生成） |
| file_count | **新增** | int | 是 | 0 | 文件数量（上传时自动计算） |
| total_size_bytes | **新增** | bigint | 是 | 0 | 文件包总大小（字节） |

**保留字段行为变更**：

| 字段名 | 变更说明 |
|---|---|
| `file_manifest` | 保留 JSON 数组。上传文件后由后端扫描 `storage_root` 目录自动重建 manifest，不再由前端传入。元素格式不变：`{relative_path, chmod_mode}` |
| `validate_status` | 保留枚举。上传后自动设为 `valid`（后端扫描通过即有效）；`storage_root` 目录为空时设为 `invalid`。移除原有的手动触发校验端点 |

### 7.3 ExperimentEnvBundle（新增实体）

| 字段名 | 数据类型 | 必填 | 默认值 | 业务说明 |
|---|---|---|---|---|
| id | int | 是 | 自增 | 主键 |
| name | string(128) | 是 | - | 环境包名称 |
| storage_root | string(512) | 是 | `/data/env_bundles/{id}` | 环境文件存储根目录 |
| container_target_dir | string(255) | 是 | `/home/ubuntu20/catkin_ws` | 环境文件在容器中的挂载目标目录 |
| access_level | enum(readonly/readwrite/hidden) | 是 | readonly | 学生对环境文件的访问权限 |
| file_count | int | 是 | 0 | 环境文件数量 |
| total_size_bytes | bigint | 是 | 0 | 总大小（字节） |
| created_by | int | 是 | - | 创建教师 ID |
| created_at | datetime | 是 | now | 创建时间 |
| updated_at | datetime | 是 | now | 更新时间 |

**启动脚本存储策略**（原 `startup_script` 字段已移除）：
- 启动脚本以文件形式存储在 `{storage_root}/startup.sh`，不存入数据库。
- 创建环境包时后端自动生成 `startup.sh`，包含模板内容和注释提示。
- `startup.sh` 通过通用文件读写 API（`files/read`、`files/save`）进行编辑。
- **后端禁止通过 `files/delete` API 删除 `startup.sh`**，返回 403。
- 容器启动时读取 `{storage_root}/startup.sh` 文件内容，挂载到容器 `/tmp/startup.sh` 执行。

### 7.4 SimulationTaskStage（枚举扩展）

| 新增枚举值 | 业务说明 |
|---|---|
| `CHECKING_GZWEB` | 等待 gzweb 端口（容器 8080 / 宿主机 gz_port）就绪 |
| `CHECKING_ROSBRIDGE` | 等待 rosbridge 端口（容器 9090 / 宿主机 ros_port）就绪 |

**阶段顺序更新**：
```
PREPARING_CONFIG → STOPPING_OLD_CONTAINER → CREATING_NEW_CONTAINER
→ CHECKING_GZWEB → CHECKING_ROSBRIDGE → SUCCEEDED/FAILED
```

原 `HEALTH_CHECKING` 阶段拆分为 `CHECKING_GZWEB` + `CHECKING_ROSBRIDGE`，粒度更细，前端可分阶段展示。

### 7.5 DryRunContainer（内存管理，不持久化）

| 字段 | 类型 | 说明 |
|---|---|---|
| container_id | str | Docker 容器 short_id |
| teacher_id | int | 创建教师 ID |
| gz_port | int | 宿主机 gzweb 端口 |
| ros_port | int | 宿主机 rosbridge 端口 |
| created_at | datetime | 创建时间 |

Dry Run 容器不写数据库，仅在进程内存中维护（`dict[str, DryRunContainer]`）。
**清理策略**：容器停止后立即自动清理（通过 `DELETE /teachers/dry-run/{container_id}` 触发，或通过 Docker event 监听容器退出事件自动清理）。Dry Run 页面直接复用学生仿真页既有心跳机制；前端在关闭页签、路由离开、刷新页面时执行 best-effort 清理请求，服务端继续以容器退出事件兜底。不再使用 30 分钟过期机制，但保留最大并发限制（每位教师最多 3 个 Dry Run 容器）。

---

## 8) 安全与边界约束

| 风险点 | 约束要求 | 控制策略 | 验证方式 |
|---|---|---|---|
| 文件包路径穿越 | 上传/读取/保存操作的路径必须在 `storage_root` 下 | `os.path.normpath` + 前缀校验；禁止 `..` | 路径穿越用例 |
| 启动脚本注入 | 教师视为受信任用户，不做内容审计 | 脚本以文件方式挂载，不经 shell 变量展开 | - |
| Dry Run 资源泄漏 | 每位教师最多同时运行 3 个 Dry Run 容器 | 内存计数器 + 容器停止后立即清理 + Docker event 监听兜底 | 并发创建用例 |
| startup.sh 禁删 | 环境包 `startup.sh` 不可被删除 | 后端 `files/delete` API 对 `startup.sh` 路径返回 403 | 删除 startup.sh 用例 |
| 文件包删除越权 | 教师只能删除自己创建的文件包（admin 除外） | `created_by` 校验 | 越权删除用例 |
| 状态转换非法 | 实验/版本状态转换必须遵循状态机 | 后端校验当前状态 + 目标状态合法性 | 状态机全路径测试 |
| 实验删除约束 | 仅当所有版本均为 draft 或无版本时才允许删除 | 后端检查版本列表 | 含 published 版本时删除用例 |
| 版本删除约束 | 仅 draft 版本可删除 | 后端校验 `publish_status` | published 版本删除用例 |
| 重命名影响检测 | 文件包重命名时列出所有引用该文件包的版本 | 后端查询 `ExperimentVersion.file_bundle_id = bundle_id` | 重命名影响用例 |

---

## 9) 失败模式与恢复策略

| Codepath | 失败模式 | 用户可见 | 日志/指标 | 测试覆盖 | 恢复策略 |
|---|---|---|---|---|---|
| file-upload | 文件超过 200MB 限制 | 是（413） | 是 | 是 | 前端预校验 + 后端拒绝 |
| file-upload | 磁盘空间不足 | 是（503） | 是 | 是 | 告警运维扩容 |
| bundle-delete | 文件包被版本引用 | 是（409 BUNDLE_IN_USE） | 是 | 是 | 展示引用版本列表，引导先解除引用 |
| bundle-rename | 名称冲突 | 是（409） | 是 | 是 | 提示换名 |
| experiment-delete | 含非 draft 版本 | 是（409） | 是 | 是 | 提示先废弃/删除版本 |
| version-delete | 非 draft 状态 | 是（409） | 是 | 是 | 提示仅 draft 可删 |
| readiness-check | gzweb 端口 60s 超时 | 是（GZWEB_NOT_READY） | 是 | 是 | 重试按钮 + 容器日志提示 |
| readiness-check | rosbridge 端口 60s 超时 | 是（ROSBRIDGE_NOT_READY） | 是 | 是 | 重试按钮 + 容器日志提示 |
| dry-run | 配额已满（3个） | 是（DRY_RUN_RESOURCE_EXHAUSTED） | 是 | 是 | 提示清理已有测试容器 |
| dry-run | 容器异常退出 | 否（自动清理） | 是 | 是 | Docker event 监听到容器退出后立即清理内存记录和端口 |
| dry-run | 容器启动失败 | 是（容器日志摘要） | 是 | 是 | 自动清理 + 提示修正配置 |
| version-validate | 镜像不存在 | 是（issues 列表） | 是 | 是 | 返回 `code=missing_image,severity=blocking`，教师更换镜像名 |
| version-validate | file_bundle 不存在或为空 | 是（issues 列表） | 是 | 是 | 返回 `code=missing_bundle/empty_bundle,severity=blocking`，教师重新关联文件包 |
| version-validate | env_bundle 不存在 | 是（issues 列表） | 是 | 是 | 返回 `code=missing_env_bundle,severity=blocking`，教师关联环境包 |
| version-validate | startup.sh 缺失 | 是（issues 列表） | 是 | 是 | 返回 `code=missing_startup_script,severity=blocking`，教师修复环境包 |
| file-save | 保存时文件已被其他操作更新 | 是（409 FILE_SAVE_CONFLICT） | 是 | 是 | 返回最新 `modified_at`，前端提示刷新后重试 |

---

## 10) 可观测性要求

### 10.1 关键日志字段（新增）

| 字段 | 说明 |
|---|---|
| `bundle_id` | 文件包/环境包 ID |
| `bundle_type` | `file` 或 `env` |
| `upload_size_bytes` | 上传文件大小 |
| `file_count` | 文件数量 |
| `dry_run_container_id` | Dry Run 容器 ID |
| `readiness_stage` | `gzweb` 或 `rosbridge` |
| `readiness_elapsed_ms` | 就绪检测耗时 |

### 10.2 核心指标（新增）

1. `bundle_upload_duration_ms`（P50/P95）— 文件包上传耗时。
2. `bundle_upload_size_bytes`（P50/P95）— 文件包大小分布。
3. `readiness_check_duration_ms{stage}`（P50/P95）— gzweb / rosbridge 各自就绪耗时。
4. `readiness_check_timeout_rate` — 就绪超时率。
5. `dry_run_success_rate` — Dry Run 成功率。
6. `dry_run_active_count` — 当前活跃 Dry Run 容器数。

### 10.3 告警建议

1. `readiness_check_timeout_rate > 10%`（5min 窗口）触发告警。
2. `dry_run_active_count >= 3`（单教师）触发通知。
3. `bundle_upload_size_bytes > 150MB` 记录 warning 日志。

---

## 11) 测试与验收

### 11.1 测试覆盖地图

**强约束**：所有关键失败模式测试必须同时断言四项结果：
1. 错误码正确。
2. 日志字段完整（至少含 `bundle_id` / `version_id` / `dry_run_container_id` / `readiness_stage` 中的相关字段）。
3. 前端提示文案与错误语义一致。
4. 清理动作正确完成（容器、端口、临时状态无泄漏）。

| 流程/分支 | 类型 | 用例要点 | 通过标准 |
|---|---|---|---|
| 文件包 CRUD 全流程 | 集成 | 创建→上传→列表→详情→重命名→删除 | 全操作成功，数据一致 |
| 文件包上传文件 | 集成 | 上传文件，压缩包不自动解压 | 压缩包文件直接保存，文件树中可手动解压 |
| 文件包上传单文件 | 集成 | 上传单个 .py 文件 | 文件保存到正确路径 |
| 文件保存冲突 | 集成 | 读取后由第二会话先保存，再由第一会话提交 | 返回 `409 FILE_SAVE_CONFLICT`，日志和前端提示一致，原文件未被静默覆盖 |
| 文件包路径穿越 | 安全 | 读取/保存路径含 `../` | 返回 400，无越界操作 |
| 文件包被引用时删除 | 业务 | 删除被版本引用的文件包 | 返回 409 BUNDLE_IN_USE |
| 文件包重命名影响检测 | 业务 | 重命名被 3 个版本引用的文件包 | 返回 affected_versions 含 3 条记录 |
| 环境包 CRUD 全流程 | 集成 | 创建→设置启动脚本→上传文件→删除 | 全操作成功 |
| 实验状态切换 | 集成 | draft→active→archived→active→draft | 每步状态正确转换 |
| 实验删除约束 | 业务 | 删除含 published 版本的实验 | 返回 409 |
| 版本删除约束 | 业务 | 删除 published 版本 | 返回 409 |
| 版本发布状态切换 | 集成 | draft→published→deprecated→published | 每步正确，发布日志同步写入 |
| 学生可见性过滤 | 集成 | 实验 status=draft 时查询 available | 返回空列表 |
| 学生可见性过滤 | 集成 | 版本 publish_status=deprecated 时查询 | 该版本不在列表中 |
| 就绪检测 Happy Path | 集成 | 容器创建后检测双端口 | CHECKING_GZWEB→CHECKING_ROSBRIDGE→SUCCEEDED |
| 就绪检测超时 | 集成 | 模拟端口不可达 | 60s 后 FAILED + GZWEB_NOT_READY，日志字段和容器清理动作齐全 |
| 版本验证 Happy Path | 集成 | 所有配置项正确 | `{valid: true, issues: []}` |
| 版本验证 — 镜像不存在 | 集成 | image_name 无效 | `{valid: false, issues: [{field: "image_name", code: "missing_image", severity: "blocking"}]}` |
| 版本验证 — startup.sh 缺失 | 集成 | 删除或重命名启动脚本后执行 validate | 返回 `missing_startup_script` 阻断项 |
| 发布硬拦截 | 集成 | validate 返回 blocking issue 后继续调用 publish-status=published | 返回 `409 VALIDATION_BLOCKING_ISSUE`，版本状态保持不变 |
| Dry Run 全流程 | 集成 | 创建→就绪→访问仿真页→结束清理 | 容器创建成功，复用仿真页面，停止后立即清理 |
| Dry Run 离开页面回收 | 集成 | 关闭页签/路由离开后触发学生页心跳终止 | 触发 best-effort 清理，请求失败时仍由容器退出事件兜底 |
| startup.sh 禁删 | 业务 | 尝试通过 files/delete 删除 startup.sh | 返回 403，文件仍存在 |
| startup.sh 自动创建 | 集成 | 创建环境包后检查文件系统 | storage_root 下存在 startup.sh 且包含模板内容 |
| Dry Run 配额限制 | 业务 | 同一教师创建第 4 个 | 返回 DRY_RUN_RESOURCE_EXHAUSTED |

### 11.2 功能验收（量化）

- [ ] 教师可通过 UI 完成文件包创建、上传、编辑、删除全流程，成功率 100%。
- [ ] 教师可创建环境包、编辑启动脚本（文件形式）、执行 Dry Run（复用仿真页面），成功率 ≥ 95%。
- [ ] 文件包上传支持压缩包和单文件上传（压缩包不自动解压，可在文件树中手动解压）。
- [ ] 学生端 `available` 接口严格按 `status=active + publish_status=published` 过滤，无例外。
- [ ] 容器启动命令 100% 从版本配置读取，不存在硬编码路径。
- [ ] 仿真页打开前 gzweb 和 rosbridge 均已通过端口检测，就绪率 ≥ 95%。

### 11.3 稳定性验收（量化）

- [ ] 50MB 文件包连续上传 50 次，成功率 ≥ 99%。
- [ ] 就绪检测 P95 耗时 ≤ 20s（从容器 running 到双端口可用）。
- [ ] Dry Run 容器停止后立即清理率 100%，无泄漏。

### 11.4 一致性验收

- [ ] `is_visible` 和 `startup_script_ref` 在前后端代码中零引用（已完全移除）。
- [ ] 文件包/环境包 API 命名风格统一（`file-bundles` / `env-bundles`）。
- [ ] 错误码字典与前端提示文案一一对应。

---

## 12) 实施分期与交付清单

### 12.1 第 10-S1 期交付内容

**文档交付**：
- 本 SDD 补充文档。

**后端交付**：

| 模块 | 交付内容 |
|---|---|
| `app/models/experiment.py` | 删除 `is_visible`、`startup_script_ref`、`experiment_id`(FileBundle)、`checksum`；新增 `env_bundle_id`、`name`(FileBundle)、`storage_root`、`file_count`、`total_size_bytes`；新增 `ExperimentEnvBundle` 模型（无 `startup_script` 字段，脚本存文件） |
| `app/schemas/experiment.py` | 同步更新所有 Schema；新增 FileBundleCreate/Response/ListItem、EnvBundleCreate/Response/ListItem、VersionValidateResponse |
| `app/crud/experiment.py` | 新增 bundle CRUD、环境包 CRUD、实验删除、状态切换、版本删除、版本发布状态切换、版本验证，并复用统一文件服务提供的文件读写能力 |
| `app/services/bundle_file_service.py` | 新建：统一文件服务 `BundleFileService`，集中处理 upload、list、read、save、delete、路径安全、冲突检测、保护路径 |
| `app/api/v1/endpoints/teacher/file_bundles.py` | 文件包管理 API 全部端点，仅做鉴权、资源查找和参数转换，实际文件操作委托 `BundleFileService` |
| `app/api/v1/endpoints/teacher/env_bundles.py` | 环境包管理 API 全部端点，仅做鉴权、资源查找和参数转换，实际文件操作委托 `BundleFileService` |
| `app/api/v1/endpoints/teacher/experiments.py` | 新增 DELETE、PATCH /status、DELETE /versions/{vid}、PATCH /publish-status、POST /validate |
| `app/api/v1/endpoints/student/simulation.py` | `_run_rebuild_task` 注入 launch 配置；健康检查拆分为 CHECKING_GZWEB + CHECKING_ROSBRIDGE |
| `app/api/v1/endpoints/student/experiments.py` | 可见性过滤条件修改 |
| `app/core/container_manager.py` | [`create_container()`](edubot-twin-server/app/core/container_manager.py:131) 新增 `launch_args`、`startup_script_path`、`env_volumes` 参数，并按“镜像/端口、启动配置、文件挂载、运行模式”四组在内部数据结构中分层实现 |
| `app/core/readiness_checker.py` | 新建：TCP 端口探测工具，支持 gzweb 和 rosbridge 分别检测 |
| `app/core/dry_run_manager.py` | 新建：Dry Run 容器生命周期管理（内存存储 + 停止即清理 + Docker event 监听兜底） |
| `app/core/system_entrypoint.py` | 新建：统一前台守护入口脚本管理，负责生成和挂载 [`system_entrypoint.sh`](docs/第10期/SDD-第10期补充：实验管理增强与资源管理体系.md:859) |
| `app/models/simulation_task.py` | `SimulationTaskStage` 枚举新增 `CHECKING_GZWEB`、`CHECKING_ROSBRIDGE` |
| `app/api/v1/endpoints/common/auth.py` | `get_user_routes()` 新增教师端二级路由路径 |
| `init_db.py` | 更新种子数据以适配新模型 |

**前端交付**（10-S1 范围内的修改）：

| 模块 | 交付内容 |
|---|---|
| `src/api/experiment/types.ts` | 移除 `is_visible`、`startup_script_ref`；新增 FileBundleXxx、EnvBundleXxx 类型 |
| `src/api/experiment/index.ts` | 新增文件包/环境包 API 函数 |
| `src/views/Teacher/Experiments/ExperimentDetail.vue` | 移除 `is_visible` 和 `startup_script_ref` 表单项；新增 `env_bundle_id` 选择；新增版本删除、发布状态切换操作按钮；新增保存后验证调用 |
| `src/views/Teacher/Experiments/Experiments.vue` | 新增实验状态切换和删除操作 |
| `src/views/Student/Home.vue` | 增强 loading 提示：分阶段显示（准备配置/清理旧环境/创建容器/等待 Gazebo/等待 ROS） |

**测试交付**：

| 测试文件 | 覆盖内容 |
|---|---|
| `tests/test_file_bundle_crud.py` | 文件包 CRUD 全路径 |
| `tests/test_file_bundle_upload.py` | 上传 |
| `tests/test_file_bundle_security.py` | 路径穿越、越权删除 |
| `tests/test_env_bundle_crud.py` | 环境包 CRUD 全路径 |
| `tests/test_experiment_lifecycle.py` | 实验状态切换、删除约束 |
| `tests/test_version_lifecycle.py` | 版本发布状态切换、删除约束 |
| `tests/test_container_launch_injection.py` | launch 参数注入为 LAUNCH_ARGS 环境变量 |
| `tests/test_readiness_checker.py` | 端口探测成功/超时 |
| `tests/test_version_validate.py` | 版本验证全路径 |
| `tests/test_student_visibility.py` | 学生可见性过滤（status + publish_status 组合） |

### 12.2 第 10-S2 期交付内容

**前端交付**：

| 模块 | 交付内容 |
|---|---|
| `src/router/index.ts` | `/teacher/experiments` 改为 `getParentLayout()` 二级菜单结构 |
| `src/views/Teacher/Experiments/ExperimentList.vue` | 从 `Experiments.vue` 重命名/重构，放入二级路由 |
| `src/views/Teacher/Experiments/ExperimentFiles.vue` | **新建**：实验文件管理页（左侧列表/文件树切换 + 右侧 Monaco 编辑器 + 右键菜单） |
| `src/views/Teacher/Experiments/ExperimentEnvs.vue` | **新建**：实验环境管理页（左侧列表/文件树+设置切换 + 右侧 Monaco 编辑器 + 右键菜单） |
| `src/composables/useFileOperations.ts` | **新建**：统一文件操作函数，适配学生端/教师文件包/教师环境包三种 API 后端地址 |

**后端交付**：

| 模块 | 交付内容 |
|---|---|
| `app/api/v1/endpoints/common/auth.py` | 教师路由列表更新 |

**测试交付**：

| 测试文件 | 覆盖内容 |
|---|---|
| `tests/e2e/test_teacher_file_management.py` | 文件管理页全流程（列表→双击进入→文件操作→右键菜单） |
| `tests/e2e/test_teacher_env_management.py` | 环境管理页全流程（含 Dry Run 复用仿真页面） |
| `tests/test_dry_run_lifecycle.py` | Dry Run 创建/就绪/复用仿真页/停止即清理/配额限制 |
| `tests/test_startup_script_protection.py` | startup.sh 自动创建/禁止删除/正常编辑保存 |

---

## 13) Deferred（后续阶段）

| 延后项 | 延后原因 | 触发条件 |
|---|---|---|
| AssetLibrary 统一资源域 | 本期文件包独立化已满足需求，统一资源域需更大重构 | 出现 3+ 种资源类型需统一管理、或 file/env bundle 出现重复治理逻辑时 |
| 文件包版本历史 | 教师直接覆盖上传满足当前需求 | 多教师协作编辑同一文件包产生冲突时 |
| 启动脚本审计与沙箱 | 教师角色受信任，无需审计 | 引入不受信助教角色时 |
| 大文件分片上传 | 200MB 上限足够教学场景 | 仿真数据集 > 500MB 成为常态时 |
| 实验模板市场 | 当前单校部署，无跨教师共享需求 | 多校/多课程部署时 |
| 文件分发超时机制 | 第10期 Eng Review 标记为 P2 TODO | 生产环境出现分发卡死时 |

---

## 14) 附录

### 14.1 规范-代码映射

| 规范项（本文档） | 现有基线路径 | 目标改动 |
|---|---|---|
| ExperimentFileBundle 重构 | `app/models/experiment.py:95-117` | 删除 `experiment_id`、`checksum`；新增 `name`、`storage_root`、`file_count`、`total_size_bytes` |
| ExperimentVersion 字段清理 | `app/models/experiment.py:55-86` | 删除 `is_visible`、`startup_script_ref`；新增 `env_bundle_id` |
| 容器启动命令动态化 | `app/core/container_manager.py:131-209` | 移除硬编码的 `launch_file` 和 `entrypoint_cmd`，改为参数注入；新增系统常驻启动脚本注入 rosbridge/gzweb 端口 |
| 学生可见性过滤 | `app/crud/experiment.py:list_student_available_versions()` | 移除 `is_visible` 条件，改为 `Experiment.status=active` |
| 仿真启动任务阶段扩展 | `app/api/v1/endpoints/student/simulation.py:_run_rebuild_task()` | 拆分 HEALTH_CHECKING 为 CHECKING_GZWEB + CHECKING_ROSBRIDGE |
| 学生首页进度展示 | `edubot-twin-web/src/views/Student/Home.vue:113-132` | 增强 `pollTaskUntilDone` 中的阶段文案映射 |
| 实验详情页字段清理 | `edubot-twin-web/src/views/Teacher/Experiments/ExperimentDetail.vue:42-72` | 移除 `is_visible`、`startup_script_ref` 表单项 |
| 教师路由重构 | `edubot-twin-web/src/router/index.ts:742-814` | `/teacher/experiments` 改为 `getParentLayout()` 嵌套结构 |
| 后端路由权限 | `app/api/v1/endpoints/common/auth.py:169-211` | 教师路由列表新增文件/环境管理路径 |

### 14.2 前端路由变更映射

**变更前**：
```
/teacher
├── home
├── students
├── experiments              → Experiments.vue
├── experiments/:id          → ExperimentDetail.vue (hidden)
└── containers/monitor
```

**变更后**：
```
/teacher
├── home
├── students
├── experiments              → getParentLayout() 二级菜单
│   ├── list                 → ExperimentList.vue（原 Experiments.vue 重命名）
│   ├── :id/detail           → ExperimentDetail.vue (hidden, activeMenu: /teacher/experiments/list)
│   ├── files                → ExperimentFiles.vue（新建）
│   └── environments         → ExperimentEnvs.vue（新建）
└── containers/monitor
```

**后端路由权限对应更新**：
```python
"teacher": [
    "/teacher",
    "/teacher/home",
    "/teacher/students",
    "/teacher/experiments",
    "/teacher/experiments/list",
    "/teacher/experiments/:id/detail",
    "/teacher/experiments/files",
    "/teacher/experiments/environments",
    "/teacher/containers",
    "/teacher/containers/monitor",
]
```

### 14.3 container_manager 参数扩展签名

当前签名：
```python
async def create_container(image, student_id, gz_port, ros_port) -> str
```

目标签名：
```python
async def create_container(
    image: str,
    student_id: int,
    gz_port: int,
    ros_port: int,
    *,
    launch_args: dict[str, str] | None = None,
    startup_script_path: str | None = None,
    env_volumes: dict[str, str] | None = None,
) -> str
```

**行为变更**：
2. `launch_args`：遍历 dict 生成 roslaunch 参数字符串 `key:=value`，直接格式化后作为环境变量 `LAUNCH_ARGS` 传入容器（教师为受信任角色，无需白名单校验）。教师在 `startup.sh` 中通过 `$LAUNCH_ARGS` 引用（如 `roslaunch pkg file.launch $LAUNCH_ARGS &`）。
3. `startup_script_path`：如果非空，将该文件路径（`{env_bundle.storage_root}/startup.sh`）挂载到容器 `/tmp/startup.sh`，在 entrypoint 中先执行此脚本。注意：启动脚本以文件形式存储在环境包根目录，不存数据库。
4. `env_volumes`：额外的 Volume 挂载映射（`{host_path: container_path}`），用于环境文件。

**参数分层约束**：实现时即便暂不引入完整 `ContainerSpec` 类型，也必须在 `container_manager` 内部按以下四组数据结构分层，禁止继续把新参数平铺堆入一段长函数：
- 镜像 / 端口：`image`、`student_id`、`gz_port`、`ros_port`
- 启动配置：`launch_args`、`startup_script_path`
- 文件挂载：`env_volumes`
- 运行模式：正式仿真 / Dry Run 的差异标记与清理策略

**向后兼容**：所有新增参数有默认值，现有调用方无需修改即可继续工作。

### 14.7 系统常驻启动脚本（system_entrypoint.sh）

每个容器固定挂载一个系统级启动脚本，负责启动 rosbridge_server 和 gzweb 服务。该脚本由平台维护，教师不可修改。

**统一前台守护约束**：容器启动链不再允许“教师脚本后台启动 + 系统脚本再各自拉起服务”的松耦合模式。最终 entrypoint 必须由一个统一前台守护入口负责拉起教师 `startup.sh`、rosbridge、gzweb，并定义任一关键进程退出时的失败语义、退出码和清理动作，避免容器存活但关键服务半故障的静默失败。

**脚本模板**（参考 `/home/ubuntu20/gzweb/dev_entrypoint.sh`）：

```bash
#!/bin/bash
# ============================================================
# system_entrypoint.sh — 系统常驻启动脚本（平台自动挂载）
# 功能：启动 rosbridge_server 和 gzweb 服务
# 端口通过环境变量注入：ROSBRIDGE_PORT, GZWEB_PORT
# ============================================================

ROSBRIDGE_PORT=${ROSBRIDGE_PORT:-9090}
GZWEB_PORT=${GZWEB_PORT:-8080}
GZWEB_DIR=${GZWEB_DIR:-/home/ubuntu20/gzweb}

# 启动 rosbridge_server（后台运行）
roslaunch rosbridge_server rosbridge_websocket.launch port:=${ROSBRIDGE_PORT} &

echo "正在启动 rosbridge (port=${ROSBRIDGE_PORT})..."
sleep 2

# 启动 gzweb 服务
cd $GZWEB_DIR
GZWEB_PORT=${GZWEB_PORT} npm start
```

**容器启动时的全部环境变量注入**：
```python
# launch_args 格式化
launch_args_str = " ".join(f"{k}:={v}" for k, v in launch_args.items()) if launch_args else ""

environment = {
    "ROSBRIDGE_PORT": str(ros_port),      # → 统一前台守护入口
    "GZWEB_PORT": str(gz_port),           # → 统一前台守护入口
    "LAUNCH_ARGS": launch_args_str,       # → 教师 startup.sh
}
```

**执行链**：统一前台守护入口拉起教师自定义 `startup.sh`（source 环境 + `roslaunch ... $LAUNCH_ARGS &`）与系统 `system_entrypoint.sh`（rosbridge + gzweb）。任一关键进程退出时，守护入口必须将容器状态显式标记为失败并触发清理路径。

### 14.4 readiness_checker 设计

TCP 端口探测工具，在 `app/core/readiness_checker.py` 中实现。

**核心函数签名**：
```python
async def check_port_ready(
    host: str,            # "127.0.0.1" 或 "0.0.0.0"
    port: int,            # 宿主机映射端口
    timeout_s: float = 60.0,
    interval_s: float = 2.0,
) -> tuple[bool, float]   # (is_ready, elapsed_ms)
```

**探测逻辑**：
1. 使用 `asyncio.open_connection(host, port)` 尝试 TCP 连接。
2. 连接成功（无异常）即视为端口就绪，立即返回。
3. 连接失败（`ConnectionRefusedError`、`OSError`）等待 `interval_s` 后重试。
4. 超过 `timeout_s` 仍未成功，返回 `(False, timeout_s * 1000)`。

**在 `_run_rebuild_task` 中的集成点**：

```
# 容器创建成功后，进入就绪检测
CREATING_NEW_CONTAINER → SUCCEEDED

# 新增两个阶段
mark_stage(CHECKING_GZWEB)
gzweb_ok, gzweb_ms = await check_port_ready("127.0.0.1", gz_port, timeout_s=60)
if not gzweb_ok: raise ReadinessTimeout("GZWEB_NOT_READY")
mark_stage(CHECKING_GZWEB, SUCCEEDED, gzweb_ms)

mark_stage(CHECKING_ROSBRIDGE)
rosbridge_ok, ros_ms = await check_port_ready("127.0.0.1", ros_port, timeout_s=60)
if not rosbridge_ok: raise ReadinessTimeout("ROSBRIDGE_NOT_READY")
mark_stage(CHECKING_ROSBRIDGE, SUCCEEDED, ros_ms)
```

### 14.5 术语表（新增/变更）

| 术语 | 定义 |
|---|---|
| 文件包（FileBundle） | 教师管理的实验资源包，独立于实验，通过版本外键引用 |
| 环境包（EnvBundle） | 教师管理的环境配置包，含 launch 相关文件和启动脚本（`startup.sh` 以文件形式存储在环境包根目录） |
| 就绪检测（Readiness Check） | 容器创建后检测 gzweb 和 rosbridge 端口是否可用的过程 |
| 试运行（Dry Run） | 教师临时创建测试容器，验证环境配置是否正确；复用学生仿真页面，容器停止后立即清理 |
| 访问权限（access_level） | 学生对环境文件的访问级别：readonly（只读）、readwrite（读写）、hidden（不可见） |
| 系统常驻启动脚本（System Entrypoint） | 平台维护的固定脚本，负责启动 rosbridge 和 gzweb，通过环境变量注入端口 |
| 统一文件操作函数（useFileOperations） | 前端抽取的通用 composable，通过 `apiPrefix` 参数适配学生/教师文件包/教师环境包三种文件 API |

### 14.6 变更记录

| 版本 | 日期 | 变更内容 |
|---|---|---|
| v1.0 | 2026-04-04 | 首版发布：第10期补充 SDD，包含模型修正、核心链路补全、教师资源管理页面三大板块 |
| v1.1 | 2026-04-04 | 六项重要修改：(1) Dry Run 复用学生仿真页面，容器停止后立即清理；(2) 新增系统常驻启动脚本，自动启动 rosbridge/gzweb 并注入端口；(3) 教师启动脚本模板与注释提醒；(4) 文件管理页改为左侧列表→双击进入文件树，右侧 Monaco 编辑器，移除 extract_zip；(5) 环境管理页同样双击进入文件树，启动脚本改为文件存储（不存 DB），基本设置移至左下方可调占比；(6) 文件包/环境包重命名和删除改为右键菜单 |
| v1.3 | 2026-04-04 | 工程审查后补充三项工程约束：(1) 容器启动链采用统一前台守护入口，任一关键进程退出即判失败；(2) 文件包与环境包文件操作统一收敛到 BundleFileService；(3) 版本发布必须复用 validate 的 blocking 校验，存在阻断项时拒绝发布 |

---

## 15) 前后端设计

### 15.1 学生首页 — 就绪检测阶段进度展示

**交互变更**：原 `loadingInstance.setText('正在重建仿真环境，请稍候...')` 替换为分阶段动态文案。

**阶段文案映射表**：

| `current_stage` | Loading 文案 | 进度百分比（参考值） |
|---|---|---|
| `PREPARING_CONFIG` | 正在准备配置... | 10% |
| `STOPPING_OLD_CONTAINER` | 正在清理旧环境... | 25% |
| `CREATING_NEW_CONTAINER` | 正在创建仿真容器... | 50% |
| `CHECKING_GZWEB` | 等待 Gazebo 仿真引擎启动... | 70% |
| `CHECKING_ROSBRIDGE` | 等待 ROS 通信桥启动... | 85% |
| `SUCCEEDED` | 仿真环境就绪，正在打开... | 100% |
| `FAILED` | （关闭 loading，弹出错误弹窗） | - |

**Loading 组件行为**：
- 使用 `ElLoading.service` 全屏遮罩。
- 每次轮询到新 stage 时调用 `loadingInstance.setText(stageText)`。
- SUCCEEDED 时延迟 500ms 后关闭 loading 并打开仿真页。
- FAILED 时立即关闭 loading，弹出 `ElMessageBox` 展示错误详情和重试按钮。

### 15.2 教师端实验列表页 — 增强操作

**现有能力**：查询、创建。

**新增操作列**：

| 操作 | 触发方式 | 条件 | 交互 |
|---|---|---|---|
| 切换状态 | 行内 Switch 组件 | 始终可用 | Switch 切换 active/draft；切换到 archived 用下拉菜单 |
| 删除 | 行内危险按钮 | 仅当无非 draft 版本 | 二次确认弹窗，含影响说明 |

### 15.3 教师端实验详情页 — 增强操作

**移除字段**：
- `is_visible` 复选框 → 删除
- `startup_script_ref` 输入框 → 删除

**新增字段**：
- `env_bundle_id` 选择器 → 下拉列表，可选已创建的环境包

**新增版本操作按钮**：

| 按钮 | 条件 | 说明 |
|---|---|---|
| 废弃版本 | `publish_status=published` | 切换为 deprecated |
| 重新发布 | `publish_status=deprecated` | 切换为 published；发布前必须再次执行 blocking 校验 |
| 删除版本 | `publish_status=draft` | 二次确认后删除 |
| 验证配置 | 始终可用 | 调用 validate API，展示 issues 列表 |

**保存后自动验证**：点击"保存配置"成功后，自动调用 `POST /validate`，若 `valid=false` 则在表单上方显示黄色警告条展示 issues。

**发布硬拦截约束**：`PATCH publish-status=published` 不是“只改状态”。它必须复用 `POST /validate` 的同一套 blocking 校验逻辑。只要存在 `severity=blocking` 的问题，就必须返回 `409 VALIDATION_BLOCKING_ISSUE`，并保持版本状态不变。

**结构化验证结果约束**：`issues` 不再只是一组自由文本，至少包含 `field`、`code`、`severity`、`message` 四个字段。当前强制支持以下阻断类问题：`missing_image`、`missing_bundle`、`empty_bundle`、`missing_env_bundle`、`missing_startup_script`。其中 `severity=blocking` 的问题必须阻止版本发布，且 validate 与 publish 不能各自实现两套不同规则。

### 15.4 实验文件管理页（10-S2 新建）

**路由**：`/teacher/experiments/files`

**布局**：左右分栏，左侧支持列表视图与文件树视图切换

**状态 A — 文件包列表视图（初始状态）**：

```
┌──────────────────────────────────────────────────────┐
│  实验文件管理                              [新建文件包] │
├──────────────┬───────────────────────────────────────┤
│              │                                       │
│  文件包列表   │                                       │
│  ─────────── │                                       │
│  📦 导航实验包│      (请选择一个文件包)                  │
│  📦 SLAM实验包│                                       │
│  📦 控制实验包│                                       │
│              │                                       │
│              │                                       │
│              │                                       │
│              │                                       │
├──────────────┴───────────────────────────────────────┤
│  状态栏: 共 3 个文件包                                  │
└──────────────────────────────────────────────────────┘
```

- **单击**：选中文件包（高亮显示），右侧显示文件包摘要信息。
- **双击**：进入文件树视图（切换到状态 B）。
- **右键菜单**：在文件包项上右键弹出上下文菜单，包含「重命名」和「删除」操作。
- **首屏可发现性约束**：列表空状态必须提供首次使用提示，明确“先新建文件包，再双击进入文件树编辑”；非空列表首屏需有轻提示文案说明“双击可进入文件树”。

**状态 B — 文件树视图（双击进入后）**：

```
┌──────────────────────────────────────────────────────┐
│  实验文件管理                                          │
├──────────────┬───────────────────────────────────────┤
│ [← 返回列表] │                                       │
│ 导航实验包    │  Monaco Editor                        │
│ ─────────── │  (点击左侧文件树中的文件打开编辑)         │
│  📁 src/     │                                       │
│    📄 nav.py │  # nav_demo.py                        │
│    📄 cfg.yml│  import rospy                         │
│  📁 launch/  │  ...                                  │
│    📄 main.. │                                       │
│           [↑]│                                       │
├──────────────┴───────────────────────────────────────┤
│  状态栏: 导航实验包 | 文件数: 12 | 总大小: 2.3MB         │
└──────────────────────────────────────────────────────┘
```

**左侧文件包管理栏（列表视图）**：
- 列表显示所有文件包（当前教师创建的）。
- 新建：顶部按钮，弹窗输入名称。
- **右键菜单操作**：
  - 重命名：弹窗输入新名称；后端返回 `affected_versions` 列表，前端展示提示："重命名将影响以下实验版本的文件包关联：..."。注意：重命名不改变 `bundle_id`，因此不影响外键引用，仅影响显示名称。
  - 删除：二次确认；若被版本引用，弹窗显示引用列表并阻止删除。

**左侧文件树（文件树视图）**：
- 顶部「← 返回列表」按钮，点击回到文件包列表视图。
- 文件树完全复用现有 WorkspacePanel 的文件树组件（`FileTree.vue`）和文件操作功能，通过统一的文件操作函数适配不同 API 后端地址。
- 文件操作（上传/删除/重命名/新建目录/解压）通过 `/teachers/file-bundles/{id}/files/*` API 完成。
- **上传压缩文件后不自动解压**：压缩文件直接保存到文件系统，教师可在文件树中通过右键菜单手动解压（复用文件树已有的解压功能）。
- [↑] 按钮为上传文件入口。

**右侧 Monaco 编辑器**：
- 点击文件树中的文件，在右侧 Monaco Editor 中打开编辑。
- 复用现有 `MonacoEditor.vue` 组件。
- 保存操作调用 `/teachers/file-bundles/{id}/files/save` API。
- **编辑态保护约束**：存在未保存变更时，切换文件、返回列表、离开当前路由、进入 Dry Run 前都必须弹出确认框，选项至少包含“保存后继续”和“放弃修改”。
- **保存冲突约束**：保存接口按 `modified_at` 或等价版本戳检测覆盖风险；若文件已被其他操作更新，后端返回 `409 FILE_SAVE_CONFLICT`，前端禁止静默覆盖。

### 15.5 实验环境管理页（10-S2 新建）

**路由**：`/teacher/experiments/environments`

**布局**：左右分栏，左侧支持列表视图与文件树+设置视图切换

**状态 A — 环境包列表视图（初始状态）**：

```
┌──────────────────────────────────────────────────────────┐
│  实验环境管理                                [新建环境包]   │
├──────────────┬───────────────────────────────────────────┤
│              │                                           │
│  环境包列表   │                                           │
│  ─────────── │       (请选择一个环境包)                    │
│  🔧 导航环境  │                                           │
│  🔧 SLAM环境  │                                           │
│              │                                           │
│              │                                           │
│              │                                           │
├──────────────┴───────────────────────────────────────────┤
│  状态栏: 共 2 个环境包                                      │
└──────────────────────────────────────────────────────────┘
```

- **单击**：选中环境包（高亮显示），右侧显示环境包摘要信息。
- **双击**：进入文件树+设置视图（切换到状态 B）。
- **右键菜单**：在环境包项上右键弹出上下文菜单，包含「重命名」和「删除」操作。
- **首屏可发现性约束**：空状态必须提示“先新建环境包，再双击进入文件树编辑 `startup.sh`”；列表存在数据时仍需保留“双击进入”的轻提示。

**状态 B — 文件树+基本设置视图（双击进入后）**：

```
┌──────────────────────────────────────────────────────────┐
│  实验环境管理                                              │
├──────────────┬───────────────────────────────────────────┤
│ [← 返回列表] │                                           │
│ 导航环境      │  Monaco Editor                            │
│ ──────────── │  (点击左侧文件打开编辑, 含 startup.sh)       │
│  📄 startup.sh│                                           │
│  📁 launch/  │  #!/bin/bash                              │
│    📄 sim.l..│  # ================================================ │
│  📁 config/  │  # 启动脚本 (以 ROOT 权限执行)               │
│    📄 nav.yml│  # ================================================ │
│           [↑]│  source "/opt/ros/noetic/setup.bash"       │
│ ─── ↕ ───── │  source "$WORKSPACE/devel/setup.bash"      │
│ ┌ 基本设置 ─┐│  ...                                      │
│ │ 目标目录:  ││                                           │
│ │ [/home/..] ││                                           │
│ │ 访问权限:  ││                                           │
│ │ [readonly] ││  [保存] [试运行]                           │
│ └───────────┘│                                           │
├──────────────┴───────────────────────────────────────────┤
│  状态栏: 导航环境 | 文件数: 5 | 访问级别: readonly            │
└──────────────────────────────────────────────────────────┘
```

**左侧文件树与基本设置**：
- 顶部「← 返回列表」按钮，点击回到环境包列表视图。
- 文件树完全复用现有 WorkspacePanel 的文件树组件（`FileTree.vue`）和文件操作功能，通过统一的文件操作函数适配不同 API 后端地址。
- 文件操作通过 `/teachers/env-bundles/{id}/files/*` API 完成。
- **`startup.sh` 文件**在文件树中始终显示在最顶部，带有特殊图标标识，且**不可删除**（右键菜单中删除选项对 `startup.sh` 禁用）。
- [↑] 按钮为上传文件入口。上传压缩包文件后不自动解压，可在文件树中手动解压。
- 文件树与基本设置之间有**可拖拽的分隔条**（`↕`），教师可自由调整两者占比。

**基本设置区（左侧下方）**：
- `container_target_dir`：环境文件在容器中的挂载目标目录，下拉建议常用路径。
- `access_level`：readonly（学生只读）、readwrite（学生可读写）、hidden（学生不可见）。

**右侧 Monaco 编辑器**：
- 点击文件树中的**任意文件**，在右侧 Monaco Editor 中打开编辑（包括 `startup.sh`、`.launch`、`.yaml` 等）。
- Monaco 编辑器根据文件后缀自动切换语言模式（`.sh` → shell, `.launch` → xml, `.yaml` → yaml 等）。
- 保存操作调用 `/teachers/env-bundles/{id}/files/save` API。
- **编辑态保护约束**：存在未保存变更时，切换文件、返回列表、离开当前路由、点击试运行前都必须弹出确认框，教师必须显式选择“保存后继续”或“放弃修改”。
- **保存冲突约束**：`startup.sh` 与普通文件均适用覆盖冲突检测，禁止因多窗口编辑造成静默覆盖。

**启动脚本模板与注释提醒**：

创建环境包时，后端自动在 `storage_root/startup.sh` 中生成以下模板内容（参考 `/home/ubuntu20/gzweb/dev_entrypoint.sh`）：

```bash
#!/bin/bash
# ================================================================
# 教师启动脚本 — 以 ROOT 权限执行
# ================================================================
# 本脚本在容器启动时首先执行，用于：
#   1. 加载 ROS 环境
#   2. 启动仿真节点（roslaunch）
#
# 注意：rosbridge 和 gzweb 由系统常驻脚本自动启动，无需在此处理。
#
# 常用模板（请根据实际情况修改）：
# ================================================================

# ── 1. 设置工作空间路径 ──────────────────────────────────────
WORKSPACE=/home/ubuntu20/catkin_ws

# ── 2. 加载 ROS 环境 ────────────────────────────────────────
source "/opt/ros/noetic/setup.bash"
source "$WORKSPACE/devel/setup.bash"

# ── 3. 设置并同步 Gazebo 自定义模型（可选：有自建模型时取消注释）──
# CUSTOM_MODEL_DIR="$WORKSPACE/src/your_package/models"
# export GAZEBO_MODEL_PATH=$GAZEBO_MODEL_PATH:$CUSTOM_MODEL_DIR
# 
# if [ -d "$CUSTOM_MODEL_DIR" ]; then
#     echo "正在同步自定义模型至浏览器前端 (GzWeb)..."
#     cp -r $CUSTOM_MODEL_DIR/* /home/ubuntu20/gzweb/http/client/assets/
#     
#     # 对自建模型增量转换 Web 格式 (PNG 贴图与路径修复)
#     for model_path in $CUSTOM_MODEL_DIR/*; do
#         if [ -d "$model_path" ]; then
#             TARGET_ASSET="/home/ubuntu20/gzweb/http/client/assets/$(basename "$model_path")"
#             python3 /home/ubuntu20/gzweb/webify_models_v2.py "$TARGET_ASSET" || true
#         fi
#     done
# fi

# ── 4. 启动 ROS 仿真节点（后台运行）──────────────────────────
# $LAUNCH_ARGS 由平台自动注入版本配置中的 launch_args_template 参数
# 例如: launch_args_template = {"robot_model": "turtlebot3", "world": "maze"}
#       → LAUNCH_ARGS="robot_model:=turtlebot3 world:=maze"
# roslaunch your_package your_launch_file.launch $LAUNCH_ARGS &

# ── 5. 等待仿真启动 ──────────────────────────────────────────
# sleep 5
```

**试运行按钮**：
- 点击后弹出确认对话框："将为您创建一个临时测试容器，验证启动脚本和 Launch 文件是否能正常运行。容器停止后将立即自动清理。"
- 需要选择关联的 `version_id`（指定镜像和 launch 配置来源）。
- 调用 `POST /teachers/env-bundles/{id}/dry-run {version_id}`。
- 若当前存在未保存修改，必须先完成保存或明确放弃，才允许进入 Dry Run。
- 成功后**跳转到学生仿真页面**（复用 `Simulation.vue` 工作台），教师可完整体验仿真环境。
- Dry Run 直接复用学生仿真页既有心跳机制；关闭页签、刷新页面或路由离开时执行 best-effort 清理，服务端继续以容器退出事件兜底。
- 仿真页顶部显示橙色提示条："试运行模式 — 该容器将在结束后立即自动清理"。
- 失败时展示容器日志摘要。

### 15.6 交互与文案矩阵（新增场景）

| 场景 | 后端返回 | 前端提示文案 | 用户可见动作 |
|---|---|---|---|
| 等待 Gazebo 启动 | `stage=CHECKING_GZWEB` | 等待 Gazebo 仿真引擎启动... | 显示进度条 70% |
| 等待 ROS 通信桥启动 | `stage=CHECKING_ROSBRIDGE` | 等待 ROS 通信桥启动... | 显示进度条 85% |
| Gazebo 超时 | `GZWEB_NOT_READY` | Gazebo 启动超时，请检查环境配置或重试 | 重试/返回首页 |
| ROS 超时 | `ROSBRIDGE_NOT_READY` | ROS 通信桥启动超时，请检查环境配置或重试 | 重试/返回首页 |
| 文件包上传成功 | 200 | 文件上传成功，共 {count} 个文件 | 文件树刷新 |
| 文件保存冲突 | 409 FILE_SAVE_CONFLICT | 文件已被其他操作更新，请刷新后重试 | 保留当前编辑内容，不做静默覆盖 |
| 文件包被引用不可删 | 409 BUNDLE_IN_USE | 该文件包被以下版本引用，请先解除关联：... | 展示版本列表 |
| startup.sh 禁止删除 | 403 | 启动脚本不可删除 | 弹出提示 |
| Dry Run 启动成功 | 200 | 测试容器已就绪，正在打开仿真工作台... | 跳转仿真页面 |
| Dry Run 启动失败 | 400/503 | 测试容器启动失败：{error_message} | 展示日志摘要 |
| 版本验证通过 | `{valid: true}` | 配置验证通过 ✓ | 绿色提示条 |
| 版本验证失败 | `{valid: false, issues}` | 配置存在以下问题：{issues} | 黄色警告条 + issues 列表 |
| 实验删除被阻止 | 409 | 该实验下存在已发布版本，请先废弃或删除所有版本 | 关闭弹窗 |
| 版本删除被阻止 | 409 | 仅草稿版本可删除 | 关闭弹窗 |

---

## 16) 补充：代码驱动增强点

### 16.1 文件包/环境包 API 复用策略

文件包和环境包的文件操作 API（upload/list/read/save/delete）逻辑高度相似，本期**强制**后端抽取一个 [`BundleFileService`](edubot-twin-server/app/services/bundle_file_service.py) 通用服务类，并将其提升为 10-S1 交付约束：

- 参数化 `storage_root`（文件包用 `/data/file_bundles/{id}`，环境包用 `/data/env_bundles/{id}`）。
- 统一路径安全校验、文件大小限制、编码检测、`modified_at`/版本戳冲突检测逻辑。
- 教师端文件操作 API 端点仅做鉴权和参数解析，实际文件操作委托给 [`BundleFileService`](edubot-twin-server/app/services/bundle_file_service.py)。
- 避免在 [`file_bundles.py`](edubot-twin-server/app/api/v1/endpoints/teacher/file_bundles.py) 和 [`env_bundles.py`](edubot-twin-server/app/api/v1/endpoints/teacher/env_bundles.py) 中重复实现相同逻辑。
- 环境包场景通过 `protected_paths` 参数约束（如 `startup.sh`），对受保护文件的删除操作返回 403。
- 上传与保存的幂等、覆盖冲突、错误码语义统一由 [`BundleFileService`](edubot-twin-server/app/services/bundle_file_service.py) 落地，禁止文件包与环境包各自定义不同规则。
- `file bundle` 与 `env bundle` 的文件操作测试也必须围绕同一服务编排，至少覆盖普通路径、越权路径、冲突保存、保护路径四类分支。

### 16.2 前端文件树组件复用策略

学生端 `FileManager.vue` 和仿真工作台 `WorkspacePanel` 已有文件树组件和文件操作功能（上传、删除、重命名、新建目录、解压）。教师端文件管理页和环境管理页应**完全复用**相同的文件树组件和文件操作逻辑，仅替换 API 后端地址。

**统一文件操作函数策略**：

建议抽取 `src/composables/useFileOperations.ts` 统一 composable，接收 `apiPrefix` 参数：

```typescript
// 统一文件操作函数
export function useFileOperations(apiPrefix: Ref<string>) {
  // apiPrefix 示例：
  //   学生端：      '/api/v1/students/files'
  //   教师文件包：   '/api/v1/teachers/file-bundles/123/files'
  //   教师环境包：   '/api/v1/teachers/env-bundles/456/files'

  const listFiles = (path?: string) => request.get(`${apiPrefix.value}`, { params: { path } })
  const readFile = (path: string) => request.get(`${apiPrefix.value}/read`, { params: { path } })
  const saveFile = (path: string, content: string) => request.post(`${apiPrefix.value}/save`, { path, content })
  const uploadFile = (file: File) => { /* multipart upload */ }
  const deleteFile = (path: string) => request.delete(`${apiPrefix.value}/delete`, { params: { path } })
  // ... 重命名、新建目录、解压等

  return { listFiles, readFile, saveFile, uploadFile, deleteFile, ... }
}
```

现有的文件树组件（`WorkspacePanel/FileTree.vue`）和文件操作命令（`useWorkspaceCommands.ts`）应重构为接收统一文件操作接口，而非硬编码学生端 API。

### 16.3 数据库迁移策略

本次涉及破坏性模型变更（删列），SQLite 不支持 `ALTER TABLE DROP COLUMN`（3.35.0+ 才支持），需要：

1. 创建新表（不含待删列）。
2. 从旧表迁移数据。
3. 删除旧表。
4. 重命名新表。

建议在 `init_db.py` 中增加迁移函数，检测表结构版本后执行迁移。

### 16.4 长期演进边界与技术债清单

**统一资源域升级触发条件**：满足以下任一条件时，当前 `file bundle` / `env bundle` 双实体方案必须升级为统一资源域（如 AssetLibrary），而不是继续在现有模型上叠补丁：
1. 资源类型扩展到 3 种及以上。
2. 文件包与环境包出现重复的权限、版本、审计、分享治理逻辑。
3. 教师协作编辑或跨课程共享成为常态需求。

**本期有意保留的技术债**：
- Dry Run 仍采用内存态记录，不做持久化表。
- readiness 错误码保持粗粒度，不细分检测器内部错误类别。
- `container_target_dir` 继续信任教师输入，不做危险目录白名单。
- 发布阶段保持基础回滚，不补零停机兼容窗口策略。

### 16.5 Dry Run 容器与正式容器隔离

Dry Run 容器使用独立标签 `edubot.type: dry-run`（正式容器为 `simulation`），便于：
- 运维识别和批量清理。
- 端口分配器排除 Dry Run 容器占用的端口（Dry Run 结束后释放）。
- 后台清理任务按标签过滤。

---

*文档结束。建议在实施前进行 Eng Review，重点关注数据库迁移方案和容器启动命令安全性。*
