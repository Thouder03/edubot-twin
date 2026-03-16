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
  point: 'vi-carbon:location',
  pose: 'vi-carbon:send-alt',
  pose_estimate: 'vi-carbon:target'
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
  align-items: center;
  gap: 5px;
  padding: 5px 11px;
  background: rgba(17, 17, 27, 0.85);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(69, 71, 90, 0.5);
  border-radius: 6px;
  color: #cdd6f4;
  font-size: 11px;
  font-family: 'Consolas', 'Monaco', monospace;
  cursor: pointer;
  transition: all 200ms ease;
  user-select: none;
  white-space: nowrap;

  &:hover {
    background: rgba(30, 30, 46, 0.95);
    border-color: rgba(137, 180, 250, 0.5);
    color: #89b4fa;
  }

  // 激活状态（发布中）
  &--active {
    background: rgba(243, 139, 168, 0.2);
    border-color: rgba(243, 139, 168, 0.6);
    color: #f38ba8;
    animation: blink-border 1.2s ease-in-out infinite;

    &:hover {
      background: rgba(243, 139, 168, 0.3);
      border-color: #f38ba8;
    }
  }
}

@keyframes blink-border {
  0%,
  100% {
    border-color: rgba(243, 139, 168, 0.4);
  }
  50% {
    border-color: rgba(243, 139, 168, 0.9);
  }
}
</style>
