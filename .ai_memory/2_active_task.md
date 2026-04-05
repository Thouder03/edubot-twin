# 当前任务状态

## 最后完成：10-S1 实验管理增强与资源管理体系（已完成）
**完成时间**：2026-04-05

### S1 完成项清单
- [x] 10-S1-1: 删除 ExperimentVersion.is_visible（可见性改由 Experiment.status+publish_status 决定）
- [x] 10-S1-2: ExperimentFileBundle 新增 name/storage_root/file_count/total_size_bytes，删除 experiment_id/checksum
- [x] 10-S1-3: 删除 ExperimentVersion.startup_script_ref（改为 startup.sh 文件存储在环境包中）
- [x] 10-S1-4: 新增 ExperimentEnvBundle 模型
- [x] 10-S1-5: ExperimentVersion 新增 env_bundle_id 外键
- [x] 10-S1-6: 新增文件包 API（/teachers/file-bundles/*）
- [x] 10-S1-7: container_manager.create_container 新增 launch_args/startup_script_path/env_volumes/is_dry_run 参数
- [x] 10-S1-7b: system_entrypoint.py（统一前台守护入口，废弃 hardcode patch_cmd）
- [x] 10-S1-8: SimulationTaskStage 新增 CHECKING_GZWEB + CHECKING_ROSBRIDGE
- [x] 10-S1-9: 实验状态机 + 删除 API（draft→active→archived→active，active 不可回退）
- [x] 10-S1-10: 版本发布状态机 + 删除 API
- [x] 10-S1-11: 版本 validate API + 发布前 blocking 强制校验
- [x] 10-S1-12: 学生可见性查询重构（JOIN Experiment.status=active）
- [x] 10-S1 测试：29/29 全部通过

### 新增文件列表
- app/models/experiment.py（重构）
- app/crud/experiment.py（重构）
- app/schemas/experiment.py（重构）
- app/services/bundle_file_service.py（新增）
- app/core/readiness_checker.py（新增）
- app/core/system_entrypoint.py（新增）
- app/api/v1/endpoints/teacher/file_bundles.py（新增）
- app/api/v1/endpoints/teacher/env_bundles.py（新增）
- app/api/v1/endpoints/teacher/experiments.py（重构）
- app/api/v1/endpoints/student/simulation.py（更新）
- tests/test_s1_integration.py（新增，29 个测试用例）

## 下一步（S2 阶段）
- 前端：实验管理路由拆分为二级菜单，文件包/环境包管理页 UI
- 前端：学生端首页就绪检测进度展示（CHECKING_GZWEB/CHECKING_ROSBRIDGE）
- 后端：Dry Run 触发端点与自动清理逻辑
