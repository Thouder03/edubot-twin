<script setup lang="ts">
/**
 * ROS3DToolbar — 3D 视图右上角工具栏
 *
 * 职责：
 * - 根据 publishType 显示对应图标/文字
 * - 点击按钮切换发布模式
 * - 通过 emit 通知外部，不依赖任何 composable
 */
import { computed } from 'vue'
import { Icon } from '@/components/Icon'

// ---------- Props ----------
interface Props {
  isPublishing: boolean
  /** 当前发布类型（来自 PublishSettings: point | pose | pose_estimate） */
  publishType?: 'point' | 'pose' | 'pose_estimate'
}

const props = withDefaults(defineProps<Props>(), {
  publishType: 'pose'
})

// ---------- Emits ----------
const emit = defineEmits<{
  (e: 'toggle'): void
}>()

// 根据 publishType 显示不同提示
const LABELS: Record<string, string> = {
  point: '发布点位',
  pose: '发布位姿',
  pose_estimate: '发布初始估计'
}

const ICONS: Record<string, string> = {
  point: 'vi-carbon:radio-button-checked',
  pose: 'vi-carbon:send-alt',
  pose_estimate: 'vi-carbon:location'
}

const btnLabel = computed(() => LABELS[props.publishType] ?? '发布')
const btnIcon = computed(() => ICONS[props.publishType] ?? 'vi-carbon:send-alt')

const activeTitle = '点击取消发布模式'
const inactiveTitle = computed(() => `点击进入发布模式（${btnLabel.value}）`)
</script>

<template>
  <div class="ros3d-toolbar">
    <button
      class="toolbar-btn"
      :class="{ 'toolbar-btn--active': isPublishing }"
      :title="isPublishing ? activeTitle : inactiveTitle"
      @click="emit('toggle')"
    >
      <Icon :icon="isPublishing ? 'vi-carbon:close-outline' : btnIcon" :size="15" />
      <span>{{ isPublishing ? '取消发布' : btnLabel }}</span>
    </button>
  </div>
</template>

<style lang="less" scoped>
.ros3d-toolbar {
  display: flex;
  gap: 6px;
}

.toolbar-btn {
  display: flex;
  padding: 5px 11px;
  font-family: Consolas, Monaco, monospace;
  font-size: 11px;
  color: #cdd6f4;
  white-space: nowrap;
  cursor: pointer;
  background: rgb(17 17 27 / 85%);
  border: 1px solid rgb(69 71 90 / 50%);
  border-radius: 6px;
  transition: all 200ms ease;
  user-select: none;
  align-items: center;
  gap: 5px;
  backdrop-filter: blur(8px);

  &:hover {
    color: #89b4fa;
    background: rgb(30 30 46 / 95%);
    border-color: rgb(137 180 250 / 50%);
  }

  // 激活状态（发布中）
  &--active {
    color: #f38ba8;
    background: rgb(243 139 168 / 20%);
    border-color: rgb(243 139 168 / 60%);
    animation: blink-border 1.2s ease-in-out infinite;

    &:hover {
      background: rgb(243 139 168 / 30%);
      border-color: #f38ba8;
    }
  }
}

@keyframes blink-border {
  0%,
  100% {
    border-color: rgb(243 139 168 / 40%);
  }

  50% {
    border-color: rgb(243 139 168 / 90%);
  }
}
</style>
