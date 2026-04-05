<script setup lang="ts">
/**
 * Simulation.vue - 仿真页面主容器
 *
 * 全屏布局，不使用 admin Layout
 * 使用 Golden Layout 实现可拖拽、可分割的多面板布局
 *
 * ── GzWeb 通信 ──
 * 页面加载时即初始化 GzWeb iframe 通信（不等 GzWebViewer 面板挂载），
 * 确保 SimControlBar 在 GzWebViewer 面板关闭时仍能控制仿真。
 *
 * ── 第四期：容器生命周期管理 ──
 * 心跳上报（30s/前台，120s/后台）
 * 页面重新激活弹窗
 * 退出仿真确认（beforeunload + sendBeacon）
 */
import { ref, onMounted, onBeforeUnmount, provide, readonly } from 'vue'
import { ElMessage, ElMessageBox, ElLoading } from 'element-plus'
import { LayoutConfig, type ResolvedLayoutConfig } from 'golden-layout'
import { useRoute, useRouter } from 'vue-router'

import SimulationHeader from './components/SimulationHeader.vue'
import GLayout from './components/GLayout.vue'
import SettingsSidebar from './components/SettingsSidebar.vue'
import { defaultLayout } from './config/predefined-layouts'
import { usePanelState } from './stores/panelState'
import { useGzBridge } from './composables/useGzBridge'
import { defaultConfig as gzDefaultConfig } from './panels/GzWebViewer/settings'
import {
  getMyContainerApi,
  heartbeatApi,
  startMyContainerApi,
  stopOnExitApi
} from '@/api/container'
import { stopDryRunApi } from '@/api/experiment'
import type { ContainerStatus } from '@/api/container/types'
import { useUserStore } from '@/store/modules/user'

// ---------- 路由 ----------
const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const experimentContext = ref<{
  experiment_name?: string
  version_name?: string
  environment_key?: string
} | null>(null)

// ---------- Dry Run 模式（SDD §15.5）----------
const isDryRun = ref(false)
const dryRunContainerId = ref<string | null>(null)

// ---------- GzWeb 通信（页面级初始化）----------
const { initialize: initGzBridge, dispose: disposeGzBridge } = useGzBridge()

/** 重新初始化 GzBridge（容器重启后使用） */
function reinitGzBridge(newUrl: string) {
  disposeGzBridge()
  // dispose 是同步清理，直接重新初始化
  setTimeout(() => {
    initGzBridge(newUrl)
  }, 500)
}

// ---------- 容器 ROS URL provide（供 ROS3DViewer 自动注入）----------
const containerRosUrl = ref<string | null>(null)
provide('containerRosUrl', readonly(containerRosUrl))

// ---------- 容器状态 provide（供各面板联动：键盘控制、终端等）----------
const containerStatus = ref<ContainerStatus | null>(null)
provide('containerStatus', readonly(containerStatus))

// ---------- 布局持久化 ----------
const LAYOUT_STORAGE_KEY = 'simulation-layout-config'

function loadLayoutFromStorage(): LayoutConfig | null {
  try {
    const saved = localStorage.getItem(LAYOUT_STORAGE_KEY)
    if (saved) {
      const resolvedConfig = JSON.parse(saved) as ResolvedLayoutConfig
      return LayoutConfig.fromResolved(resolvedConfig)
    }
  } catch (e) {
    console.warn('加载布局失败，将使用默认布局:', e)
    localStorage.removeItem(LAYOUT_STORAGE_KEY)
  }
  return null
}

// ---------- 状态 ----------
const glLayoutRef = ref<InstanceType<typeof GLayout> | null>(null)
const currentLayout = ref<LayoutConfig>(loadLayoutFromStorage() || defaultLayout)

// ---------- 设置面板 ----------
const panelState = usePanelState()

function handleSettingsToggle(panelId: string) {
  if (panelState.state.selectedPanelId === panelId) {
    // 同一面板 → 保持打开
  } else {
    panelState.selectPanel(panelId)
  }
}

// ---------- 布局管理 ----------
function handleLayoutChange(config: LayoutConfig) {
  if (glLayoutRef.value) {
    glLayoutRef.value.loadLayout(config)
    ElMessage.success('布局已切换')
  }
}

function handleAddPanel(type: string, title: string) {
  if (glLayoutRef.value) {
    glLayoutRef.value.addComponent(type, title)
  }
}

function saveLayoutToStorage() {
  if (glLayoutRef.value) {
    const config = glLayoutRef.value.saveLayout()
    if (config) {
      try {
        localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(config))
      } catch (e) {
        console.warn('保存布局失败:', e)
      }
    }
  }
}

// ─── 心跳定时器 ──────────────────────────────────────────
const HEARTBEAT_INTERVAL = 30_000 // 前台：30 秒
const HEARTBEAT_INTERVAL_BG = 120_000 // 后台/低频：120 秒

let heartbeatTimer: ReturnType<typeof setInterval> | null = null
let currentInterval = HEARTBEAT_INTERVAL

