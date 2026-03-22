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
.sim-control-bar {
  display: flex;
  align-items: center;
  gap: 2px;
  height: 100%;
}

// ── 连接状态灯 ──
.status-light {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
  margin: 0 4px;
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
    box-shadow: 0 0 6px rgba(166, 227, 161, 0.5);
  }

  &.error {
    background: #f38ba8;
    box-shadow: 0 0 6px rgba(243, 139, 168, 0.5);
  }
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.4;
  }
}

// ── 控制按钮 ──
.ctrl-btn {
  color: #bac2de;
  padding: 4px 6px;
  min-height: unset;

  &:hover:not(:disabled) {
    color: #cdd6f4;
    background: rgba(255, 255, 255, 0.06);
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
    color: #6c7086;
    font-size: 11px;
    font-weight: 500;
    text-transform: uppercase;
  }

  .time-value {
    color: #a6adc8;
    font-size: 12px;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    min-width: 90px;
  }
}

// ── 分割线 ──
:deep(.el-divider--vertical) {
  border-color: #45475a;
  margin: 0 6px;
  height: 16px;
}
</style>
