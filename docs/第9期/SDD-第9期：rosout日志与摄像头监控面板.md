# SDD-第九期：rosout 日志与摄像头监控面板

**文档版本**: v1.2
**创建日期**: 2026-03-29
**修订日期**: 2026-04-01
**目标**: 实现 ROS 日志实时显示和摄像头图像监控功能

---

## 一、需求概述

### 1.1 核心需求

1. **rosout 日志面板**: 实时订阅并显示 ROS 系统日志
2. **摄像头监控面板**: 订阅摄像头 Topic 并显示实时图像
3. **面板集成**: 作为独立面板集成到仿真页面的 Golden Layout 中

### 1.2 设计原则

- 实时性：WebSocket 订阅，低延迟显示
- 可过滤：支持日志级别过滤、关键词搜索
- 轻量级：避免大量日志导致前端卡顿
- 复用组件：使用现有 ROS 连接基础设施

---

## 二、系统架构

### 2.1 整体架构图

```mermaid
graph TB
    subgraph ROS 容器
        A[ROS Master]
        B[rosout 节点]
        C[摄像头节点]
    end
    
    subgraph rosbridge
        D[rosbridge_server]
    end
    
    subgraph 前端面板
        E[RosoutPanel]
        F[CameraPanel]
        G[useRos Hook]
    end
    
    B -->|/rosout| D
    C -->|/camera/image_raw| D
    D -->|WebSocket| G
    G --> E
    G --> F
```

### 2.2 数据流时序图

```mermaid
sequenceDiagram
    participant R as ROS 节点
    participant B as rosbridge
    participant W as WebSocket
    participant V as Vue 组件
    participant U as 用户界面

    Note over R,U: rosout 日志流程
    R->>B: 发布 /rosout 消息
    B->>W: 推送 JSON 消息
    W->>V: onMessage 回调
    V->>V: 过滤 + 格式化
    V->>U: 渲染日志行

    Note over R,U: 摄像头图像流程
    R->>B: 发布 /camera/image_raw/compressed
    B->>W: 推送 JSON 消息（data 为 Base64 string）
    W->>V: onMessage 回调
    V->>V: format 解析 + Data URL 拼接
    V->>U: 更新 <img> src
```

---

## 三、数据库设计

### 3.1 无需新增数据表

本模块不需要数据库支持，所有数据通过 ROS Topics 实时传输。

---

## 四、后端 API 设计

### 4.1 无需新增后端 API

本模块完全基于 rosbridge WebSocket，无需后端 API。

### 4.2 依赖的 ROS Topics

| Topic | 消息类型 | 说明 |
|-------|---------|------|
| `/rosout` | `rosgraph_msgs/Log` | ROS 系统日志 |
| `/camera/rgb/image_raw` | `sensor_msgs/Image` | 摄像头原始图像 |
| `/camera/rgb/image_raw/compressed` | `sensor_msgs/CompressedImage` | 压缩图像（推荐） |

---

## 五、前端组件设计

### 5.1 组件结构

```
edubot-twin-web/src/views/Simulation/panels/
├── RosoutPanel/
│   ├── index.vue                 # 主面板
│   ├── LogItem.vue               # 单条日志组件
│   ├── settings.ts               # 配置接口 + buildNodes + applyAction
│   └── composables/
│       └── useRosout.ts          # 日志订阅逻辑
├── CameraPanel/
│   ├── index.vue                 # 主面板
│   ├── settings.ts               # 配置接口 + buildNodes + applyAction
│   └── composables/
│       └── useCamera.ts          # 图像订阅逻辑
└── registry.ts                   # 面板注册（本期修改）
```

---

## 六、rosout 日志面板详细设计

### 6.1 ROS 消息结构

**Topic**: `/rosout`  
**类型**: `rosgraph_msgs/Log`

```typescript
interface RosoutMessage {
  header: {
    seq: number
    stamp: { secs: number; nsecs: number }
    frame_id: string
  }
  level: number  // 1=DEBUG, 2=INFO, 4=WARN, 8=ERROR, 16=FATAL
  name: string   // 节点名称
  msg: string    // 日志内容
  file: string   // 源文件
  function: string
  line: number
  topics: string[]
}
```

