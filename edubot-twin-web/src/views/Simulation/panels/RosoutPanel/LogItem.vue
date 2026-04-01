<script setup lang="ts">
import { computed } from 'vue'
import { ElIcon } from 'element-plus'
import {
  CircleCheckFilled,
  InfoFilled,
  WarningFilled,
  CircleCloseFilled
} from '@element-plus/icons-vue'
import type { RosoutLogEntry } from './composables/useRosout'

const props = defineProps<{
  item: RosoutLogEntry
}>()

const levelMeta = computed(() => {
  const map: Record<number, { label: string; color: string; icon: unknown }> = {
    1: { label: 'DEBUG', color: '#909399', icon: InfoFilled },
    2: { label: 'INFO', color: '#409eff', icon: CircleCheckFilled },
    4: { label: 'WARN', color: '#e6a23c', icon: WarningFilled },
    8: { label: 'ERROR', color: '#f56c6c', icon: CircleCloseFilled },
    16: { label: 'FATAL', color: '#f56c6c', icon: CircleCloseFilled }
  }
  return map[props.item.level] ?? map[2]
})

const timeText = computed(() => {
  const d = props.item.timestamp
  const pad = (v: number) => String(v).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
})
</script>

<template>
  <div class="v-rosout-log-item">
    <div class="v-rosout-log-item__left">
      <span class="v-rosout-log-item__time">{{ timeText }}</span>
      <span class="v-rosout-log-item__level" :style="{ color: levelMeta.color }">
        <ElIcon><component :is="levelMeta.icon" /></ElIcon>
        {{ levelMeta.label }}
      </span>
      <span class="v-rosout-log-item__node">{{ item.node }}</span>
    </div>
    <div class="v-rosout-log-item__message">{{ item.message }}</div>
  </div>
</template>

<style scoped lang="less">
.v-rosout-log-item {
  display: flex;
  padding: 6px 10px;
  font-size: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  flex-direction: column;
  gap: 4px;

  &__left {
    display: flex;
    align-items: center;
    gap: 10px;
    color: var(--el-text-color-secondary);
  }

  &__time {
    width: 64px;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  }

  &__level {
    display: flex;
    width: 78px;
    font-weight: 600;
    align-items: center;
    gap: 4px;
  }

  &__node {
    max-width: 220px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--el-color-primary);
  }

  &__message {
    line-height: 1.4;
    color: var(--el-text-color-primary);
    word-break: break-word;
  }
}
</style>
