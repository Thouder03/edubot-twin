# 工程审查报告：第9期 — rosout 日志与摄像头监控面板

**审查日期**: 2026-04-01  
**审查基准**: [CEO审查报告](./CEO审查报告-rosout日志与摄像头监控面板.md)  
**当前 commit**: 60a85e2  
**分支**: master

---

## 一、范围确认

| 决策项 | 结论 |
|--------|------|
| 虚拟滚动 | ❌ 不引入。500 条限制内用 `v-for` 普通列表，零依赖。`vue-virtual-scroller@1.x` 仅支持 Vue 2，Vue 3 需 `@next` — 版本陷阱风险高于收益 |
| 新增文件 | 7 个新文件 + 2 个修改（`registry.ts`、`package.json` 无改动） |
| 新增依赖 | 无 |

**完整文件清单**：

```
panels/RosoutPanel/
├── index.vue                # 主面板 + 遮罩 + 工具栏
├── settings.ts              # 接口 + DEFAULT_CONFIG + buildNodes + applyAction
├── composables/
│   └── useRosout.ts         # ROS 订阅 + 过滤 + 导出
└── LogItem.vue              # 单条日志行（提高可测性）

panels/CameraPanel/
├── index.vue                # 主面板 + 遮罩 + 帧显示
├── settings.ts
└── composables/
    └── useCamera.ts         # ROS 订阅 + FPS 计算 + 截图

panels/registry.ts           # [修改] 注册两个新面板
```

---

## 二、架构审查

### 2.1 组件边界 — 合理

| 组件 | 职责 | 评估 |
|------|------|------|
| `index.vue` | 布局 + 遮罩 + UI 事件绑定 | ✅ 薄 |
| `useRosout.ts` | ROS 连接 + 日志缓冲 + 过滤 + 导出状态 | ✅ 清晰 |
| `useCamera.ts` | ROS 连接 + imageSrc + FPS | ✅ 清晰 |
| `settings.ts` | 配置接口 + `buildNodes` + `applyAction` | ✅ 纯函数 |
| `LogItem.vue` | 单行渲染 | ✅ 利于隔离测试 |

**无循环依赖**。composable 不依赖 view，settings 不依赖 composable。

### 2.2 ROS 连接模式 — 与 KeyboardControl 完全对齐

```typescript
// ✅ 标准接入（与 KeyboardControl/index.vue 一致）
const containerRosUrl = inject<Ref<string | null>>('containerRosUrl', ref(null))
const containerStatus = inject<Ref<ContainerStatus | null>>('containerStatus', ref(null))

let ros: Ros | null = null

function connectRos() {
  if (!containerRosUrl.value) return
  ros?.close()
  ros = new Ros({ url: containerRosUrl.value })
  ros.on('connection', () => subscribe())
  ros.on('error', () => { /* noop */ })
  ros.on('close', () => { /* noop */ })
}

watch(containerRosUrl, (url) => {
  if (url) connectRos()
})
```

### 2.3 设置树接入 — 符合规范

```typescript
// ✅ 必须显式调用 registerPanel（usePanelConfig 不做此事）
onMounted(() => {
  registerPanel(props.panelId, 'RosoutPanel')
  // usePanelConfig 在调用时已通过 watch(immediate:true) 注册设置树
})

onBeforeUnmount(() => {
  unregisterPanel(props.panelId)
})
```

`usePanelConfig` 签名已确认：`usePanelConfig(panelId, DEFAULT_CONFIG, buildNodes, applyAction)` — 4 个参数，返回 `{ config: Ref<T> }`。

### 2.4 settings.ts 标准结构

`SettingsTreeAction` 类型已确认两种变体：`'update'` 和 `'perform-node-action'`。`applyAction` 必须处理 `action.action !== 'update'` 的情况（直接返回 config 不变即可）。

```typescript
export function applyAction(config: RosoutConfig, action: SettingsTreeAction): RosoutConfig {
  if (action.action !== 'update') return config
  const { path, value } = action.payload
  // path = ['general', 'topic'] | ['general', 'maxLogs'] | ['general', 'minLevel']
  return { ...config, [path[1]]: value }
}
```

---

## 三、代码质量审查

### 3.1 内存泄漏风险（P0，必须修复）

以下资源若在 `onBeforeUnmount` 中未清理，会在面板关闭后持续运行：

