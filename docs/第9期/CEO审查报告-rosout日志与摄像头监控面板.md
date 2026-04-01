# CEO 审查报告：第9期 — rosout 日志与摄像头监控面板

**审查日期**: 2026-04-01  
**审查模式**: SELECTIVE EXPANSION  
**审查基准**: [SDD-第9期：rosout日志与摄像头监控面板](../../docs/第9期/SDD-第9期：rosout日志与摄像头监控面板.md)  
**当前 commit**: 60a85e2

---

## 一、前提验证

**问题是否正确？** 是。rosout + 摄像头是 ROS 机器人实训最高频调试工具，学生缺少这两个面板等于"盲飞"。

**最直接路径？** 是。基于现有 rosbridge WebSocket 基础设施扩展，零后端改动，路径最短。

**不做的代价？** 学生只能靠 `rostopic echo` 查日志，无摄像头可视化，严重影响实训效果。

---

## 二、SDD 技术偏差（必须修正）

SDD 与项目现有代码存在以下关键偏差，实现前必须对齐：

| # | 偏差项 | SDD 描述 | 应改为 |
|---|--------|----------|--------|
| 1 | 面板注册位置 | `Simulation.vue` | `registry.ts` |
| 2 | ROS URL 来源 | 未提及 | `inject('containerRosUrl', ref(null))` |
| 3 | 设置树管理 | 手动实现 | `usePanelConfig()` composable |
| 4 | 容器状态联动 | 未提及 | `inject('containerStatus', ref(null))` |
| 5 | CompressedImage.data 类型 | `number[]` | `string`（JSON 传输时已是 Base64） |
| 6 | 传输方式 | CBOR（推荐） | JSON（更简单，当前足够） |
| 7 | format 字段解析 | 未处理 | `(message.format\|\|'').split(';')[0].trim()\|\|'jpeg'` |
| 8 | Log ID 生成 | `时间戳 + 随机数` | `${Date.now()}-${_seq++}`（_seq 模块级，重连时重置） |

### 关键类型定义修正

```typescript
// ❌ SDD 错误定义
interface CompressedImage {
  data: number[]  // 错！
}

// ✅ 正确定义（JSON 传输）
interface CompressedImage {
  header: { seq: number; stamp: { secs: number; nsecs: number }; frame_id: string }
  format: string  // "jpeg" | "png" | "rgb8; jpeg compressed bgr8" 等
  data: string    // Base64 字符串，直接用于 <img> src
}

// 正确的 imageSrc 构建
const mimeType = (message.format || '').split(';')[0].trim() || 'jpeg'
imageSrc.value = `data:image/${mimeType};base64,${message.data}`
```

---

## 三、范围决策（SELECTIVE EXPANSION 结果）

### 纳入本期的扩展（共 4 项）

| # | 扩展项 | 理由 | 工作量 |
|---|--------|------|--------|
| 1 | **Topic 名称设置树可配置** | 不同实训环境摄像头 Topic 名不统一，硬编码不可用 | XS |
| 2 | **容器运行状态联动** | 与 KeyboardControl 一致，避免空列表无提示的困惑 | XS |
| 3 | **日志导出为 .log 文件** | 学生上报 bug 的刚需，~20 行代码 | XS |
| 4 | **不改默认布局，仅注册新面板** | 降低对现有学生体验的影响 | XS |

### 延迟到 TODOS.md（共 3 项）

| 项 | 优先级 | 说明 |
|----|--------|------|
| 多摄像头 PiP 布局 | P3 | 架构已支持，UI 设计需单独做 |
| 日志录制与回放 | P3 | 需持久化存储，单独设计期次 |
| Topic 自动发现 | P2 | 调用 rosbridge topic list API |

### 跳过（1 项）

| 项 | 原因 |
|----|------|
| CBOR 传输压缩 | JSON 传输已满足，CBOR 增加 Uint8Array 处理复杂度，收益比低 |

---

## 四、本期完整实现范围

### RosoutPanel

```
panels/RosoutPanel/
├── index.vue               # 主面板
├── settings.ts             # 配置接口 + buildNodes + applyAction
└── composables/
    └── useRosout.ts        # 日志订阅 + 过滤 + 状态管理
```