function startHeartbeat() {
  stopHeartbeat()
  heartbeatTimer = setInterval(sendHeartbeat, currentInterval)
  sendHeartbeat() // 立即发一次
}

function stopHeartbeat() {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer)
    heartbeatTimer = null
  }
}

async function sendHeartbeat() {
  try {
    const res = await heartbeatApi()
    const status = res?.data?.status

    if (status) {
      // 始终同步最新状态给子面板
      containerStatus.value = status
    }

    if (status && status !== 'running') {
      // 容器已不在运行 → 触发重新激活弹窗
      stopHeartbeat()
      handleContainerStopped()
    }
  } catch (err) {
    // 网络错误：静默处理，等下次心跳重试
    console.warn('[Heartbeat] 心跳失败:', err)
  }
}

// ─── Page Visibility 联动 ────────────────────────────────
function handleVisibilityChange() {
  if (document.hidden) {
    // 页面进入后台：降频心跳
    currentInterval = HEARTBEAT_INTERVAL_BG
    startHeartbeat()
  } else {
    // 页面恢复前台：恢复正常心跳 + 立即检查状态
    currentInterval = HEARTBEAT_INTERVAL
    startHeartbeat()
    checkContainerOnReactivation()
  }
}

// ─── 重新激活检查与弹窗 ─────────────────────────────────
let isAlertShowing = false

async function checkContainerOnReactivation() {
  if (isAlertShowing) return

  try {
    const res = await getMyContainerApi()
    const status = res?.data?.status

    if (status === 'running') {
      // 一切正常，无需操作
      return
    }

    if (status === 'stopped') {
      await handleContainerStopped()
    } else if (status) {
      if (isAlertShowing) return
      isAlertShowing = true
      // error / creating / removing → 提示异常
      await ElMessageBox.alert('仿真容器状态异常，请返回首页重新操作。', '容器异常', {
        confirmButtonText: '返回首页',
        type: 'error'
      }).catch(() => {})
      isAlertShowing = false
      navigateToHome()
    }
  } catch (err: any) {
    if (err?.response?.status === 404) {
      if (isAlertShowing) return
      isAlertShowing = true
      await ElMessageBox.alert('您的仿真容器已被管理员回收，请返回首页重新申请。', '容器已回收', {
        confirmButtonText: '返回首页',
        type: 'warning'
      }).catch(() => {})
      isAlertShowing = false
      navigateToHome()
    } else {
      ElMessage.warning('网络连接异常，请检查网络')
    }
  }
}

async function handleContainerStopped() {
  if (isAlertShowing) return
  isAlertShowing = true
  try {
    await ElMessageBox.confirm(
      '由于长时间未活动，您的仿真容器已自动关闭。是否重新启动？',
      '仿真容器已关闭',
      {
        confirmButtonText: '重新启动',
        cancelButtonText: '返回首页',
        type: 'warning',
        closeOnClickModal: false,
        closeOnPressEscape: false
      }
    )
    isAlertShowing = false
    // 用户点击"重新启动"
    await restartContainer()
  } catch {
    isAlertShowing = false
    // 用户点击"返回首页"
    navigateToHome()
  }
}

async function restartContainer() {
  const loading = ElLoading.service({ text: '正在重新启动仿真容器...' })
  try {
    await startMyContainerApi()

    // 轮询等待容器 running（最多 60s）
    const result = await waitForContainerRunning()
    if (result) {
      const gzUrl = result.gzbridge_url
      const rosUrl = result.rosbridge_url
      if (gzUrl) reinitGzBridge(gzUrl)
      if (rosUrl) containerRosUrl.value = rosUrl
      startHeartbeat()
      ElMessage.success('仿真容器已重新启动')
    } else {
      ElMessage.error('容器启动超时，请返回首页重试')
      navigateToHome()
    }
  } catch (err) {
    console.error('[Simulation] 重启容器失败:', err)
    ElMessage.error('重启失败，请返回首页重试')
    navigateToHome()
  } finally {
    loading.close()
  }
}

async function waitForContainerRunning(maxAttempts = 30, intervalMs = 2000) {
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise((resolve) => setTimeout(resolve, intervalMs))
    try {
      const res = await getMyContainerApi()
      const data = res?.data
      if (data?.status === 'running') return data
      if (data?.status === 'error') return null
    } catch {
      // 继续重试
    }
  }
  return null
}

function navigateToHome() {
  // 仿真页是新标签页打开的，尝试关闭
  window.close()
  // 如果 window.close() 不起作用（非 JS 打开的标签页）
  setTimeout(() => {
    router.push('/student/home')
  }, 300)
}

// ─── beforeunload 拦截 ────────────────────────────────────
function handleBeforeUnload(event: BeforeUnloadEvent) {
  // 现代浏览器标准规范
  event.preventDefault()
  // 兼容 Safari 及某些旧版浏览器
  event.returnValue = '退出将关闭仿真容器，确定要离开吗？'
  return event.returnValue
}

// ---------- 局部暗色模式 ----------
let originalDarkClass = false

