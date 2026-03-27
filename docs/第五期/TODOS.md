# TODOS - 教师端管理模块（第五期）

**生成日期**：2026-03-27  
**来源**：工程架构审查  
**优先级**：P0（必须）> P1（重要）> P2（可选）

---

## P0 - 必须完成（本期范围）

### 后端 - 架构优化

#### TODO-1: 添加 SimContainer 与 Student 的 relationship
**What**: 在 `models/container.py` 中添加 relationship 定义  
**Why**: 解决 N+1 查询问题，监控 API 性能提升 96%  
**Pros**: 自动预加载，所有查询受益  
**Cons**: 增加模型耦合  
**Context**: 当前监控 API 查询 50 个容器需要 51 次数据库查询（1 次容器 + 50 次学生）。添加 relationship 后只需 2 次查询。  
**Implementation**:
```python
# models/container.py
from sqlalchemy.orm import relationship

class SimContainer(Base):
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    student: Mapped["Student"] = relationship(lazy='selectin')
```
**Depends on**: 无  
**Blocked by**: 无  
**Effort**: 5 分钟

---

#### TODO-2: 实现后台采集任务（FastAPI BackgroundTasks）
**What**: 使用 FastAPI startup event + asyncio 实现 10 秒定时采集  
**Why**: 监控 API 需要从缓存读取性能数据，而非实时查询 Docker  
**Pros**: 无额外依赖，与 FastAPI 生命周期绑定，简单可靠  
**Cons**: 单进程方案，多 worker 需要协调  
**Context**: CEO Review 原方案使用 APScheduler（1.5 小时），简化为 asyncio（30 分钟），节省 1 小时。采集任务需要并发查询 50+ 容器的 Docker stats，顺序执行需 5 秒，并发执行只需 500ms。  
**Implementation**:
```python
# app/main.py
@app.on_event("startup")
async def start_metrics_collector():
    asyncio.create_task(metrics_collection_loop())

async def metrics_collection_loop():
    while True:
        await collect_all_metrics()
        await asyncio.sleep(10)
```
**Depends on**: TODO-3（container_metrics 表）  
**Blocked by**: 无  
**Effort**: 30 分钟

---

#### TODO-3: 创建 container_metrics 表
**What**: 新增表存储容器性能历史数据  
**Why**: 支持后台采集任务和历史趋势分析  
**Pros**: 解耦采集和查询，支持历史数据  
**Cons**: 增加存储空间  
**Context**: 表结构包含 container_id, cpu_percent, memory_mb, timestamp, collection_status, error_message。需要复合索引 (container_id, timestamp) 和单独的 timestamp 索引。  
**Implementation**:
```sql
CREATE TABLE container_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    container_id INTEGER NOT NULL,
    cpu_percent FLOAT NOT NULL,
    memory_mb INTEGER NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    collection_status VARCHAR(20) DEFAULT 'success',
    error_message VARCHAR(500),
    FOREIGN KEY (container_id) REFERENCES sim_containers(id) ON DELETE CASCADE
);
CREATE INDEX idx_container_time ON container_metrics(container_id, timestamp);
CREATE INDEX idx_timestamp ON container_metrics(timestamp);
```
**Depends on**: 无  
**Blocked by**: 无  
**Effort**: 15 分钟

---

#### TODO-4: 实现健壮的采集错误处理
**What**: 分级错误处理 + 状态字段  
**Why**: 防止 Docker daemon 故障导致监控失效  
**Pros**: 单容器故障不影响整体，错误可追溯  
**Cons**: 增加代码复杂度  
**Context**: 原设计使用 `try-except pass` 静默失败。需要区分：容器不存在（WARNING）、Docker 不可达（ERROR）、采集超时（WARNING）。  
**Implementation**: 见 Eng-Review 文档 2.2 节决策 3  
**Depends on**: TODO-2, TODO-3  
**Blocked by**: 无  
**Effort**: 30 分钟

---

#### TODO-5: 添加教师角色验证中间件
**What**: 实现 `get_current_teacher` 依赖注入  
**Why**: 防止学生通过 API 访问教师端功能  
**Pros**: 统一的安全验证，防止权限绕过  
**Cons**: 无  
**Context**: 学生端 API 已有 `get_current_student_id` 验证，教师端需要对应的角色验证。验证 role in ["teacher", "admin"]。  
**Implementation**:
```python
# app/core/security.py
async def get_current_teacher(token: str = Depends(oauth2_scheme)):
    payload = verify_token(token)
    if not payload:
        raise HTTPException(401, "无效的认证令牌")
    role = payload.get("role")
    if role not in ["teacher", "admin"]:
        raise HTTPException(403, "需要教师权限")
    return payload.get("user_id")
```
**Depends on**: 无  
**Blocked by**: 无  
**Effort**: 20 分钟

---

