# TODOS - 第10期 实验环境版本化与容器重建主链路

**生成日期**：2026-04-02
**来源**：CEO Review 审查
**优先级**：P1（必须）> P2（重要）> P3（可选）

---

## P1 — 必须处理（验收前）

### P95 ≤ 30s 指标的可测量定义

**What:** 补充 SDD 第11节验收标准：
1. 负载剖面：至少 30 个学生并发触发重建（模拟正常班级规模）
2. 计时起点：从 `POST /students/simulation/start` 收到 202 响应到 `SimulationTask.status = SUCCEEDED`
3. 前提条件：`edubot/gazebo-ros` 镜像已预拉取至所有宿主机节点（否则 P95 无意义）

**Why:** 当前硬指标无法客观验收，上线后无法判断是否达标。开发团队可能因"主观感觉快"而误判通过。

**Pros:** 让指标可测量，避免上线后争议。
**Cons:** 需准备压测环境（但教学场景本身就是 30 人并发，不算额外工作量）。

**Context:** CEO Review 外部节点发现此缺口。需要在第10期验收测试前补全，否则"稳定性验收"章节无法客观执行。

**Effort:** S (human) → S (CC+gstack)
**Priority:** P1
**Depends on:** 第10期主链路实现完成，测试环境就绪

---

## P2 — 重要，下期或实现阶段处理

### 文件分发 API 同步/异步语义明确化

**What:** `POST /students/simulation/files/distribute` 响应中包含 `job_id`，但没有对应的 `/tasks/{job_id}` 查询路由，且状态码为 200，暗示同步语义。若文件包较大（如 >100MB），同步分发可能导致请求超时。

**Why:** 语义不一致（job_id 暗示异步，200 暗示同步）会导致前端轮询逻辑错误，也会让大文件场景无从处理。

**Pros:** 明确语义后，可选择：(a) 彻底同步（加超时保护，适合小文件）；(b) 纳入 SimulationTask 阶段（最一致）；(c) 独立 job 体系（最灵活但最复杂）。
**Cons:** 改造涉及 API 契约变更，需前后端联动。

**Context:** 外部评审（plan-eng-review 第10期）发现此缺口。当前 SDD 暂定同步，上线后若出现大文件包场景需评估是否重构。

**Effort:** S (human) → S (CC+gstack)
**Priority:** P2
**Depends on:** 第10期稳定运行后收集实际文件包大小分布数据

### 孤儿任务超时阈值标定

**What:** TaskRunner 启动时扫描 `updated_at < now()-5min` 的孤儿任务。5 分钟阈值需根据实际任务耗时上限校准。

**Why:** 如果阈值太低，正常慢任务（网络慢时 Docker stop 可能接近 2 分钟）会被误判为孤儿，导致两个并发容器创建竞争。

**Pros:** 消除误判风险，提高系统可靠性。
**Cons:** 需要先收集真实 P99 任务耗时数据。

**Context:** 外部节点指出 5min 窗口可能与正常慢任务冲突。建议上线后通过 `simulation_rebuild_duration_ms` 指标观察 P99，再调整阈值（建议 P99 + 60s 缓冲）。

**Effort:** S (human) → XS (CC+gstack)
**Priority:** P2
**Depends on:** 第10期稳定运行 1 个迭代，收集到 P99 耗时数据

---

### 实验模板/Fork 功能

**What:** 教师可基于现有实验创建分支实验（Fork），复用环境配置和文件包。

**Why:** 每次创建新实验都要从零填写重复字段（launch 文件、参数模板），浪费时间。

**Pros:** 降低实验创建成本，鼓励教师积累实验库。
**Cons:** 需要处理 file_bundle 的浅拷贝/深拷贝语义。

**Context:** 第10期已有完整 Experiment + ExperimentVersion 领域模型，Fork 是自然扩展。

**Effort:** S (human) → S (CC+gstack)
**Priority:** P2
**Depends on:** 第10期完成且实验管理页稳定

---

### 教师操作链路问题回放面板 / 运维查询页

**What:** 提供按 `trace_id`、`bundle_id`、`version_id`、`dry_run_container_id` 查询的教师问题回放面板或运维查询页，串联文件编辑、配置验证、Dry Run、发布等关键链路。

**Why:** 当前第10期补充 SDD 保持现有日志与指标方案，若教师反馈“改过文件后 Dry Run 失败”之类问题，缺少一个可直接回看整条操作链路的统一入口，排障成本高。

**Pros:** 显著降低跨页面、跨接口、跨容器问题的定位成本，让运维和研发可以快速复盘一次教师操作链。
**Cons:** 需要补查询聚合能力和展示界面，且依赖日志字段口径长期稳定。

**Context:** 来自第10期补充 SDD 的 CEO/架构审查，作为第8节可观测性审查后的延后项保留。当前先保持现状，不纳入本期交付，但建议在资源管理链路稳定后优先规划。

**Effort:** M (human) → S (CC+gstack)
**Priority:** P2
**Depends on:** 第10期补充 SDD 落地，文件编辑 → 验证 → Dry Run → 发布链路的日志字段稳定可追踪

---

### 教师资源管理首次使用向导

**What:** 为教师资源管理页增加一步式首次使用向导，将“新建环境包 → 编辑 `startup.sh` → 选择 `version_id` → Dry Run”串成可视化引导流程。

**Why:** 当前第10期补充 SDD 已决定补齐首屏空状态、双击进入可发现性和 Dry Run 风险提示，但首次使用仍可能让教师不知道推荐顺序，导致学习成本偏高。

**Pros:** 降低首次上手门槛，减少教师在文件页、环境页、详情页之间来回试错的次数。
**Cons:** 需要补引导状态管理、步骤文案和跨页面跳转设计，且要避免打扰熟练用户。

**Context:** 来自第11节设计与 UX 审查。当前阶段先选择在 SDD 中落地首屏设计约束，不把向导纳入本期强制交付，作为后续增强项保留到 [`docs/第10期/TODOS.md`](docs/第10期/TODOS.md)。

**Effort:** M (human) → S (CC+gstack)
**Priority:** P2
**Depends on:** 教师文件管理页、环境管理页、Dry Run 主流程稳定，首屏空状态和提示文案先完成
