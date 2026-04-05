# 当前任务状态

## 任务：第10期补充SDD（S2 + S1前端补全） 

### 状态：✅ S2 全部完成

---

## S2 最终完成清单

| 工作项 | SDD 来源 | 状态 |
|---|---|---|
| 教师端路由重构（二级菜单） | §12.2/§S2-1 | ✅ |
| ExperimentList.vue（实验列表+状态切换+删除） | §12.2/§15.2 | ✅ |
| ExperimentFiles.vue（文件包管理） | §12.2/§15.4 | ✅ |
| ExperimentEnvs.vue（环境包管理+Dry Run） | §12.2/§15.5 | ✅ |
| useFileOperations.ts composable | §12.2/§16.2 | ✅ |
| auth.py 路由权限更新 | §12.2 | ✅ |
| ExperimentDetail.vue 字段清理（移除 is_visible/startup_script_ref） | §15.3 | ✅ |
| ExperimentDetail.vue 版本操作按钮（废弃/重新发布/删除/验证） | §15.3 | ✅ |
| ExperimentDetail.vue env_bundle_id 改为下拉选择 | §15.3 | ✅ |
| ExperimentDetail.vue 保存后自动验证+黄色警告条 | §15.3 | ✅ |
| Student/Home.vue 分阶段进度显示（CHECKING_GZWEB等） | §15.1 | ✅ |
| Student/Home.vue FAILED 时弹出错误弹窗含重试按钮 | §15.1 | ✅ |
| Student/Home.vue SUCCEEDED 时延迟500ms跳转 | §15.1 | ✅ |
| Simulation.vue Dry Run 橙色提示条 | §15.5 | ✅ |
| Simulation.vue Dry Run best-effort 容器清理 | §15.5 | ✅ |

## 新增 API

| 函数 | 端点 | SDD |
|---|---|---|
| `deleteExperimentVersionApi` | DELETE /experiments/{eid}/versions/{vid} | §6.3 |
| `updateExperimentVersionPublishStatusApi` | PATCH .../{vid}/publish-status | §6.3 |
| `validateExperimentVersionApi` | POST .../{vid}/validate | §6.3 |

## 新增 Types

- `ExperimentVersionIssue`
- `ExperimentVersionValidateResponse`
- `ExperimentVersionPublishStatusRequest`
- `ExperimentVersionPublishStatusResponse`
- `SimulationTaskStage`（枚举）

---

## 剩余 Lint（纯格式，不影响运行）

ExperimentDetail.vue 中有若干 ESLint 行宽格式换行警告，可用 `npx eslint --fix` 统一处理。

---

## 下一步建议（非S2范围）

- 后端实现 S1 所有 Endpoints（前端已完全准备就绪）
- 验收测试：按 SDD §11.2/11.3 场景逐一测试