**功能清单**:
- 实时订阅 `/rosout`（Topic 名称在设置树可配置）
- 日志级别过滤（DEBUG/INFO/WARN/ERROR/FATAL）
- 关键词搜索（trailing-edge debounce 300ms）
- 虚拟滚动（`vue-virtual-scroller`，支持 500+ 条流畅显示）
- 最多保留 500 条（FIFO 删旧，静默）
- 自动滚动：`nextTick().then(() => scrollToBottom())`
- 暂停/恢复接收
- 清空日志
- **[新增]** 日志导出：JSON Lines 格式，文件名 `rosout_YYYYMMDD_HHmmss.log`
- **[新增]** 容器非 running 时显示遮罩 + 禁用操作按钮

### CameraPanel

```
panels/CameraPanel/
├── index.vue               # 主面板
├── settings.ts             # 配置接口 + buildNodes + applyAction
└── composables/
    └── useCamera.ts        # 图像订阅 + FPS 计算
```

**功能清单**:
- 实时订阅 CompressedImage（JSON 传输）
- format 字段安全解析
- FPS 显示（帧到达时间差计算，UI 上限 30fps / 33ms 节流）
- 暂停/恢复
- 截图下载（当前帧保存为图片）
- **[新增]** Topic 名称在设置树可配置
- **[新增]** 容器非 running 时显示遮罩

### 注册与布局

- 在 `registry.ts` 注册两个新面板
- **不修改** `predefined-layouts.ts` 默认布局
- 面板可在用户自定义布局中自由添加

---

## 五、关键实现细节

### useRosout.ts 模式（对齐 KeyboardControl）

```typescript
// ① inject 获取 ROS URL
const containerRosUrl = inject<Ref<string | null>>('containerRosUrl', ref(null))
const containerStatus = inject<Ref<ContainerStatus | null>>('containerStatus', ref(null))

// ② usePanelConfig 接入设置树（含 localStorage 持久化）
const { config } = usePanelConfig(props.panelId, DEFAULT_CONFIG, buildNodes, applyAction)

// ③ Log ID 防 burst 重复
let _seq = 0
const id = `${Date.now()}-${_seq++}`  // _seq 在 onBeforeUnmount 时重置为 0

// ④ 超限 FIFO 删旧
logs.push(entry)
if (logs.length > config.value.maxLogs) logs.shift()

// ⑤ autoScroll
await nextTick()
scrollToBottom()
```

### useCamera.ts 关键片段

```typescript
// FPS 节流
let lastFrameTime = 0
function onMessage(message: CompressedImage) {
  if (paused.value) return
  const now = performance.now()
  if (now - lastFrameTime < 33) return  // 30fps 上限
  lastFrameTime = now

  // format 解析
  const mimeType = (message.format || '').split(';')[0].trim() || 'jpeg'
  imageSrc.value = `data:image/${mimeType};base64,${message.data}`

  // FPS 计算（每秒重置）
  frameCount++
  if (now - lastFpsUpdate >= 1000) {
    fps.value = frameCount
    frameCount = 0
    lastFpsUpdate = now
  }
}
```

### settings.ts 标准结构（以 RosoutPanel 为例）

```typescript
export interface RosoutConfig {
  topic: string
  maxLogs: number
  minLevel: LogLevel
}

export const DEFAULT_CONFIG: RosoutConfig = {
  topic: '/rosout',
  maxLogs: 500,
  minLevel: LogLevel.DEBUG
}

export function buildNodes(config: RosoutConfig): SettingsTreeNodes {
  return {
    general: {
      label: '通用',
      fields: {
        topic: { label: 'Topic', input: 'string', value: config.topic },
        maxLogs: { label: '最大日志条数', input: 'number', value: config.maxLogs, min: 100, max: 2000 },
        minLevel: { label: '最低级别', input: 'select', value: config.minLevel, options: [...] }
      }
    }
  }
}
```

---

## 六、Critical Gaps（实现时必须处理）

| # | 问题 | 具体表现 | 修复方案 |
|---|------|---------|---------|
| 1 | CameraPanel `data` 为空 | `<img>` 显示 broken image | 加 `if (!message.data) return` 检查 |
| 2 | 无帧超 1 秒时 FPS 不重置 | 持续显示过期 FPS 值 | 加 `setInterval` 每秒检查，若无新帧则 `fps.value = 0` |

---

## 七、测试矩阵