### 6.2 日志级别映射

```typescript
enum LogLevel {
  DEBUG = 1,
  INFO = 2,
  WARN = 4,
  ERROR = 8,
  FATAL = 16
}

const LOG_LEVEL_MAP = {
  1: { label: 'DEBUG', color: '#909399', icon: 'bug' },
  2: { label: 'INFO', color: '#409EFF', icon: 'info-filled' },
  4: { label: 'WARN', color: '#E6A23C', icon: 'warning-filled' },
  8: { label: 'ERROR', color: '#F56C6C', icon: 'circle-close-filled' },
  16: { label: 'FATAL', color: '#F56C6C', icon: 'circle-close-filled' }
}
```

### 6.3 组件状态设计

```typescript
interface RosoutState {
  logs: LogEntry[]           // 日志列表
  maxLogs: number           // 最大保留条数（默认 500）
  filterLevel: LogLevel[]   // 过滤级别
  filterKeyword: string     // 关键词过滤
  autoScroll: boolean       // 自动滚动到底部
  paused: boolean           // 暂停接收
}

interface LogEntry {
  id: string                // 唯一 ID
  timestamp: Date
  level: LogLevel
  node: string
  message: string
  file?: string
  line?: number
}
```

### 6.4 核心功能实现

**useRosout.ts 核心逻辑伪代码**:

```
FUNCTION useRosout(panelId):
    注入:
        containerRosUrl = inject('containerRosUrl', ref(null))
        containerStatus = inject('containerStatus', ref(null))

    配置:
        config = usePanelConfig(panelId, DEFAULT_CONFIG, buildNodes, applyAction)

    初始化状态:
        logs = 空数组
        paused = false
        _seq = 0  # composable 函数体内（实例级闭包）

    FUNCTION connectRos(url):
        建立 Ros 连接
        连接成功后订阅 Topic(config.topic)

    监听消息回调:
        IF paused THEN 返回

        创建日志条目 {
            id: `${Date.now()}-${_seq++}`,
            timestamp: 从消息头提取时间,
            level: 消息.level,
            node: 消息.name,
            message: 消息.msg,
            file: 消息.file,
            line: 消息.line
        }

        添加到 logs 数组
        IF logs.length > config.maxLogs THEN
            移除最旧的日志（FIFO）
        END IF

    FUNCTION onBeforeUnmount():
        topic.unsubscribe()
        ros.close()
        unregisterPanel(panelId)

    返回 { logs, paused, connectRos, clear, exportLogs }
END FUNCTION
```

### 6.5 UI 设计

**布局结构**:
```
┌─ Rosout 日志 ────────────────────────────────────┐
│ [🔍 搜索] [DEBUG] [INFO] [WARN] [ERROR] [清空]   │
├──────────────────────────────────────────────────┤
│ 10:30:15 [INFO] /move_base: Goal received        │
│ 10:30:16 [WARN] /amcl: Laser scan timeout        │
│ 10:30:17 [ERROR] /rosout: Connection lost        │
│ ...                                              │
│ (自动滚动到底部)                                  │
└──────────────────────────────────────────────────┘
```

**关键特性**:
- 普通列表渲染：`v-for` 渲染 + 500 条上限（不引入虚拟滚动依赖）
- 颜色编码：不同级别使用不同颜色
- 时间戳：显示相对时间或绝对时间
- 节点过滤：点击节点名快速过滤
- 日志导出：JSON Lines 格式，下载为 `.log` 文件
- 状态联动：容器非 running 时显示遮罩并禁用操作

---

## 七、摄像头监控面板详细设计

### 7.1 ROS 消息结构

**Topic**: `/camera/rgb/image_raw/compressed`  
**类型**: `sensor_msgs/CompressedImage`

```typescript
interface CompressedImage {
  header: {
    seq: number
    stamp: { secs: number; nsecs: number }
    frame_id: string
  }
  format: string  // "jpeg" | "png" | "rgb8; jpeg compressed bgr8" 等
  data: string    // JSON 传输下为 Base64 字符串
}
```

### 7.2 组件状态设计

