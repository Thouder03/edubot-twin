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
 */
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { LayoutConfig, type ResolvedLayoutConfig } from 'golden-layout'

import SimulationHeader from './components/SimulationHeader.vue'
import GLayout from './components/GLayout.vue'
import SettingsSidebar from './components/SettingsSidebar.vue'
import { defaultLayout } from './config/predefined-layouts'
import { usePanelState } from './stores/panelState'
import { useGzBridge } from './composables/useGzBridge'
import { defaultConfig as gzDefaultConfig } from './panels/GzWebViewer/settings'

// ---------- GzWeb 通信（页面级初始化）----------
const { initialize: initGzBridge, dispose: disposeGzBridge } = useGzBridge()

// ---------- 布局持久化 ----------
const LAYOUT_STORAGE_KEY = 'simulation-layout-config'

/**
 * 同步读取 localStorage 中保存的布局
 * 必须在组件 setup 阶段执行（GLayout onMounted 之前），
 * 否则 GLayout 会先用 defaultLayout 初始化
 */
function loadLayoutFromStorage(): LayoutConfig | null {
  try {
    const saved = localStorage.getItem(LAYOUT_STORAGE_KEY)
    if (saved) {
      const resolvedConfig = JSON.parse(saved) as ResolvedLayoutConfig
      // saveLayout() 返回的是 ResolvedLayoutConfig，
      // 必须用 LayoutConfig.fromResolved() 转换回 LayoutConfig
      return LayoutConfig.fromResolved(resolvedConfig)
    }
  } catch (e) {
    console.warn('加载布局失败，将使用默认布局:', e)
    localStorage.removeItem(LAYOUT_STORAGE_KEY)
  }
  return null
}

// ---------- 状态 ----------
// 在 setup 阶段同步确定初始布局（GLayout onMounted 之前）
const glLayoutRef = ref<InstanceType<typeof GLayout> | null>(null)
const currentLayout = ref<LayoutConfig>(loadLayoutFromStorage() || defaultLayout)

// ---------- 设置面板 ----------
const panelState = usePanelState()

function handleSettingsToggle(panelId: string) {
  if (panelState.state.selectedPanelId === panelId) {
    // 同一面板 → 保持打开
  } else {
    // 不同面板或当前未打开 → 打开/切换
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

function handleBack() {
  window.close()
  setTimeout(() => {
    ElMessage.info('请手动关闭此标签页')
  }, 300)
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

// ---------- 局部暗色模式 ----------
// 仿真页在新标签页打开，强制暗色模式不影响全局设置
let originalDarkClass = false

// ---------- 生命周期 ----------
onMounted(() => {
  // 记录原始状态并强制暗色模式
  originalDarkClass = document.documentElement.classList.contains('dark')
  document.documentElement.classList.add('dark')
  document.documentElement.classList.remove('light')

  document.body.style.overflow = 'hidden'
  window.addEventListener('beforeunload', saveLayoutToStorage)

  // ── 页面级 GzWeb 通信初始化 ──
  // 使用 GzWebViewer 默认配置中的 gzwebUrl
  // 将来第二期从后端 API 获取动态地址后，此处改为 API 返回值
  initGzBridge(gzDefaultConfig.gzwebUrl)
})

onBeforeUnmount(() => {
  saveLayoutToStorage()

  // ── 销毁 GzWeb 通信 ──
  disposeGzBridge()

  // 恢复原始暗色模式状态
  if (!originalDarkClass) {
    document.documentElement.classList.remove('dark')
    document.documentElement.classList.add('light')
  }

  document.body.style.overflow = ''
  window.removeEventListener('beforeunload', saveLayoutToStorage)
})
</script>

<template>
  <div class="simulation-page">
    <SimulationHeader
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
  width: 100vw;
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #11111b;
}

.simulation-content {
  flex: 1;
  overflow: hidden;
  display: flex;
}

.lm_header .lm_tab.lm_active.lm_focused {
  background-color: #222222 !important;
}
</style>

<!-- 引入 Golden Layout 样式 -->
<style src="golden-layout/dist/css/goldenlayout-base.css"></style>
<style src="golden-layout/dist/css/themes/goldenlayout-dark-theme.css"></style>