| 测试场景 | 类型 | 优先级 | SDD 有？ |
|---------|------|--------|---------|
| 日志实时显示 | 集成 | P1 | ✅ |
| 日志级别过滤 | 单元 | P1 | ✅ |
| 关键词搜索（debounce 300ms） | 单元 | P1 | ✅ |
| 超 500 条自动删旧 | 单元 | P1 | ❌ |
| ROS 断线后重连恢复 | 集成 | P1 | ❌ |
| format 非标准值 fallback | 单元 | P2 | ❌ |
| data 为空时不 crash | 单元 | P1 | ❌ |
| FPS 无帧超 1 秒归零 | 单元 | P2 | ❌ |
| 容器非 running 时显示遮罩 | 集成 | P1 | ✅ |

---

## 八、系统架构图

```
Simulation.vue
  │ provide('containerStatus', ...)
  │ provide('containerRosUrl', ...)
  │
  ├─ GLayout
  │   ├─ RosoutPanel
  │   │   ├─ inject('containerRosUrl', 'containerStatus')
  │   │   ├─ usePanelConfig(DEFAULT_CONFIG, buildNodes, applyAction)
  │   │   └─ roslib.Topic('/rosout', 'rosgraph_msgs/Log')
  │   │         │ WebSocket
  │   │         ▼ useRosout: logs[] → 过滤 → virtual-scroller
  │   │
  │   └─ CameraPanel
  │       ├─ inject('containerRosUrl', 'containerStatus')
  │       ├─ usePanelConfig(DEFAULT_CONFIG, buildNodes, applyAction)
  │       └─ roslib.Topic('/camera/...', 'sensor_msgs/CompressedImage')
  │             │ WebSocket (JSON, data=Base64 string)
  │             ▼ useCamera: imageSrc → <img>
  │
  └─ registry.ts ← 两个新面板注册于此（不改默认布局）
```

---

## 九、实施前提核查清单

- [ ] `pnpm add vue-virtual-scroller` 安装并验证 Vue 3 兼容（备选 `@tanstack/vue-virtual`）
- [ ] 本地 rosbridge 环境验证 `/rosout` 可正常推送
- [ ] 本地 rosbridge 环境验证 `/camera/rgb/image_raw/compressed` 可正常推送图像
- [ ] 500 条 mock 数据验证 virtual-scroller <16ms 帧预算

---

## 十、延迟工作（已写入 TODOS.md）

详见 [TODOS.md](../../TODOS.md)：

- P2: Topic 自动发现（调用 rosbridge topic list API）
- P3: 多摄像头 PiP 布局
- P3: rosout 日志录制与回放
- P3: 图像标注工具

---

## 十一、审查结论

| 维度 | 结论 |
|------|------|
| 需求方向 | ✅ 正确 |
| SDD 技术偏差 | ⚠ 8 处，已记录（见第二节）|
| 本期范围 | ✅ 合理，4 项 cherry-pick 纳入 |
| Critical Gaps | ⚠ 2 处（data 为空、FPS 无帧归零）|
| 可逆性 | ✅ 5/5（纯新增文件） |
| 部署风险 | ✅ 极低 |
| **建议** | 可进入实现，工程审查已完成（见第十二节） |

---

## 十二、工程审查结论（/plan-eng-review 已完成）

**审查日期**: 2026-04-01 | **审查文档**: [工程审查报告](./工程审查报告-rosout日志与摄像头监控面板.md)

| 维度 | 结论 | 关键行动 |
|------|------|---------|
| 架构设计 | ✅ 合理 | 与 KeyboardControl 模式完全对齐 |
| 内存泄漏 | ⚠ P0 风险 | `onBeforeUnmount` 清理 ros/topic/interval 必须实现 |
| 虚拟滚动 | ✅ 已移除 | 500 条普通列表，零依赖 |
| `_seq` 作用域 | ⚠ 建议修正 | 移入 composable 函数体（闭包），非模块级 |
| FPS 归零 | ✅ 方案确认 | `setInterval` 每秒检查，1.5s 无帧归零 |
| 日志导出 | ✅ 方案确认 | JSON Lines + `URL.revokeObjectURL` 立即释放 |
| 可逆性 | ✅ 5/5 | 全为新增文件 |
| **实现顺序** | settings.ts → useRosout → RosoutPanel → LogItem → useCamera → CameraPanel → registry.ts ||
