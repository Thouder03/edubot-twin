<script setup lang="ts">
/**
 * SettingsSidebar.vue - 可调宽度的 overlay 设置侧栏
 *
 * 覆盖在 GL 布局之上，不参与 GL 生命周期管理。
 * 标题栏 + 关闭按钮 + 右侧 resize handle。
 */
import { ref, computed } from 'vue'
import { Icon } from '@/components/Icon'
import { usePanelState } from '../stores/panelState'
import PanelSettings from './PanelSettings.vue'

// ---------- 宽度持久化 ----------
const SIDEBAR_WIDTH_KEY = 'simulation-sidebar-width'

function loadWidthFromStorage(): number {
  try {
    const saved = localStorage.getItem(SIDEBAR_WIDTH_KEY)
    if (saved) {
      const width = Number(saved)
      if (width >= 100 && width <= 500) {
        return width
      }
    }
  } catch (e) {
    console.warn('加载设置面板宽度失败:', e)
  }
  return 200
}

// ---------- 面板状态 ----------
const panelState = usePanelState()

const isOpen = computed(() => panelState.state.selectedPanelId !== null)

const panelTypeLabel = computed(() => {
  const map: Record<string, string> = {
    ROS3DViewer: 'ROS 3D 视图',
    GzWebViewer: 'Gazebo 仿真',
    WorkspacePanel: '代码编辑'
  }
  return (
    map[panelState.selectedPanelType.value ?? ''] ??
    panelState.selectedPanelType.value ??
    '未知面板'
  )
})

// ---------- 关闭 ----------
function handleClose() {
  panelState.clearSelection()
}

// ---------- Resize ----------
const MIN_WIDTH = 100
const MAX_WIDTH = 500
const sidebarWidth = ref(loadWidthFromStorage())
const isResizing = ref(false)

function onResizeStart(e: MouseEvent) {
  e.preventDefault()
  isResizing.value = true
  const startX = e.clientX
  const startWidth = sidebarWidth.value

  function onMouseMove(moveEvent: MouseEvent) {
    const delta = moveEvent.clientX - startX
    sidebarWidth.value = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, startWidth + delta))
  }

  function onMouseUp() {
    isResizing.value = false
    try {
      localStorage.setItem(SIDEBAR_WIDTH_KEY, String(sidebarWidth.value))
    } catch (e) {
      console.warn('保存设置面板宽度失败:', e)
    }
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
  }

  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
}
</script>

<template>
  <Transition name="sidebar-slide">
    <div v-if="isOpen" class="settings-sidebar" :style="{ width: sidebarWidth + 'px' }">
      <!-- 标题栏 -->
      <div class="sidebar-header">
        <div class="sidebar-title">
          <Icon icon="vi-carbon:settings" :size="14" class="mr-6px" />
          <span>设置 - {{ panelTypeLabel }}</span>
        </div>
        <button class="sidebar-close" @click="handleClose" title="关闭设置">
          <Icon icon="vi-carbon:close" :size="14" />
        </button>
      </div>

      <!-- 内容区 -->
      <div class="sidebar-body">
        <PanelSettings />
      </div>

      <!-- Resize handle -->
      <div class="sidebar-resize-handle" @mousedown="onResizeStart"></div>
    </div>
  </Transition>
</template>

<style lang="less" scoped>
.settings-sidebar {
  position: relative;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: #1e1e2e;
  border-right: 1px solid #313244;
  user-select: none;
}

.sidebar-header {
  display: flex;
  height: 32px;
  padding: 0 8px 0 12px;
  background: #181825;
  border-bottom: 1px solid #313244;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}

.sidebar-title {
  display: flex;
  overflow: hidden;
  font-size: 12px;
  font-weight: 500;
  color: #89b4fa;
  text-overflow: ellipsis;
  white-space: nowrap;
  align-items: center;
}

.sidebar-close {
  display: flex;
  width: 22px;
  height: 22px;
  color: #6c7086;
  cursor: pointer;
  background: transparent;
  border: none;
  border-radius: 4px;
  transition: all 150ms ease;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;

  &:hover {
    color: #cdd6f4;
    background: #313244;
  }
}

.sidebar-body {
  overflow: hidden auto;
  flex: 1;
}

.sidebar-resize-handle {
  position: absolute;
  top: 0;
  right: -3px;
  bottom: 0;
  z-index: auto;
  width: 6px;
  cursor: col-resize;
  background-color: #000;

  &:hover,
  &:active {
    background: rgb(137 180 250 / 30%);
  }
}

// ---------- 过渡动画 ----------
.sidebar-slide-enter-active {
  transition: transform 200ms ease;
}

.sidebar-slide-leave-active {
  transition: transform 100ms ease;
}

.sidebar-slide-enter-from,
.sidebar-slide-leave-to {
  transform: translateX(-100%);
}
</style>