| 资源 | 泄漏场景 | 修复 |
|------|---------|------|
| `ros.close()` | 面板卸载时 WebSocket 连接不关闭 | `onBeforeUnmount(() => ros?.close())` |
| `topic.unsubscribe()` | ROS Topic 订阅不取消 | `onBeforeUnmount(() => topicSub?.unsubscribe())` |
| `setInterval` (FPS 归零) | interval 不清除 → 每秒继续执行 | `onBeforeUnmount(() => clearInterval(fpsResetTimer))` |
| `URL.revokeObjectURL` | 日志导出后 Blob URL 不释放 | 下载后立即调用 `URL.revokeObjectURL(url)` |

**useRosout.ts 最小清理模板**：

```typescript
let ros: Ros | null = null
let topicSub: Topic | null = null

onBeforeUnmount(() => {
  topicSub?.unsubscribe()
  topicSub = null
  ros?.close()
  ros = null
})
```

**useCamera.ts 最小清理模板**：

```typescript
let fpsResetTimer: ReturnType<typeof setInterval> | null = null

onBeforeUnmount(() => {
  topicSub?.unsubscribe()
  ros?.close()
  ros = null
  if (fpsResetTimer) {
    clearInterval(fpsResetTimer)
    fpsResetTimer = null
  }
})
```

### 3.2 Log ID `_seq` — 作用域问题

CEO 报告中描述 `_seq` 为"模块级变量，重连时重置为 0"，但**模块级**有副作用：多个 RosoutPanel 实例共享同一 `_seq`，导致 ID 跨实例连续计数（不影响正确性，但语义误导）。

**建议**：`_seq` 定义在 composable 函数体内（闭包），而非模块顶层。每个面板实例独立计数，卸载时自然丢弃，无需显式重置。

```typescript
// ✅ composable 函数体内
export function useRosout(panelId: string) {
  let _seq = 0
  // ...
}
```

### 3.3 FPS 计算 — 需补充 setInterval 归零

CEO 报告已识别此问题（Critical Gap #2）。具体实现：

```typescript
// useCamera.ts
let fpsResetTimer: ReturnType<typeof setInterval> | null = null
let lastFrameTime = 0

onMounted(() => {
  fpsResetTimer = setInterval(() => {
    // 若超过 1.5s 没有新帧，fps 归零
    if (performance.now() - lastFrameTime > 1500) {
      fps.value = 0
      frameCount = 0
    }
  }, 1000)
})

// onBeforeUnmount 中 clearInterval（见 3.1）
```

### 3.4 日志导出 — 时间戳格式

`rosout_YYYYMMDD_HHmmss.log` 格式，使用 Date API：

