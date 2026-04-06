# Dry Run 重构计划：Shadow 学生身份方案

## Context

当前教师 Dry Run 采用内存态会话管理（`dry_run_manager.py`），容器不写入数据库，前端 `Simulation.vue` 中有大量 `isDryRun` 条件分支。教师体验与学生端不一致：无心跳、无重激活、退出即清理。

本次重构将 Dry Run 改为"Shadow 学生身份"方案：教师获得一个代理学生账号，用该账号的 JWT 访问所有学生接口，获得与学生完全一致的仿真体验。同时新增 Dry Run 专属悬浮工具栏（Docker Logs + 失败回顾）和终端/文件面板的 ROOT 切换功能。

## 已确认设计决策

| 决策项 | 结论 |
|--------|------|
| 并发 | 同时 1 个（与学生一致，force_recreate） |
| Token | sessionStorage 隔离（新标签页独立，不影响教师原标签页） |
| Docker logs | REST API 一次性获取最近 N 行 + 手动刷新 |
| ROOT 文件范围 | 容器内全部文件系统（docker exec） |

---

## Step 1: User 模型扩展 + Shadow 账号服务

### 1.1 User 模型增加字段

**文件**: `edubot-twin-server/app/models/student.py`

```python
# 新增两个字段
is_shadow: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
shadow_owner_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
```

- `is_shadow=True` 标记为 Shadow 学生（用于查询过滤、权限判断）
- `shadow_owner_id` 指向拥有者教师的 `user_id`

### 1.2 Shadow 账号 CRUD 服务

**新建文件**: `edubot-twin-server/app/crud/shadow_student.py`

```python
async def get_or_create_shadow(db, teacher_id: int) -> User:
    """幂等：查询或创建教师的 Shadow 学生"""
    # SELECT WHERE is_shadow=True AND shadow_owner_id=teacher_id
    # 不存在则 INSERT: username="_shadow_{teacher_id}", role_code="student", is_shadow=True

async def is_shadow_user(db, user_id: int) -> bool:
    """快速检查是否为 Shadow 学生"""
```

- Shadow 学生 `role_code = "student"`，JWT 包含 `role: "student"`
- 命名规范: `_shadow_{teacher_id}`（下划线前缀防与真实用户名冲突）
- 密码: 随机 bcrypt hash（永远不会通过登录页面使用）

### 1.3 学生列表过滤

**文件**: `edubot-twin-server/app/crud/student.py`

`get_users()` / `get_students()` 查询添加 `WHERE is_shadow = False`，防止 Shadow 账号出现在教师管理的学生列表中。

---

## 变更文件总览

| 文件 | 操作 | 改动量 |
|------|------|--------|
| `DryRunSimulation.vue` | **新建** | ~80 行（轻量包装） |
| `DryRunLoadingOverlay.vue` | **新建** | ~60 行 |
| `Simulation.vue` | 修改 | 删 ~30 行 + 加 ~6 行 |
| `DryRunToolbar.vue` | 修改 | 新增拖拽逻辑 ~40 行 |
| `router/index.ts` | 修改 | +8 行 |
| `ExperimentEnvs.vue` | 修改 | **仅改 1 行**（路由名） |

---

## 详细变更说明

### 一、新建 `DryRunSimulation.vue`

路径：`src/views/Simulation/DryRunSimulation.vue`

**职责**：
1. 从 URL query 取 `simulation_token` → 存 `sessionStorage`（与现有逻辑相同）
2. `provide('isDryRunContext', true)` 传给子组件 Simulation.vue
3. 全屏加载覆盖层：轮询 `getMyContainerApi()`，容器 running 后隐藏覆盖层
4. 渲染 `<Simulation />`（直接作为子组件）
5. 悬浮 `<DryRunToolbar />`（始终可见，不受覆盖层遮挡）
6. `onBeforeUnmount`：`sessionStorage.removeItem('simulation_token')`（从 Simulation.vue 移过来）

**模板结构**：
```vue
<template>
  <!-- 学生端仿真页面作为子组件直接引入，100vw/100vh 全屏 -->
  <Simulation />

  <!-- 初始加载覆盖层（position:fixed z-index:9999，遮住 Simulation） -->
  <DryRunLoadingOverlay v-if="loadingVisible" :stage-text="loadingText" />

  <!-- Dry Run 工具栏（position:fixed z-index:10000，始终显示，可拖拽） -->
  <DryRunToolbar />
</template>
```

> **布局说明**：Simulation.vue 根元素 `.simulation-page` 是 `width:100vw; height:100vh`，
> 非 `position:fixed`，直接作为子组件渲染无冲突。覆盖层和工具栏用 `position:fixed` 悬浮顶部。