```typescript
interface CameraState {
  imageSrc: string          // 图像 Data URL
  fps: number               // 当前帧率
  lastUpdate: Date          // 最后更新时间
  quality: 'low' | 'medium' | 'high'  // 图像质量
  paused: boolean
}
```

### 7.3 核心功能实现

**useCamera.ts 核心逻辑伪代码**:

```
FUNCTION useCamera(panelId):
    注入:
        containerRosUrl = inject('containerRosUrl', ref(null))
        containerStatus = inject('containerStatus', ref(null))

    配置:
        config = usePanelConfig(panelId, DEFAULT_CONFIG, buildNodes, applyAction)

    初始化状态:
        imageSrc = 空字符串
        fps = 0
        paused = false
        frameCount = 0
        lastFpsUpdate = 当前时间
        lastFrameTime = 0

    FUNCTION subscribe(ros连接, topic名称):
        创建 Topic 订阅 {
            名称: topic名称,
            类型: 'sensor_msgs/CompressedImage'
        }

        监听消息回调:
            IF !message.data THEN 返回  # Critical Gap: 防 broken image
            IF paused THEN 返回

            当前时间 = 获取当前时间
            IF 当前时间 - lastFrameTime < 33毫秒 THEN 返回  # 30fps 节流
            lastFrameTime = 当前时间

            mimeType = (message.format || '').split(';')[0].trim() || 'jpeg'
            imageSrc = "data:image/" + mimeType + ";base64," + message.data

            frameCount++
            IF 当前时间 - lastFpsUpdate >= 1000毫秒 THEN
                fps = frameCount
                frameCount = 0
                lastFpsUpdate = 当前时间
            END IF
        END 监听
    END FUNCTION

    FUNCTION startFpsResetTimer():
        每秒检查一次
        IF 超过 1.5 秒没有新帧 THEN
            fps = 0
            frameCount = 0
        END IF

    FUNCTION onBeforeUnmount():
        topic.unsubscribe()
        ros.close()
        clearInterval(fpsResetTimer)
        unregisterPanel(panelId)

    返回 { imageSrc, fps, paused, subscribe, screenshot }
END FUNCTION
```

### 7.4 UI 设计

**布局结构**:
```
┌─ 摄像头监控 ─────────────────────────────────────┐
│ Topic: /camera/rgb/image_raw/compressed  FPS: 30 │
├──────────────────────────────────────────────────┤
│                                                  │
│          [摄像头图像显示区域]                     │
│                                                  │
│                                                  │
├──────────────────────────────────────────────────┤
│ [⏸ 暂停] [📷 截图] [🔄 刷新]                     │
└──────────────────────────────────────────────────┘
```

**关键特性**:
- 自适应缩放：图像自动适应面板大小
- 帧率显示：实时显示当前 FPS（无帧超 1.5s 自动归零）
- 截图功能：保存当前帧为图片
- Topic 可配置：通过设置树切换订阅 Topic
- 状态联动：容器非 running 时显示遮罩

---

## 八、Golden Layout 集成

### 8.1 面板注册

**修改位置**: `edubot-twin-web/src/views/Simulation/panels/registry.ts`

**注册伪代码**:
```
registerPanel('RosoutPanel', RosoutPanel)
registerPanel('CameraPanel', CameraPanel)
```

### 8.2 默认布局配置

本期**不修改默认布局**（`predefined-layouts.ts` 保持不变），仅完成面板注册，允许用户在自定义布局中按需添加。

---

## 九、性能优化

### 9.1 日志面板优化

| 优化项 | 方案 | 效果 |
|--------|------|------|
| 列表渲染 | `v-for` 普通列表（500 条上限） | 零依赖、维护成本低 |
| 日志限制 | 最多保留 500 条 | 防止内存溢出 |
| 暂停接收 | paused 状态 | 调试时冻结日志 |
| 防抖过滤 | debounce 300ms | 减少重复渲染 |

### 9.2 摄像头面板优化

| 优化项 | 方案 | 效果 |
|--------|------|------|
| 压缩传输 | CompressedImage（JSON） | 带宽减少 80% |
| 帧率限制 | throttle 30fps | 避免过度渲染 |
| 图像缓存 | 复用 Data URL | 减少字符串处理 |
| Topic 配置 | 设置树切换 Topic | 适配不同实训环境 |

