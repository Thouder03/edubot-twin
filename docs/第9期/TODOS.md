# TODOS

本项目的延迟工作清单，按优先级排序。

---

## P2 — 重要，下期考虑

### [第9期后] Topic 自动发现

**What:** 调用 rosbridge `/rostopic/list` API 列出可用 Topic，Rosout 和 Camera 面板提供下拉选择而非手动输入。

**Why:** 学生记不住 Topic 名称，手动输入错误率高。自动发现消除猜测，提升实训效率。

**Pros:** 用户体验大幅提升；杜绝拼写错误；支持动态发现新的传感器 Topic。

**Cons:** 需额外 rosbridge API 调用；列表可能很长（需过滤）；rosbridge 版本兼容性需验证。

**Context:** 第9期已实现 Topic 名称在设置树手动配置，这是下一步自然进化。调用 `ros.getTopics()` 即可获取列表。

**Effort:** M (human) → S (CC+gstack)

**Priority:** P2

**Depends on:** 第9期完成（Rosout + Camera 面板稳定运行后）

---

## P3 — 有价值，后期规划

### [第10期+] 多摄像头 PiP 布局

**What:** 支持同时查看多个摄像头视角（如全局俯视 + 机器人视角），以画中画或并排方式显示。

**Why:** 移动机器人实训常需要多视角协调调试（如导航 + 抓取）。

**Pros:** 显著提升调试效率；架构上已支持（多个 CameraPanel 实例即可）。

**Cons:** 需设计 PiP 布局容器；多 rosbridge 连接带宽压力增大。

**Context:** 第9期 CameraPanel 设计为无状态单 Topic 订阅者，天然支持多实例。无需重构，仅需 UI 布局支持。

**Effort:** M (human) → S (CC+gstack)

**Priority:** P3

**Depends on:** 第9期 CameraPanel 稳定

---

### [第10期+] rosout 日志录制与回放

**What:** 录制指定时间段的 rosout 日志，存储后可回放，用于复现 bug 场景。

**Why:** 学生在实训中经常遇到一次性 bug，无法事后重现给老师看。录制功能解决"只出现一次"的问题。

**Pros:** 大幅提升 bug 上报质量；支持离线分析。

**Cons:** 需要持久化存储（IndexedDB 或后端 API）；回放需要时间线 UI；存储空间管理复杂。

**Context:** 日志导出（第9期已做）解决了小场景问题。录制/回放是更完整的方案，需单独设计期次。

**Effort:** L (human) → M (CC+gstack)

**Priority:** P3

**Depends on:** 第9期日志导出功能稳定后评估

---

### [第10期+] 图像标注工具

**What:** 在摄像头图像上绘制检测框、关键点等标注，用于视觉算法调试。

**Why:** 学生实现目标检测时，需要在图像上可视化验证算法输出。

**Pros:** 将算法验证从命令行带入视觉交互界面。

**Cons:** 需 Canvas API 覆盖 `<img>`；标注数据需通过 ROS Topic 传入（与后端算法集成复杂）。

**Context:** 依赖摄像头面板稳定，且需要配套的 ROS 标注话题（如 `visualization_msgs/ImageMarker`）。

**Effort:** XL (human) → L (CC+gstack)

**Priority:** P3

**Depends on:** CameraPanel 稳定 + ROS 视觉话题标准确定