**加载逻辑**：
```typescript
// shadow_token 存入 sessionStorage（Shadow JWT 立即生效）
const simToken = route.query.simulation_token
if (typeof simToken === 'string') {
  sessionStorage.setItem('simulation_token', simToken)
  const { simulation_token: _, ...restQuery } = route.query
  router.replace({ ...route, query: restQuery }) // 清除 URL 中的 token
}

// 轮询容器状态，running 后隐藏覆盖层
const loadingVisible = ref(true)
const loadingText = ref('正在连接仿真容器...')

async function waitForContainer() {
  const stages: Record<string, string> = {
    creating: '正在创建仿真容器...',
    running:  '仿真环境就绪，正在加载...',
  }
  for (let i = 0; i < 30; i++) {
    try {
      const res = await getMyContainerApi() // 走 shadow JWT
      const status = res?.data?.status
      if (status && stages[status]) loadingText.value = stages[status]
      if (status === 'running') {
        await new Promise(r => setTimeout(r, 500))
        loadingVisible.value = false
        return
      }
    } catch {}
    await new Promise(r => setTimeout(r, 2000))
  }
  // 超时：仍然放行（Simulation.vue 自己会处理）
  loadingVisible.value = false
}

onMounted(async () => {
  provide('isDryRunContext', true)
  await waitForContainer()
})
```

---

### 二、修改 `Simulation.vue`（最小改动）

路径：`src/views/Simulation/Simulation.vue`

**改动 ①：删除 DryRunToolbar 相关（~8 行）**
```diff
- import DryRunToolbar from './components/DryRunToolbar.vue'
  ...
- // ---------- Dry Run 模式标记（仅用于工具栏可见性，不影响业务逻辑）----------
- const isDryRunMode = ref(!!sessionStorage.getItem('simulation_token'))
  ...
- <DryRunToolbar v-if="isDryRunMode" />
```

**改动 ②：删除 `handleSimulationToken` 及其调用（~10 行）**
```diff
- // ─── simulation_token 接收与 URL 清理 ────────────────────
- function handleSimulationToken() {
-   const simToken = route.query.simulation_token
-   if (typeof simToken === 'string') {
-     sessionStorage.setItem('simulation_token', simToken)
-     isDryRunMode.value = true
-     const { simulation_token: _, ...restQuery } = route.query
-     router.replace({ ...route, query: restQuery })
-   }
- }
  // onMounted 中
- handleSimulationToken()
```

**改动 ③：删除 sessionStorage cleanup（移到 DryRunSimulation.vue 负责）**
```diff
  onBeforeUnmount(() => {
    ...
-   sessionStorage.removeItem('simulation_token')
    ...
  })
```

**改动 ④：注入 isDryRunContext，屏蔽弹窗逻辑（+6 行）**
```typescript
// 新增（与其他 import/inject 放在一起）：
const isDryRunContext = inject('isDryRunContext', false)

// handleContainerStopped 开头新增一行：
async function handleContainerStopped() {
  if (isDryRunContext) return  // ← 新增：Dry Run 模式不弹窗不跳转
  if (isAlertShowing) return
  ...
}

// checkContainerOnReactivation 中 stopped 分支（原来直接 await handleContainerStopped）：
if (status === 'stopped') {
  if (!isDryRunContext) await handleContainerStopped()  // ← 加 guard
  return
}

// error/其他分支（原来直接 navigateToHome）：
if (!isDryRunContext) navigateToHome()  // ← 加 guard（共 2 处）
```

> **注意**：`isDryRunContext` 默认值为 `false`，学生端直接用 Simulation.vue 时行为完全不变。

---

### 三、修改 `router/index.ts`（+8 行）

在 `/simulation` 路由定义旁新增：
```typescript
{
  path: '/dry-run-simulation',
  component: () => import('@/views/Simulation/DryRunSimulation.vue'),
  name: 'DryRunSimulation',
  meta: {
    hidden: true,
    title: 'Dry Run 仿真',
    noTagsView: true,
    noCache: true
  }
}
```

---

### 四、修改 `ExperimentEnvs.vue`（改 1 行）

`startDryRun()` 函数中仅修改路由名：
```diff
  const url = router.resolve({
-   name: 'Simulation',
+   name: 'DryRunSimulation',
    query: {
      simulation_token: shadow_token,  // 完全保持不变
      env_bundle_name: selectedEnvBundle.value.name
    }
  }).href
  window.open(url, '_blank')
```

---

### 五、修改 `DryRunToolbar.vue`（新增拖拽 + 位置记忆）

路径：`src/views/Simulation/components/DryRunToolbar.vue`

**位置改为动态定位**（从 `bottom/right` 固定 → `left/top` 可拖动）：
```typescript
// 位置状态，从 localStorage 恢复，默认右下角
const pos = ref<{ x: number; y: number }>(restorePosition())

function restorePosition() {
  try {
    const saved = localStorage.getItem('dry-run-toolbar-pos')
    if (saved) return JSON.parse(saved)
  } catch {}
  return { x: window.innerWidth - 140, y: window.innerHeight - 240 }
}

function startDrag(e: MouseEvent) {
  e.preventDefault()
  const startX = e.clientX - pos.value.x
  const startY = e.clientY - pos.value.y
  const onMove = (ev: MouseEvent) => {
    pos.value = {
      x: Math.max(0, Math.min(window.innerWidth - 140, ev.clientX - startX)),
      y: Math.max(0, Math.min(window.innerHeight - 240, ev.clientY - startY))
    }
  }
  const onUp = () => {
    localStorage.setItem('dry-run-toolbar-pos', JSON.stringify(pos.value))
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}
```

