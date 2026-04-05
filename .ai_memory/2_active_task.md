# 当前任务状态

## 任务：第10期补充SDD（S2 偏差修复）

### 状态：✅ 所有 SDD 偏差已修复完毕

---

## 偏差修复完成清单

| 偏差 | 描述 | 状态 |
|---|---|---|
| 偏差1 | Dry Run 后端端点按 SDD 重构（接受 version_id，返回 simulation_url） | ✅ |
| 偏差2 | Dry Run 版本选择改为两级联动下拉（实验→版本） | ✅ |
| 偏差3 | 保存冲突检测协议完整透传（modified_at） | ✅ |
| 偏差4 | 删除旧 Experiments.vue | ✅ |

---

## 偏差1：Dry Run 后端端点按 SDD 重建（最复杂）

**SDD 要求**（§6.2）：
```
POST /api/v1/teachers/env-bundles/{id}/dry-run
Request:  { version_id: int }
Response: { container_id: str, simulation_url: str }
```

### 修改文件清单

| 文件 | 变更内容 |
|---|---|
| `schemas/experiment.py` | 新增 `EnvBundleDryRunByVersionRequest`（接受 `version_id`）和 `EnvBundleDryRunByVersionResponse`（`container_id + simulation_url + rosbridge_url`）；旧 Schema 保留带废弃注释 |
| `core/dry_run_manager.py` | 新增 `count_for_teacher(teacher_id)` 方法，用于配额检查（SDD §8：每教师最多3个） |
| `api/v1/endpoints/teacher/env_bundles.py` | Dry Run 路由完全重写：接受 `version_id`，查版本读取 `image_name/launch_file_path/launch_args_template`，检查配额，启动容器并返回 `{container_id, simulation_url, rosbridge_url}` |
| `src/api/experiment/types.ts` | `DryRunStartResponse` 增加 `rosbridge_url` 字段 |
| `src/views/Teacher/Experiments/ExperimentEnvs.vue` | 跳转时传入 `rosbridge_url` query 参数 |
| `src/views/Simulation/Simulation.vue` | Dry Run 模式下从 `route.query.simulation_url` / `rosbridge_url` 获取 GzBridge 初始化地址，跳过调用学生容器 API |

### 技术决策
- response 在 SDD 基础上额外增加 `rosbridge_url`（SDD 仅定义 `simulation_url`），因为 Simulation.vue 需要用它初始化 ROS3D 连接，SDD 未覆盖此细节但从完整性考虑是必要的。

---

## 偏差2/3/4 已在上一轮会话完成（见 0_archive_context.md）

---

## 下一步建议（验收阶段）
- 按 SDD §11.2/11.3 进行功能验收测试
- 特别验证 Dry Run 全流程：选择版本 → 启动容器 → 跳转仿真页 → 结束清理
- 验证文件保存冲突检测：双浏览器同时编辑同一文件，后保存者应收到 409 提示