```typescript
function exportLogs() {
  const now = new Date()
  const ts = now.toISOString().replace(/[-:T]/g, '').slice(0, 15).replace('.', '')
  // 或者更直接：
  const pad = (n: number) => String(n).padStart(2, '0')
  const filename = `rosout_${now.getFullYear()}${pad(now.getMonth()+1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}.log`

  const content = logs.value.map(l => JSON.stringify(l)).join('\n')
  const blob = new Blob([content], { type: 'text/plain' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)  // ← 立即释放
}
```

### 3.5 空数据保护 — Critical Gap #1

```typescript
// useCamera.ts — onMessage 内
function onMessage(message: CompressedImage) {
  if (!message.data) return  // ← 防 broken image
  if (paused.value) return
  // ...
}
```

### 3.6 类型安全

`SettingsTreeField.value` 当前是 `any`（见 `settings.ts:24`），这是现有类型系统的已知限制。`applyAction` 收到的 `value` 类型是 `any`，实现时无需额外断言，保持与现有 settings 一致即可。

---

## 四、测试审查

### 4.1 测试框架现状

**项目当前无测试框架**（`vitest`/`jest` 未在 devDeps 中）。本期不引入测试框架，改为人工测试检查清单。

### 4.2 测试矩阵（人工验证）

```
RosoutPanel
┌─────────────────────────────────────────┬──────┬─────────────────────┐
│ 场景                                     │ 优先 │ 验证方法             │
├─────────────────────────────────────────┼──────┼─────────────────────┤
│ 日志实时显示（连接 rosbridge 后收到消息） │  P1  │ 手动连接            │
│ 日志级别过滤（切换 DEBUG/INFO/WARN 等）  │  P1  │ 手动点击过滤按钮     │
│ 关键词搜索（输入后 300ms 触发过滤）       │  P1  │ 手动输入             │
│ 超 500 条自动删旧（不提示）              │  P1  │ mock 脚本注入 501 条 │
│ 日志导出（下载 .log 文件，格式正确）      │  P1  │ 手动点击导出         │
│ ROS 断线后重连恢复                       │  P1  │ 手动断开 rosbridge   │
│ 容器非 running 时显示遮罩                │  P1  │ 切换容器状态         │
│ 面板卸载后无内存泄漏（无 console.error） │  P1  │ 关闭面板后观察控制台  │
│ format 非标准值 fallback 到 jpeg        │  P2  │ 单元函数直接测试      │
│ FPS 无帧超 1.5s 归零                    │  P2  │ 暂停 rosbridge 观察   │
└─────────────────────────────────────────┴──────┴─────────────────────┘

CameraPanel
┌─────────────────────────────────────────┬──────┬─────────────────────┐
│ 场景                                     │ 优先 │ 验证方法             │
├─────────────────────────────────────────┼──────┼─────────────────────┤
│ 图像实时显示（连接 rosbridge）           │  P1  │ 手动连接            │
│ data 为空时不 crash                      │  P1  │ mock 空消息          │
│ FPS 显示正确（连续帧时 >0）              │  P1  │ 手动连接观察         │
│ FPS 无帧超 1.5s 归零                    │  P1  │ 暂停 rosbridge       │
│ 截图下载（图片内容正确）                  │  P1  │ 手动点击截图         │
│ 暂停 / 恢复（帧停止 / 恢复更新）         │  P1  │ 手动点击暂停         │
│ Topic 名称可配置（切换 Topic 后重订阅）  │  P1  │ 设置树修改           │
│ 容器非 running 时显示遮罩                │  P1  │ 切换容器状态         │
└─────────────────────────────────────────┴──────┴─────────────────────┘
```

---

## 五、性能审查

### 5.1 500 条普通列表

在 Golden Layout 面板内，500 条 × ~40px/条 = 20,000px DOM 高度。

- 面板一般高度 300-600px，可见区域约 10-15 条
- 500 条 DOM 节点：现代浏览器 layout/paint 耗时约 5-10ms（远低于 16ms 帧预算）
- **结论**: 可接受，无需虚拟滚动

### 5.2 关键词搜索 debounce

`v-for` + `computed` 过滤在 500 条 × 字符串 includes 下约 0.1-0.5ms，远低于感知阈值。debounce 300ms 主要是减少 Vue watcher 触发频率，非必要但是好习惯。

### 5.3 摄像头 33ms 节流

rosbridge JSON 传输下，`sensor_msgs/CompressedImage` 每帧约 30-200KB（取决于分辨率）。33ms 帧间隔（30fps）与典型网络带宽匹配。

**注意**: 33ms 节流仅控制 `<img>` src 更新频率，不控制 rosbridge 消息接收速率。高帧率摄像头（60fps）时，每秒约有 30 帧被 `return` 丢弃，这是正常的。不要在 `onMessage` 中 `unsubscribe` — 仅 `return` 跳过处理即可。

### 5.4 日志 burst 场景

500 条 FIFO + 300ms debounce 搜索 + nextTick autoScroll，理论最坏情况（500条/秒持续输入）：

- `logs.shift()` 是 O(n)，500 条规模下约 0.1ms — 可接受
- 如出现卡顿（概率低），加 requestAnimationFrame throttle 即可，本期暂不做

---

## 六、故障模式分析

| 故障 | 触发条件 | 现象 | 处理方式 |
|------|---------|------|---------|
| rosbridge 未启动 | 容器内 rosbridge 服务未运行 | 遮罩提示（容器状态非 running） | 遮罩覆盖，无 crash |
| WebSocket 断线 | 网络抖动 | 日志/画面停止更新 | `containerRosUrl` watch 重连 |
| CompressedImage.data 为空 | 摄像头驱动异常帧 | broken image（若未检查） | `if (!message.data) return` |
| format 字段非标准 | 自定义摄像头驱动 | MIME 类型错误，图片无法显示 | split+trim+fallback 'jpeg' |
| 面板快速关闭/重开 | 用户快速操作 | 旧 Ros 实例未清理，双重订阅 | `onBeforeUnmount` 清理 + `ros?.close()` |
| localStorage 配额超出 | 极少 | `usePanelConfig` catch 并 warn | 已处理（见 `usePanelConfig.ts:45-48`） |
| 500 条以上日志 | 高频 rosout | FIFO 静默删旧 | `logs.shift()`，无提示（符合 UX 惯例） |

---

## 七、实施前提核查清单

- [ ] `registry.ts` 中确认两个新 `componentType` key（`RosoutPanel`, `CameraPanel`）与 `registerPanel` 调用时传入的 name 完全一致
- [ ] `inject('containerRosUrl')` 已在 `Simulation.vue` 的 `provide` 中注册（对照 KeyboardControl 正常工作可验证）
- [ ] 本地 rosbridge 环境验证 `/rosout` 可收到消息（`rostopic echo /rosout`）
- [ ] 本地摄像头 Topic 名称确认（默认 `/camera/rgb/image_raw/compressed`，可通过设置树修改）
- [ ] 面板卸载后检查浏览器 DevTools → Console，确认无 `WebSocket is already in CLOSING or CLOSED state` 警告

---

## 八、不在范围内（本期跳过）

以下内容已由 CEO 审查决策，工程审查确认维持：

| 项 | 理由 |
|----|------|
| 虚拟滚动 | `vue-virtual-scroller@1.x` 是 Vue 2；`@next` 未经项目验证；500 条普通列表足够 |
| CBOR 传输 | rosbridge 默认 JSON，data 已是 Base64 string，无需 CBOR |
| Topic 自动发现 | 需 `ros.getTopics()` API，工作量超出本期，已记入 TODOS.md（P2） |
| 多摄像头 PiP | 架构支持，UI 设计待单独期次，已记入 TODOS.md（P3） |
| 测试框架 | 引入 vitest 超出本期范围，改用人工检查清单 |

---

## 九、设计验证（关键实现片段）

### useRosout.ts 骨架

```typescript
import { ref, computed, inject, onMounted, onBeforeUnmount, watch, nextTick, type Ref } from 'vue'
import { Ros, Topic } from 'roslib'
import { usePanelConfig } from '../../../composables/usePanelConfig'
import { usePanelState } from '../../../stores/panelState'
import { DEFAULT_CONFIG, buildNodes, applyAction } from '../settings'
import type { ContainerStatus } from '@/api/container/types'

export interface RosoutLog {
  id: string
  level: number
  msg: string
  name: string
  stamp: { secs: number; nsecs: number }
}

export function useRosout(panelId: string, logListEl: Ref<HTMLElement | null>) {
  const containerRosUrl = inject<Ref<string | null>>('containerRosUrl', ref(null))
  const containerStatus = inject<Ref<ContainerStatus | null>>('containerStatus', ref(null))
  const isRunning = computed(() => containerStatus.value === 'running')

  const { config } = usePanelConfig(panelId, DEFAULT_CONFIG, buildNodes, applyAction)
  const { registerPanel, unregisterPanel } = usePanelState()

  const logs = ref<RosoutLog[]>([])
  const paused = ref(false)
  const keyword = ref('')
  let _seq = 0

  const filteredLogs = computed(() => {
    let result = logs.value.filter(l => l.level >= config.value.minLevel)
    if (keyword.value.trim()) {
      const kw = keyword.value.trim().toLowerCase()
      result = result.filter(l => l.msg.toLowerCase().includes(kw) || l.name.toLowerCase().includes(kw))
    }
    return result
  })

  let ros: Ros | null = null
  let topicSub: Topic | null = null

  function subscribe() {
    if (!ros) return
    topicSub = new Topic({ ros, name: config.value.topic, messageType: 'rosgraph_msgs/Log' })
    topicSub.subscribe((msg: any) => {
      if (paused.value) return
      if (msg.level < config.value.minLevel) return

      const entry: RosoutLog = {
        id: `${Date.now()}-${_seq++}`,
        level: msg.level,
        msg: msg.msg,
        name: msg.name,
        stamp: msg.header?.stamp ?? { secs: 0, nsecs: 0 }
      }
      logs.value.push(entry)
      if (logs.value.length > config.value.maxLogs) logs.value.shift()

      nextTick(() => {
        logListEl.value?.scrollTo({ top: logListEl.value.scrollHeight })
      })
    })
  }

  function connectRos() {
    if (!containerRosUrl.value) return
    topicSub?.unsubscribe()
    ros?.close()
    ros = new Ros({ url: containerRosUrl.value })
    ros.on('connection', () => subscribe())
    ros.on('error', () => {})
    ros.on('close', () => {})
  }

  watch(containerRosUrl, (url) => { if (url) connectRos() })

  // Topic 变化时重订阅
  watch(() => config.value.topic, () => {
    topicSub?.unsubscribe()
    if (ros) subscribe()
  })

  function clearLogs() { logs.value = [] }

  function exportLogs() {
    const pad = (n: number) => String(n).padStart(2, '0')
    const now = new Date()
    const filename = `rosout_${now.getFullYear()}${pad(now.getMonth()+1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}.log`
    const content = logs.value.map(l => JSON.stringify(l)).join('\n')
    const blob = new Blob([content], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = filename; a.click()
    URL.revokeObjectURL(url)
  }

  onMounted(() => {
    registerPanel(panelId, 'RosoutPanel')
    if (containerRosUrl.value) connectRos()
  })

  onBeforeUnmount(() => {
    topicSub?.unsubscribe()
    topicSub = null
    ros?.close()
    ros = null
    unregisterPanel(panelId)
  })

  return { config, logs, filteredLogs, paused, keyword, isRunning, clearLogs, exportLogs }
}
```

### useCamera.ts 骨架

```typescript
export interface CompressedImage {
  header: { seq: number; stamp: { secs: number; nsecs: number }; frame_id: string }
  format: string
  data: string  // Base64 string (JSON transport)
}

export function useCamera(panelId: string) {
  // ... inject, usePanelConfig, registerPanel ...
  const imageSrc = ref<string | null>(null)
  const fps = ref(0)
  const paused = ref(false)
  let frameCount = 0
  let lastFpsUpdate = 0
  let lastFrameTime = 0
  let fpsResetTimer: ReturnType<typeof setInterval> | null = null

  function onMessage(message: CompressedImage) {
    if (!message.data) return
    if (paused.value) return
    const now = performance.now()
    if (now - lastFrameTime < 33) return
    lastFrameTime = now

    const mimeType = (message.format || '').split(';')[0].trim() || 'jpeg'
    imageSrc.value = `data:image/${mimeType};base64,${message.data}`

    frameCount++
    if (now - lastFpsUpdate >= 1000) {
      fps.value = frameCount
      frameCount = 0
      lastFpsUpdate = now
    }
  }

  onMounted(() => {
    registerPanel(panelId, 'CameraPanel')
    if (containerRosUrl.value) connectRos()
    fpsResetTimer = setInterval(() => {
      if (performance.now() - lastFrameTime > 1500) { fps.value = 0; frameCount = 0 }
    }, 1000)
  })

  onBeforeUnmount(() => {
    topicSub?.unsubscribe(); ros?.close(); ros = null
    if (fpsResetTimer) { clearInterval(fpsResetTimer); fpsResetTimer = null }
    unregisterPanel(panelId)
  })

  function screenshot() {
    if (!imageSrc.value) return
    const a = document.createElement('a')
    a.href = imageSrc.value
    a.download = `camera_${Date.now()}.jpg`
    a.click()
  }

  return { config, imageSrc, fps, paused, isRunning, screenshot }
}
```

---

## 十、审查结论

| 维度 | 结论 | 备注 |
|------|------|------|
| 架构设计 | ✅ 合理 | 与 KeyboardControl 模式完全对齐 |
| 内存泄漏 | ⚠ 高风险 | `onBeforeUnmount` 清理是 P0，必须实现 |
| 代码质量 | ✅ 路径清晰 | `_seq` 建议移入 composable 函数体 |
| 类型安全 | ✅ 关键修正已记录 | `CompressedImage.data: string` 已明确 |
| 性能 | ✅ 满足 | 500 条普通列表 + 33ms 节流足够 |
| 故障覆盖 | ✅ 主要场景已处理 | 空 data、format fallback、断线重连 |
| 测试 | ⚠ 无框架 | 改用人工检查清单（第四节） |
| 可逆性 | ✅ 5/5 | 全为新增文件，`registry.ts` 改动可回滚 |
| **建议** | **可进入实现** | P0：先实现 `onBeforeUnmount` 清理，再写功能 |

**实现顺序建议**：

1. `settings.ts` × 2（纯函数，最简单，先验证 `usePanelConfig` 集成）
2. `useRosout.ts`（含 onBeforeUnmount 清理）
3. `RosoutPanel/index.vue`（遮罩 + 列表 + 工具栏）
4. `LogItem.vue`
5. `useCamera.ts`（含 FPS timer 清理）
6. `CameraPanel/index.vue`
7. `registry.ts` — 最后注册，完成后验证两个面板可在布局中添加