**模板**（标签行作为拖拽手柄，加 `cursor: move`）：
```vue
<div
  class="dry-run-toolbar"
  :class="{ collapsed }"
  :style="{ left: pos.x + 'px', top: pos.y + 'px' }"
>
  <!-- 标签行可拖拽 -->
  <div class="toolbar-label" @mousedown="startDrag">🔬 Dry Run ⠿</div>
  <!-- 收起/展开按钮 -->
  <button class="toolbar-toggle" @click="collapsed = !collapsed">
    {{ collapsed ? '🔧' : '×' }}
  </button>
  <template v-if="!collapsed">
    ...原有按钮不变...
  </template>
</div>
```

**CSS 修改**：
```diff
 .dry-run-toolbar {
   position: fixed;
-  bottom: 24px;
-  right: 24px;
+  /* left/top 由 :style 动态绑定 */
   ...
 }

+.toolbar-label {
+  cursor: move;
+  user-select: none;
+}
```

---

### 六、新建 `DryRunLoadingOverlay.vue`

路径：`src/views/Simulation/components/DryRunLoadingOverlay.vue`

仿学生端 `ElLoading` 风格的全屏覆盖层（暗色背景 + 旋转动画 + 阶段文字）：

```vue
<script setup lang="ts">
defineProps<{ stageText?: string }>()
</script>

<template>
  <div class="dry-run-overlay">
    <div class="overlay-body">
      <div class="spinner" />
      <div class="overlay-text">{{ stageText || '正在连接仿真容器...' }}</div>
    </div>
  </div>
</template>

<style scoped>
.dry-run-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(17, 17, 27, 0.95);
  display: flex;
  align-items: center;
  justify-content: center;
}
.overlay-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
}
.spinner {
  width: 48px;
  height: 48px;
  border: 4px solid #313244;
  border-top-color: #cba6f7;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.overlay-text {
  color: #cdd6f4;
  font-size: 15px;
  letter-spacing: 0.5px;
}
</style>
```

---

## 行为对比

| 行为 | Simulation.vue（学生端） | DryRunSimulation（教师 Dry Run） |
|------|--------------------------|----------------------------------|
| Shadow JWT | ❌ 学生自身 JWT | ✅ 完整保留，机制不变 |
| DryRunToolbar | ❌ 已移除 | ✅ 始终显示，可拖拽，记住位置 |
| 工具栏初始可见 | - | ✅ 页面打开即可用（覆盖层之上） |
| 加载覆盖层 | ❌（学生首页处理） | ✅ 页面自带，容器就绪后消失 |
| 容器关闭弹窗 | ✅ 弹出「重启/返回首页」 | ❌ **inject 屏蔽，不弹窗不跳转** |
| 运行失败跳转 | ✅ 弹窗/跳转 | ❌ **inject 屏蔽，保持在页面** |
| stopOnExitApi | 学生 JWT | Shadow JWT（请求拦截器自动） |
| sessionStorage cleanup | ❌（已移除） | ✅ DryRunSimulation.vue 负责 |

---

## 加载时序

```
教师点击「试运行」按钮（ExperimentEnvs.vue）
    │
    ▼
startDryRunApi(envBundleId, versionId)
    │
    ▼  返回 { shadow_token, container_id }
    │
    ▼
window.open('/dry-run-simulation?simulation_token=<shadow_token>&...')

    ═══════════════ 新标签页 ═══════════════

DryRunSimulation.vue onMounted:
    │
    ├─ shadow_token → sessionStorage       ← Shadow JWT 立即生效
    ├─ provide('isDryRunContext', true)    ← 注入行为控制
    ├─ loadingVisible = true               ← 覆盖层显示（遮住 Simulation）
    ├─ DryRunToolbar 渲染                  ← 工具栏立即可用（在覆盖层之上）
    │
    ├─ 轮询 getMyContainerApi() （走 shadow JWT）
    │       │
    │       ▼ status === 'running'
    │
    └─ loadingVisible = false              ← 覆盖层消失，Simulation 展示
```

---

## 验证计划

1. **教师端**：点击「试运行」→ 新标签页打开，立即显示加载覆盖层，工具栏可见可拖拽
2. **容器就绪**：覆盖层消失，仿真面板正常显示，工具栏继续悬浮
3. **拖拽记忆**：拖动工具栏到任意位置 → 刷新页面 → 位置恢复
4. **容器关闭**：不弹出「仿真容器已关闭」弹窗，页面保持不动
5. **学生端验证**：`/simulation` 路由无 DryRunToolbar，无 shadow_token 逻辑
6. **TypeScript 检查**：`npm run type-check --prefix edubot-twin-web`