#### TODO-6: 添加历史数据清理任务
**What**: 每天凌晨 3 点删除 7 天前的 metrics 数据  
**Why**: 防止数据库无限增长  
**Pros**: 自动化清理，无运维负担  
**Cons**: 无  
**Context**: 50 个容器每天产生 432,000 条记录，7 天约 300MB。清理逻辑集成到后台采集任务中。  
**Implementation**:
```python
async def cleanup_old_metrics():
    cutoff = datetime.utcnow() - timedelta(days=7)
    await db.execute(delete(ContainerMetrics).where(ContainerMetrics.timestamp < cutoff))
```
**Depends on**: TODO-2  
**Blocked by**: 无  
**Effort**: 15 分钟

---

#### TODO-7: 实现批量操作 API（部分成功模式）
**What**: batch-start/stop/delete 三个端点，返回详细结果  
**Why**: 教师需要批量管理容器  
**Pros**: 提升运维效率，部分失败不阻塞整体  
**Cons**: 无  
**Context**: 批量操作需要返回每个容器的成功/失败状态，前端显示明细。见 Eng-Review 文档 2.2 节决策 8。  
**Implementation**: 见 Eng-Review 文档  
**Depends on**: 无  
**Blocked by**: 无  
**Effort**: 45 分钟

---

#### TODO-8: 添加学生删除的事务和容错处理
**What**: 使用事务包裹删除操作，Docker 失败时容错继续  
**Why**: 保证数据一致性，防止 Docker 故障阻塞学生删除  
**Pros**: 数据库是唯一真相源  
**Cons**: 无  
**Context**: 学生删除需要级联删除容器。Docker 容器可能已被手动删除，需要容错处理。  
**Implementation**:
```python
async with db.begin():
    for container in containers:
        try:
            await container_manager.remove_container(...)
        except NotFound:
            logger.warning("容器已不存在")
        except Exception as e:
            logger.error(f"Docker 删除失败: {e}")
        await db.delete(container)
    await db.delete(student)
```
**Depends on**: 无  
**Blocked by**: 无  
**Effort**: 10 分钟

---

#### TODO-9: 添加并发采集和超时控制
**What**: 使用 asyncio.Semaphore 限制并发数为 10，单容器超时 5 秒  
**Why**: 50 个容器顺序采集需 5 秒，并发采集只需 500ms  
**Pros**: 性能提升 10x  
**Cons**: 增加代码复杂度  
**Context**: 采集间隔 10 秒，5 秒用于采集效率低。见 Eng-Review 文档 5.2 节优化 1。  
**Implementation**: 见 Eng-Review 文档  
**Depends on**: TODO-2  
**Blocked by**: 无  
**Effort**: 20 分钟

---

#### TODO-10: 配置数据库连接池
**What**: 设置 pool_size=20, max_overflow=10  
**Why**: 防止高并发时连接耗尽  
**Pros**: 提升连接复用效率  
**Cons**: 无  
**Context**: 10 个教师 + 后台采集任务并发查询，默认连接池可能不足。  
**Implementation**:
```python
engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=3600
)
```
**Depends on**: 无  
**Blocked by**: 无  
**Effort**: 5 分钟

---

### 后端 - 代码质量

#### TODO-11: 统一错误响应格式
**What**: 所有端点统一使用 ApiResponse  
**Why**: 前端只需处理一种响应格式  
**Pros**: 代码一致性  
**Cons**: 需要修改现有端点  
**Context**: 当前混合使用 ApiResponse 和 JSONResponse。  
**Implementation**: 将所有 `JSONResponse(status_code=200, content={...})` 改为 `ApiResponse(code=..., message=..., data=...)`  
**Depends on**: 无  
**Blocked by**: 无  
**Effort**: 10 分钟

---

#### TODO-12: 添加结构化日志
**What**: 实现 `log_container_event` 函数，JSON 格式日志  
**Why**: 便于日志分析和告警  
**Pros**: 包含上下文信息，易于排查  
**Cons**: 无  
**Context**: 日志级别规范：ERROR（需告警）、WARNING（可恢复）、INFO（正常操作）。  
**Implementation**: 见 Eng-Review 文档 3.2 节改进 3  
**Depends on**: 无  
**Blocked by**: 无  
**Effort**: 20 分钟

---

#### TODO-13: 添加资源配额输入验证
**What**: 在 ContainerCreate schema 中添加 Field 验证  
**Why**: 防止无效配额导致容器创建失败  
**Pros**: 安全可靠，自动生成 API 文档  
**Cons**: 无  
**Context**: CPU 范围 0.1-4.0，内存范围 256-8192 MB。  
**Implementation**: 见 Eng-Review 文档 3.2 节改进 4  
**Depends on**: 无  
**Blocked by**: 无  
**Effort**: 15 分钟

---

### 前端

#### TODO-14: 实现 Students.vue 学生管理页面
**What**: 参考 Authorization/User/User.vue 实现完整 CRUD  
**Why**: 教师需要管理学生账号  
**Pros**: 复用现有模式，开发快速  
**Cons**: 无  
**Context**: 使用 useTable + useCrudSchemas，包含搜索、分页、新增、编辑、删除功能。  
**Implementation**: 参考 User.vue 模式  
**Depends on**: 后端学生管理 API  
**Blocked by**: 无  
**Effort**: 1 小时