// ---------- 生命周期 ----------
onMounted(async () => {
  // 记录原始状态并强制暗色模式
  originalDarkClass = document.documentElement.classList.contains('dark')
  document.documentElement.classList.add('dark')
  document.documentElement.classList.remove('light')

  document.body.style.overflow = 'hidden'
  window.addEventListener('beforeunload', saveLayoutToStorage)
  window.addEventListener('beforeunload', handleBeforeUnload)
  document.addEventListener('visibilitychange', handleVisibilityChange)

  const experimentName =
    typeof route.query.experiment_name === 'string' ? route.query.experiment_name : undefined
  const versionName =
    typeof route.query.version_name === 'string' ? route.query.version_name : undefined
  const environmentKey =
    typeof route.query.environment_key === 'string' ? route.query.environment_key : undefined

  experimentContext.value = {
    experiment_name: experimentName,
    version_name: versionName,
    environment_key: environmentKey
  }

  // Dry Run 模式检测（SDD §15.5）
  isDryRun.value = route.query.dry_run === '1'
  if (isDryRun.value) {
    const cid = route.query.container_id
    dryRunContainerId.value = typeof cid === 'string' ? cid : null
  }

  // ── 页面级 GzWeb 通信初始化 ──
  try {
    const res = await getMyContainerApi()
    const data = res?.data
    const gzUrl = data?.gzbridge_url
    const rosUrl = data?.rosbridge_url

    // 同步初始容器状态
    if (data?.status) {
      containerStatus.value = data.status
    }

    if (gzUrl) {
      console.info('[Simulation] 从 API 获取 gzbridge URL:', gzUrl)
      initGzBridge(gzUrl)
    } else {
      console.warn('[Simulation] API 未返回 gzbridge_url，使用 fallback:', gzDefaultConfig.gzwebUrl)
      initGzBridge(gzDefaultConfig.gzwebUrl)
    }

    if (rosUrl) {
      containerRosUrl.value = rosUrl
      console.info('[Simulation] 已 provide 容器 rosbridge_url:', rosUrl)
    }
  } catch (err) {
    console.warn(
      '[Simulation] 页面级初始化: 获取容器 API 失败, 使用 fallback:',
      err,
      gzDefaultConfig.gzwebUrl
    )
    initGzBridge(gzDefaultConfig.gzwebUrl)
  }

  // ── 启动心跳 ──
  startHeartbeat()
})

onBeforeUnmount(() => {
  stopHeartbeat()
  saveLayoutToStorage()
  disposeGzBridge()

  // 组件卸载时用 sendBeacon 通知后端停止容器
  const token = userStore.getToken
  if (token) {
    stopOnExitApi(token)
  }

  // 恢复原始暗色模式状态
  if (!originalDarkClass) {
    document.documentElement.classList.remove('dark')
    document.documentElement.classList.add('light')
  }

  document.body.style.overflow = ''
  window.removeEventListener('beforeunload', saveLayoutToStorage)
  window.removeEventListener('beforeunload', handleBeforeUnload)
  document.removeEventListener('visibilitychange', handleVisibilityChange)

  // Dry Run：best-effort 清理测试容器（SDD §15.5）
  if (isDryRun.value && dryRunContainerId.value) {
    stopDryRunApi(dryRunContainerId.value).catch(() => {})
  }
})

// ---------- 退出（来自 SimulationHeader 的 back 事件）----------
async function handleBack() {
  // SimulationHeader 已自行弹窗确认并停止容器，这里只需关闭标签页
  window.close()
  setTimeout(() => {
    router.push('/student/home')
  }, 300)
}
</script>

<template>
  <div class="simulation-page">
    <!-- Dry Run 橙色提示条（SDD §15.5）-->
    <div v-if="isDryRun" class="dry-run-banner"> 🧪 试运行模式 — 该容器将在结束后立即自动清理 </div>
    <SimulationHeader
      :experiment-context="experimentContext"
      @layout-change="handleLayoutChange"
      @add-panel="handleAddPanel"
      @back="handleBack"
    />
    <div class="simulation-content">
      <SettingsSidebar />
      <GLayout
        ref="glLayoutRef"
        :initial-layout="currentLayout"
        @settings-toggle="handleSettingsToggle"
      />
    </div>
  </div>
</template>

<style lang="less">
/* 不能 scoped，因为子组件的 GL 样式需要继承 */
.simulation-page {
  display: flex;
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  background: #11111b;
  flex-direction: column;
}

.dry-run-banner {
  background: #e6790c;
  color: #fff;
  text-align: center;
  font-size: 13px;
  font-weight: 600;
  padding: 6px 16px;
  letter-spacing: 0.3px;
  flex-shrink: 0;
  z-index: 100;
}

.simulation-content {
  display: flex;
  overflow: hidden;
  flex: 1;
}

.lm_header .lm_tab.lm_active.lm_focused {
  background-color: #222 !important;
}
</style>

<!-- 引入 Golden Layout 样式 -->
<style src="golden-layout/dist/css/goldenlayout-base.css"></style>
<style src="golden-layout/dist/css/themes/goldenlayout-dark-theme.css"></style>
