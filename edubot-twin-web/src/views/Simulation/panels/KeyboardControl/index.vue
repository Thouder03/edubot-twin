<script setup lang="ts">
/**
 * KeyboardControl - 键盘控制面板
 *
 * - 通过 WASD / 方向键 控制机器人移动（发布 geometry_msgs/Twist）
 * - 空格键急停（发布全零 Twist）
 * - 只在面板聚焦时监听键盘，避免干扰终端等其他输入
 * - 容器非 running 时：控件全部禁用，显示状态提示
 * - 使用 usePanelConfig 接入设置树（线速度、角速度、Topic）
 */
import { ref, computed, reactive, inject, onMounted, onBeforeUnmount, watch, type Ref } from 'vue'
import { Ros, Topic } from 'roslib'
import { usePanelConfig } from '../../composables/usePanelConfig'
import { usePanelState } from '../../stores/panelState'
import { DEFAULT_CONFIG, buildNodes, applyAction } from './settings'
import type { ContainerStatus } from '@/api/container/types'

// ---------- Props ----------
const props = defineProps<{ panelId: string }>()

// ---------- 设置接入 ----------
const { config } = usePanelConfig(props.panelId, DEFAULT_CONFIG, buildNodes, applyAction)
const { registerPanel, unregisterPanel } = usePanelState()

// ---------- 容器状态联动 ----------
const containerStatus = inject<Ref<ContainerStatus | null>>('containerStatus', ref(null))
const containerRosUrl = inject<Ref<string | null>>('containerRosUrl', ref(null))

const isRunning = computed(() => containerStatus.value === 'running')

const statusText = computed(() => {
  const s = containerStatus.value
  if (!s) return '容器状态未知，请稍候...'
  const map: Record<ContainerStatus, string> = {
    running: '运行中',
    stopped: '容器已停止，请返回首页重启后使用',
    creating: '容器启动中，请稍候...',
    removing: '容器删除中',
    error: '容器异常，请联系管理员'
  }
  return map[s] ?? s
})

// ---------- ROS 连接 ----------
let ros: Ros | null = null
let cmdVelPub: Topic | null = null
const rosConnected = ref(false)

function connectRos() {
  if (!containerRosUrl.value) return
  if (ros) {
    ros.close()
    ros = null
  }
  try {
    ros = new Ros({ url: containerRosUrl.value })
    ros.on('connection', () => {
      rosConnected.value = true
      setupPublisher()
    })
    ros.on('error', () => {
      rosConnected.value = false
    })
    ros.on('close', () => {
      rosConnected.value = false
    })
  } catch (e) {
    console.warn('[KeyboardControl] ROS 连接失败:', e)
  }
}

function setupPublisher() {
  if (!ros) return
  cmdVelPub = new Topic({
    ros,
    name: config.value.cmdVelTopic,
    messageType: 'geometry_msgs/Twist'
  })
}

function publishTwist(linear: number, angular: number) {
  if (!cmdVelPub || !rosConnected.value) return
  cmdVelPub.publish({
    linear: { x: linear, y: 0, z: 0 },
    angular: { x: 0, y: 0, z: angular }
  } as any)
}

// 当 rosUrl 变化时重新连接
watch(containerRosUrl, (url) => {
  if (url) connectRos()
})

// ---------- 面板聚焦态 ----------
const panelEl = ref<HTMLElement | null>(null)
const isFocused = ref(false)

function onPanelFocus() {
  isFocused.value = true
}
function onPanelBlur(e: FocusEvent) {
  if (panelEl.value?.contains(e.relatedTarget as Node)) return
  isFocused.value = false
}

// ---------- 按键状态 ----------
const keys = reactive({
  w: false,
  s: false,
  a: false,
  d: false
})

function updateMovement() {
  if (!isRunning.value) return
  let linear = 0
  let angular = 0
  if (keys.w) linear += config.value.linearSpeed
  if (keys.s) linear -= config.value.linearSpeed
  if (keys.a) angular += config.value.angularSpeed
  if (keys.d) angular -= config.value.angularSpeed
  publishTwist(linear, angular)
}

let moveTimer: ReturnType<typeof setInterval> | null = null

function startMoveLoop() {
  if (moveTimer) return
  moveTimer = setInterval(updateMovement, 100) // 10Hz
}

function stopMoveLoop() {
  if (moveTimer) {
    clearInterval(moveTimer)
    moveTimer = null
  }
  publishTwist(0, 0)
}