---

#### TODO-15: 实现 Monitor.vue 容器监控页面
**What**: 显示容器列表 + 性能数据 + 批量操作  
**Why**: 教师需要监控容器运行情况  
**Pros**: 实时监控，批量管理  
**Cons**: 无  
**Context**: 使用 useTable，30 秒轮询，Page Visibility API 控制。状态用 el-tag，性能用 el-progress。  
**Implementation**: 见 SDD 文档 3.2.2 节  
**Depends on**: 后端监控 API  
**Blocked by**: 无  
**Effort**: 1.1 小时

---

#### TODO-16: 添加前端轮询可见性控制
**What**: 使用 Page Visibility API 控制轮询  
**Why**: 减少 70% 无效请求  
**Pros**: 降低服务器负载  
**Cons**: 无  
**Context**: 页面不可见时停止轮询，可见时恢复。  
**Implementation**: 见 Eng-Review 文档 2.2 节决策 9  
**Depends on**: TODO-15  
**Blocked by**: 无  
**Effort**: 10 分钟

---

#### TODO-17: 配置双重路由
**What**: 在 router/index.ts 和 mock/role/index.mock.ts 同时配置  
**Why**: 前端路由系统要求  
**Pros**: 用户可以访问页面  
**Cons**: 容易遗漏  
**Context**: 必须同时配置父路由和子路由，否则 404。  
**Implementation**: 见 SDD 文档 3.1 节  
**Depends on**: TODO-14, TODO-15  
**Blocked by**: 无  
**Effort**: 10 分钟

---

### 测试

#### TODO-18: 添加完整测试覆盖（78 个测试）
**What**: 后端单元测试 42 个 + 前端组件测试 28 个 + E2E 测试 8 个  
**Why**: 当前 0% 测试覆盖率，生产风险极高  
**Pros**: 保证代码质量，防止回归  
**Cons**: 增加工作量  
**Context**: 关键路径（学生删除级联、批量操作）必须有测试。见 Eng-Review 文档第 4 节测试覆盖率图表。  
**Implementation**: 使用 pytest（后端）+ Vitest（前端）  
**Depends on**: 所有功能实现完成  
**Blocked by**: 无  
**Effort**: 1 小时

---

## P1 - 重要（第六期优先）

#### TODO-19: 告警阈值系统
**What**: CPU/内存超阈值时主动通知教师  
**Why**: 为自动化运维打基础  
**Pros**: 主动发现问题  
**Cons**: 需要通知渠道（邮件/短信）  
**Context**: 依赖 container_metrics 表的历史数据。  
**Depends on**: TODO-3  
**Blocked by**: 无  
**Effort**: 2 小时

---

#### TODO-20: 学生批量导入（Excel/CSV）
**What**: 支持批量创建学生账号  
**Why**: 新学期必备功能  
**Pros**: 提升效率  
**Cons**: 需要文件解析和验证  
**Context**: 使用 pandas 解析 Excel，批量插入数据库。  
**Depends on**: TODO-14  
**Blocked by**: 无  
**Effort**: 2 小时

---

#### TODO-21: 历史性能趋势图表
**What**: ECharts 折线图展示 CPU/内存趋势  
**Why**: 帮助诊断性能问题  
**Pros**: 可视化分析  
**Cons**: 需要积累历史数据  
**Context**: 查询 container_metrics 表，按时间聚合。  
**Depends on**: TODO-3  
**Blocked by**: 需要至少 1 天的历史数据  
**Effort**: 3 小时

---

## P2 - 可选（按需实现）

#### TODO-22: 容器操作日志审计
**What**: 记录所有容器操作历史  
**Why**: 问题追溯和责任界定  
**Pros**: 完整的审计日志  
**Cons**: 增加存储  
**Context**: 新增 container_operation_logs 表。  
**Depends on**: 无  
**Blocked by**: 无  
**Effort**: 1 小时

---

#### TODO-23: WebSocket 实时推送
**What**: 替代轮询，实时推送容器状态变化  
**Why**: 更好的用户体验  
**Pros**: 实时性更好  
**Cons**: 增加复杂度，轮询方案已足够  
**Context**: 使用 FastAPI WebSocket。  
**Depends on**: TODO-15  
**Blocked by**: 无  
**Effort**: 3 小时

---

## 工作量汇总

| 优先级 | 任务数 | 总工作量 |
|--------|--------|----------|
| P0（必须） | 18 | 8.5 小时 |
| P1（重要） | 3 | 7 小时 |
| P2（可选） | 2 | 4 小时 |
| **总计** | **23** | **19.5 小时** |

---

**文档状态**：已完成  
**生成工具**：工程架构审查  
**最后更新**：2026-03-27
