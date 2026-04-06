<script setup lang="ts">
/**
 * DryRunSimulation.vue - Dry Run 专属仿真页面
 *
 * 流程：
 *   1. ExperimentEnvs.vue 点击按钮后立即打开此页（传入 env_bundle_id + version_id）
 *   2. 本页用教师 JWT 调用 startDryRunApi → 获得 shadow_token → 存入 sessionStorage
 *   3. 轮询容器状态，running 前显示全屏覆盖层，Simulation.vue 此时不挂载
 *   4. 容器就绪后 simulationReady=true，Simulation.vue 首次挂载（直接连接已就绪的容器）
 *
 * provide('isDryRunContext', true) 注入 Simulation.vue，屏蔽容器关闭弹窗等行为。
 * DryRunToolbar 始终可见（z-index: 10000），覆盖层期间也可操作。
 */
import { ref, provide, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import Simulation from './Simulation.vue'
import DryRunToolbar from './components/DryRunToolbar.vue'
import DryRunLoadingOverlay from './components/DryRunLoadingOverlay.vue'
import { getMyContainerApi } from '@/api/container'
import { getDryRunFailureReviewApi, startDryRunApi } from '@/api/experiment'

const route = useRoute()

// ── provide：Simulation.vue 内部据此屏蔽容器关闭弹窗和失败跳转 ──
provide('isDryRunContext', true)

// ── 从路由参数获取 env_bundle_id 和 version_id ──────────────
const envBundleId = Number(route.query.env_bundle_id)
const versionId = Number(route.query.version_id)

// ── 覆盖层状态 ────────────────────────────────────────────────
const loadingVisible = ref(true)
const loadingText = ref('正在启动 Dry Run 容器...')
const loadingError = ref<string | null>(null)

// simulationReady 控制 <Simulation /> 是否挂载
// false 时 Simulation.vue 不加载，避免在容器未就绪时建立连接
const simulationReady = ref(false)
// shadowTokenReady 控制工具栏功能是否可用：false 时 shadow_token 尚未就位
const shadowTokenReady = ref(false)

const stageTextMap: Record<string, string> = {
  creating: '正在创建仿真容器...',
  stopping: '正在清理旧容器...',
  running: '仿真环境就绪，正在加载...',
  error: '容器启动异常，请检查日志...'
}

// ── 轮询容器直到 running ─────────────────────────────────────
async function getDryRunFailureDetail(): Promise<string | null> {
  try {
    const res = await getDryRunFailureReviewApi()
    const containerStatus = String(res?.data?.container?.status || '')
    const containerError = String(res?.data?.container?.error_message || '').trim()
    const taskError = String(res?.data?.task?.error_message || '').trim()
    const taskCode = String(res?.data?.task?.error_code || '').trim()
    const taskStage = String(res?.data?.task?.current_stage || '').trim()

    if (containerError) return containerError
    if (taskError) return taskError
    if (taskCode) return taskStage ? `${taskCode} (${taskStage})` : taskCode

    if (containerStatus === 'error') {
      return '容器状态异常，但后端未返回错误详情，请查看 Docker Logs'
    }
    return null
  } catch {
    return null
  }
}

async function waitForContainer(): Promise<
  { ok: true } | { ok: false; reason: 'error' | 'timeout'; detail?: string }
> {
  const maxAttempts = 30 // 最多等待 60 秒
  for (let i = 0; i < maxAttempts; i++) {
    try {
      const res = await getMyContainerApi() // 此时走 shadow JWT
      const status = res?.data?.status as string | undefined
      if (status && stageTextMap[status]) {
        loadingText.value = stageTextMap[status]
      }
      if (status === 'running') {
        return { ok: true }
      }
      if (status === 'error') {
        const detail = await getDryRunFailureDetail()
        return { ok: false, reason: 'error', detail: detail ?? undefined }
      }
    } catch {
      // 网络错误静默重试
    }
    await new Promise((r) => setTimeout(r, 2000))
  }
  return { ok: false, reason: 'timeout' }
}

// ── 初始化：startDryRunApi → 存 token → 轮询 → 挂载 Simulation ──
onMounted(async () => {
  // 检查参数合法性
  if (!envBundleId || !versionId) {
    loadingError.value = '参数缺失：env_bundle_id 或 version_id 不存在'
    return
  }

  try {
    // Step 1: 用教师 JWT 启动 Dry Run（sessionStorage 中此时无 shadow_token）
    loadingText.value = '正在启动 Dry Run 容器...'
    const res = await startDryRunApi(envBundleId, versionId)
    const { shadow_token } = res.data

    // Step 2: 存入 sessionStorage，后续所有 API 调用自动走 shadow JWT
    sessionStorage.setItem('simulation_token', shadow_token)
    // shadow_token 就位，工具栏功能即刻可用
    shadowTokenReady.value = true

    // Step 3: 轮询容器状态
    loadingText.value = '正在等待容器就绪...'
    const result = await waitForContainer()

    if (result.ok) {
      // Step 4: 容器就绪，挂载 Simulation.vue（首次挂载时容器已 running）
      simulationReady.value = true
      // 稍作延迟确保响应式更新后再移除覆盖层
      await new Promise((r) => setTimeout(r, 300))
      loadingVisible.value = false
    } else if (result.reason === 'error') {
      loadingError.value = result.detail
        ? `容器启动失败：${result.detail}`
        : '容器启动失败，请查看 Docker Logs 排查原因'
    } else {
      loadingError.value = '容器启动超时，请查看 Docker Logs 排查原因'
    }
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    loadingError.value = '启动失败：' + (detail || e?.message || '未知错误')
    ElMessage.error(loadingError.value)
  }
})
</script>

<template>
  <!--
    Simulation.vue 只在容器就绪（simulationReady=true）后才挂载，
    避免容器未启动时建立无效连接。
  -->
  <Simulation v-if="simulationReady" />

  <!-- 加载覆盖层（z-index: 9999），容器就绪前持续显示 -->
  <DryRunLoadingOverlay
    v-if="loadingVisible"
    :stage-text="loadingError ?? loadingText"
    :is-error="!!loadingError"
  />

  <!-- Dry Run 工具栏（z-index: 10000），始终可见，覆盖层上方 -->
  <!-- ready: shadow_token 就位后才允许调用 API -->
  <DryRunToolbar :ready="shadowTokenReady" />
</template>
