<script setup lang="ts">
/**
 * SimControlBar.vue - 仿真控制栏
 *
 * 显示 GzWeb 连接状态、仿真时间，提供 Play/Pause/Reset 控制。
 * 所有状态和操作来自 useGzBridge composable（无 props/emits）。
 */
import { ElButton, ElTooltip, ElDivider } from 'element-plus'
import { Icon } from '@/components/Icon'
import { useGzBridge } from '../composables/useGzBridge'

const {
  connectionStatus,
  isPaused,
  simTime,
  realTime,
  isConnected,
  togglePause,
  resetWorld,
  resetModels,
  resetView
} = useGzBridge()
</script>

<template>
  <div class="sim-control-bar">
    <!-- 连接状态指示灯 -->
    <ElTooltip :content="`连接状态: ${connectionStatus}`" placement="bottom">
      <span class="status-light" :class="connectionStatus"></span>
    </ElTooltip>

    <ElDivider direction="vertical" />

    <!-- Play / Pause -->
    <ElTooltip :content="isPaused ? '继续仿真' : '暂停仿真'" placement="bottom">
      <ElButton text :disabled="!isConnected" class="ctrl-btn" @click="togglePause">
        <Icon :icon="isPaused ? 'vi-carbon:play-filled' : 'vi-carbon:pause-filled'" :size="16" />
      </ElButton>
    </ElTooltip>

    <!-- Reset World -->
    <ElTooltip content="重置世界" placement="bottom">
      <ElButton text :disabled="!isConnected" class="ctrl-btn" @click="resetWorld">
        <Icon icon="vi-carbon:reset" :size="16" />
      </ElButton>
    </ElTooltip>

    <!-- Reset Models -->
    <ElTooltip content="重置模型姿态" placement="bottom">
      <ElButton text :disabled="!isConnected" class="ctrl-btn" @click="resetModels">
        <Icon icon="vi-carbon:undo" :size="16" />
      </ElButton>
    </ElTooltip>

    <!-- Reset View -->
    <ElTooltip content="重置视角" placement="bottom">
      <ElButton text :disabled="!isConnected" class="ctrl-btn" @click="resetView">
        <Icon icon="vi-carbon:center-to-fit" :size="16" />
      </ElButton>
    </ElTooltip>

    <ElDivider direction="vertical" />

    <!-- 时间显示 -->
    <div class="time-group">
      <div class="time-item">
        <span class="time-label">Real</span>
        <span class="time-value">{{ realTime }}</span>
      </div>
      <div class="time-item">
        <span class="time-label">Sim</span>
        <span class="time-value">{{ simTime }}</span>
      </div>
    </div>
  </div>
</template>

<style lang="less" scoped>
@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.4;
  }
}

.sim-control-bar {
  display: flex;
  align-items: center;
  gap: 2px;
  height: 100%;
}

// ── 连接状态灯 ──
.status-light {
  display: inline-block;
  width: 8px;
  height: 8px;
  margin: 0 4px;
  border-radius: 50%;
  transition: background-color 0.3s ease;

  &.disconnected {
    background: #6c7086;
  }

  &.connecting {
    background: #f9e2af;
    animation: pulse 1.5s infinite;
  }

  &.connected {
    background: #a6e3a1;
    box-shadow: 0 0 6px rgb(166 227 161 / 50%);
  }

  &.error {
    background: #f38ba8;
    box-shadow: 0 0 6px rgb(243 139 168 / 50%);
  }
}

// ── 控制按钮 ──
.ctrl-btn {
  min-height: unset;
  padding: 4px 6px;
  color: #bac2de;

  &:hover:not(:disabled) {
    color: #cdd6f4;
    background: rgb(255 255 255 / 6%);
  }

  &:disabled {
    color: #45475a;
  }
}

// ── 时间显示 ──
.time-group {
  display: flex;
  gap: 12px;
}

.time-item {
  display: flex;
  align-items: center;
  gap: 4px;

  .time-label {
    font-size: 11px;
    font-weight: 500;
    color: #6c7086;
    text-transform: uppercase;
  }

  .time-value {
    min-width: 90px;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 12px;
    color: #a6adc8;
  }
}

// ── 分割线 ──
:deep(.el-divider--vertical) {
  height: 16px;
  margin: 0 6px;
  border-color: #45475a;
}
</style>