---

## 十、实施计划

### 10.1 开发任务分解

| 任务 | 预估工时 | 优先级 |
|------|---------|--------|
| RosoutPanel / CameraPanel settings.ts | 0.5 天 | P1 |
| useRosout.ts（含 onBeforeUnmount 清理） | 0.5 天 | P1 |
| RosoutPanel + LogItem.vue | 0.5 天 | P1 |
| useCamera.ts（含 FPS 归零定时器清理） | 0.5 天 | P1 |
| CameraPanel + registry.ts 注册 | 0.5 天 | P1 |
| 人工测试矩阵执行 | 0.5 天 | P1 |

**总计**: 约 3 天

### 10.2 测试用例

| 测试场景 | 操作 | 预期结果 |
|---------|------|---------|
| 订阅 rosout | 启动 ROS 节点 | 日志实时显示 |
| 日志过滤 | 选择 ERROR 级别 | 仅显示错误日志 |
| 关键词搜索 | 输入 "move_base" | 300ms 后生效 |
| 超 500 条自动删旧 | 注入 501 条日志 | 最旧日志被静默移除 |
| ROS 断线后重连 | 手动断开后恢复 rosbridge | 日志/画面可恢复更新 |
| 日志导出 | 点击导出按钮 | 下载 JSON Lines `.log` 文件 |
| data 为空保护 | 注入空 data 消息 | 不出现 broken image |
| format fallback | 注入非标准 format | 回退为 `image/jpeg` 正常显示 |
| FPS 无帧归零 | 暂停消息 1.5 秒以上 | FPS 显示归零 |
| 容器状态遮罩 | 切换容器到非 running | Rosout/Camera 均显示遮罩 |
| 摄像头订阅 | 启动摄像头节点 | 图像实时显示 |
| 截图功能 | 点击截图按钮 | 下载当前帧 |
| 暂停/恢复 | 切换暂停状态 | 图像冻结/恢复 |

---

## 十一、技术风险与应对

| 风险 | 影响 | 应对措施 |
|------|------|---------|
| 面板卸载资源未清理 | 内存泄漏/重复订阅 | `onBeforeUnmount` 清理 ros/topic/interval |
| 图像传输带宽占用高 | 网络拥堵 | 使用 CompressedImage + 30fps 节流 |
| rosbridge 连接不稳定 | 数据丢失 | 监听 `containerRosUrl` 变化并重连 |
| 不同摄像头 Topic 名称不一致 | 无法订阅 | 设置树可配置 Topic |

---

## 十二、后续优化方向

1. **Topic 自动发现**: 调用 rosbridge topic list API（P2）
2. **日志回放**: 录制并回放历史日志（P3）
3. **多摄像头 PiP**: 同时显示多个摄像头（P3）
4. **图像标注**: 在图像上绘制检测框（P3）
5. **性能监控**: 显示 CPU/内存/网络使用情况

---

**文档状态**: 已完成  
**审核状态**: CEO + Eng 已审批（按审查意见修订）
**最后更新**: 2026-04-01

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 3 | ISSUES_OPEN (SELECTIVE EXPANSION) | 4 scope proposals accepted, 3 deferred, 2 critical gaps |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 2 | CLEAR (PLAN) — 2 commits stale | 7 issues found, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 1 | issues_open (via /autoplan) | — |

**CRITICAL GAPS (2):**
- `CameraPanel`: `data` 为空时未处理 → `<img>` 显示 broken image
- `CameraPanel`: 无帧超 1 秒时 FPS 不重置 → 显示过期 FPS 值

**SCOPE CHANGES VS SDD:**
- ✅ Topic 名称可配置（设置树）
- ✅ 容器运行状态联动（非 running 显示遮罩）
- ✅ 日志导出为 JSON Lines .log 文件
- ✅ 不改默认布局，仅在 registry.ts 注册新面板

**VERDICT:** CEO + ENG CLEARED — 可进入实现。建议先跑一次新鲜 `/plan-eng-review` 覆盖 cherry-pick 范围变更。
