# 询问模式规则（仅非显而易见内容）

## 文档位置陷阱

**ROS3D 扩展规范**: 在 `.agent/rules/ros3dviewer-extension-guidance.md`，不在代码注释中

**路由配置说明**: 在 `.agent/rules/router-map-guidance.md`，解释双重配置原则

**仿真面板开发**: 在 `.agent/rules/simulation-panel-guidance.md`，包含 Golden Layout 集成

## 反直觉的架构设计

**Renderer 不依赖 roslib**：`index.vue` 作为桥接层注入消息，Renderer 只处理标准化数据

**非连续渲染**：Three.js 场景不是每帧自动渲染，必须调用 `queueAnimationFrame()` 触发

**设置树 JSON 驱动**：UI 表单由 `buildSettingsTree()` 返回的 JSON 描述生成，不是硬编码组件

## 测试账号

| 用户名 | 密码 | 角色 |
|--------|------|------|
| admin | admin | admin |
| test | test | test |
| student | student | student |

## 项目记忆系统

`.ai_memory/` 目录维护长期上下文（简体中文）：
- `1_project_context.md` - 核心知识库
- `2_active_task.md` - 当前任务
- `3_work_log.md` - 开发日志