function onKeyDown(e: KeyboardEvent) {
  // 只有聚焦且 running 时才处理
  if (!isFocused.value || !isRunning.value) return
  // 防止 WASD/方向键/空格 触发页面滚动
  if (
    ['w', 's', 'a', 'd', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', ' '].includes(e.key)
  ) {
    e.preventDefault()
  }
  if (e.key === ' ') {
    emergencyStop()
    return
  }
  const map: Record<string, keyof typeof keys> = {
    w: 'w',
    ArrowUp: 'w',
    s: 's',
    ArrowDown: 's',
    a: 'a',
    ArrowLeft: 'a',
    d: 'd',
    ArrowRight: 'd'
  }
  const k = map[e.key]
  if (k) {
    keys[k] = true
    startMoveLoop()
  }
}

function onKeyUp(e: KeyboardEvent) {
  const map: Record<string, keyof typeof keys> = {
    w: 'w',
    ArrowUp: 'w',
    s: 's',
    ArrowDown: 's',
    a: 'a',
    ArrowLeft: 'a',
    d: 'd',
    ArrowRight: 'd'
  }
  const k = map[e.key]
  if (k) {
    keys[k] = false
    if (!keys.w && !keys.s && !keys.a && !keys.d) {
      stopMoveLoop()
    }
  }
}

// ---------- 主动按钮控制 ----------
function pressKey(key: keyof typeof keys) {
  if (!isRunning.value) return
  keys[key] = true
  startMoveLoop()
}

function releaseKey(key: keyof typeof keys) {
  keys[key] = false
  if (!keys.w && !keys.s && !keys.a && !keys.d) {
    stopMoveLoop()
  }
}

function emergencyStop() {
  Object.assign(keys, { w: false, s: false, a: false, d: false })
  stopMoveLoop()
  publishTwist(0, 0)
}

// ---------- 生命周期 ----------
onMounted(() => {
  registerPanel(props.panelId, 'KeyboardControl')
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('keyup', onKeyUp)
  connectRos()
})

onBeforeUnmount(() => {
  stopMoveLoop()
  if (ros) {
    ros.close()
    ros = null
  }
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('keyup', onKeyUp)
  unregisterPanel(props.panelId)
})
</script>

<template>
  <div ref="panelEl" class="keyboard-panel" tabindex="0" @focus="onPanelFocus" @blur="onPanelBlur">
    <!-- 容器未运行遮罩 -->
    <div v-if="!isRunning" class="keyboard-panel__overlay">
      <div class="keyboard-panel__overlay-icon">⚠</div>
      <div class="keyboard-panel__overlay-text">{{ statusText }}</div>
    </div>

    <!-- 主体内容 -->
    <template v-else>
      <!-- ROS 连接状态 -->
      <div class="keyboard-panel__status-bar">
        <span
          class="keyboard-panel__ros-dot"
          :class="rosConnected ? 'keyboard-panel__ros-dot--ok' : 'keyboard-panel__ros-dot--off'"
        ></span>
        <span class="keyboard-panel__ros-label">
          {{ rosConnected ? `ROS 已连接 · ${config.cmdVelTopic}` : 'ROS 未连接' }}
        </span>
        <span v-if="!isFocused" class="keyboard-panel__hint">点击面板激活键盘</span>
      </div>

      <!-- 方向控制区 -->
      <div class="keyboard-panel__dpad-wrap">
        <!-- 前进 -->
        <div class="keyboard-panel__dpad-row keyboard-panel__dpad-row--top">
          <button
            class="keyboard-panel__dpad-btn keyboard-panel__dpad-btn--primary"
            :class="{ 'keyboard-panel__dpad-btn--active': keys.w }"
            @mousedown="pressKey('w')"
            @mouseup="releaseKey('w')"
            @mouseleave="releaseKey('w')"
            @touchstart.prevent="pressKey('w')"
            @touchend.prevent="releaseKey('w')"
          >
            <span class="keyboard-panel__key-label">W</span>
            <span class="keyboard-panel__key-arrow">↑</span>
          </button>
        </div>

        <!-- 中间一排：左转 / 后退 / 右转 -->
        <div class="keyboard-panel__dpad-row">
          <button
            class="keyboard-panel__dpad-btn"
            :class="{ 'keyboard-panel__dpad-btn--active': keys.a }"
            @mousedown="pressKey('a')"
            @mouseup="releaseKey('a')"
            @mouseleave="releaseKey('a')"
            @touchstart.prevent="pressKey('a')"
            @touchend.prevent="releaseKey('a')"
          >
            <span class="keyboard-panel__key-label">A</span>
            <span class="keyboard-panel__key-arrow">←</span>
          </button>

          <button
            class="keyboard-panel__dpad-btn"
            :class="{ 'keyboard-panel__dpad-btn--active': keys.s }"
            @mousedown="pressKey('s')"
            @mouseup="releaseKey('s')"
            @mouseleave="releaseKey('s')"
            @touchstart.prevent="pressKey('s')"
            @touchend.prevent="releaseKey('s')"
          >
            <span class="keyboard-panel__key-label">S</span>
            <span class="keyboard-panel__key-arrow">↓</span>
          </button>

          <button
            class="keyboard-panel__dpad-btn"
            :class="{ 'keyboard-panel__dpad-btn--active': keys.d }"
            @mousedown="pressKey('d')"
            @mouseup="releaseKey('d')"
            @mouseleave="releaseKey('d')"
            @touchstart.prevent="pressKey('d')"
            @touchend.prevent="releaseKey('d')"
          >
            <span class="keyboard-panel__key-label">D</span>
            <span class="keyboard-panel__key-arrow">→</span>
          </button>
        </div>
      </div>

      <!-- 急停 -->
      <div class="keyboard-panel__stop-wrap">
        <button class="keyboard-panel__stop-btn" @click="emergencyStop">■ 急停 (Space)</button>
      </div>

      <!-- 速度信息 -->
      <div class="keyboard-panel__speed-info">
        <span>线速度 {{ config.linearSpeed }} m/s</span>
        <span class="keyboard-panel__speed-sep">·</span>
        <span>角速度 {{ config.angularSpeed }} rad/s</span>
      </div>
    </template>
  </div>
</template>

<style lang="less" scoped>
.keyboard-panel {
  position: relative;
  display: flex;
  width: 100%;
  height: 100%;
  background: #1e1e2e;
  outline: none;
  user-select: none;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;

  &__overlay {
    position: absolute;
    z-index: 10;
    display: flex;
    background: rgb(30 30 46 / 92%);
    inset: 0;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
  }

  &__overlay-icon {
    font-size: 32px;
    color: #f9e2af;
  }

  &__overlay-text {
    padding: 0 24px;
    font-size: 14px;
    color: #a6adc8;
    text-align: center;
  }

  &__status-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    color: #6c7086;
  }

  &__ros-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;

    &--ok {
      background: #a6e3a1;
    }

    &--off {
      background: #f38ba8;
    }
  }

  &__ros-label {
    color: #a6adc8;
  }

  &__hint {
    padding: 2px 8px;
    margin-left: 8px;
    font-size: 11px;
    color: #f9e2af;
    background: rgb(249 226 175 / 10%);
    border-radius: 4px;
  }

  &__dpad-wrap {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
  }

  &__dpad-row {
    display: flex;
    gap: 4px;

    &--top {
      justify-content: center;
    }
  }

  &__dpad-btn {
    display: flex;
    width: 72px;
    height: 72px;
    color: #cdd6f4;
    cursor: pointer;
    background: #27273a;
    border: 1px solid #313244;
    border-radius: 12px;
    transition: all 0.1s ease;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2px;
    -webkit-tap-highlight-color: transparent;

    &:hover {
      background: #313244;
      border-color: #585b70;
    }

    &--primary {
      background: #1e3a5f;
      border-color: #89b4fa;
    }

    &--active {
      color: #1e1e2e !important;
      background: #89b4fa !important;
      border-color: #89b4fa !important;
      transform: scale(0.95);
      box-shadow: 0 0 16px rgb(137 180 250 / 50%);
    }
  }

  &__key-label {
    font-size: 16px;
    font-weight: 700;
    line-height: 1;
  }

  &__key-arrow {
    font-size: 18px;
    line-height: 1;
    opacity: 0.7;
  }

  &__stop-wrap {
    width: 100%;
    max-width: 240px;
    padding: 0 16px;
  }

  &__stop-btn {
    width: 100%;
    height: 44px;
    font-size: 15px;
    font-weight: 600;
    letter-spacing: 1px;
    color: #f38ba8;
    cursor: pointer;
    background: rgb(243 139 168 / 12%);
    border: 2px solid #f38ba8;
    border-radius: 10px;
    transition: all 0.15s ease;

    &:hover {
      background: rgb(243 139 168 / 25%);
      box-shadow: 0 0 12px rgb(243 139 168 / 30%);
    }

    &:active {
      transform: scale(0.97);
    }
  }

  &__speed-info {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    color: #585b70;
  }

  &__speed-sep {
    color: #45475a;
  }
}
</style>
