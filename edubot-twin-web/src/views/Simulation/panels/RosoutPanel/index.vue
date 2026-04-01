<script setup lang="ts">
import { ref } from 'vue'
import { useDesign } from '@/hooks/web/useDesign'
import LogItem from './LogItem.vue'
import { useRosout } from './composables/useRosout'
import { ElButton, ElInput } from 'element-plus'

const props = defineProps<{ panelId: string }>()

const { getPrefixCls } = useDesign()
const prefixCls = getPrefixCls('rosout-panel')

const listRef = ref<HTMLElement | null>(null)

const {
  filteredLogs,
  keyword,
  paused,
  rosConnected,
  isRunning,
  statusText,
  clearLogs,
  exportLogs
} = useRosout(props.panelId, listRef)
</script>

<template>
  <div :class="prefixCls">
    <div v-if="!isRunning" :class="`${prefixCls}__overlay`">
      <div :class="`${prefixCls}__overlay-icon`">⚠</div>
      <div :class="`${prefixCls}__overlay-text`">{{ statusText }}</div>
    </div>

    <template v-else>
      <div :class="`${prefixCls}__toolbar`">
        <div :class="`${prefixCls}__toolbar-left`">
          <span
            :class="[
              `${prefixCls}__dot`,
              rosConnected ? `${prefixCls}__dot--ok` : `${prefixCls}__dot--off`
            ]"
          ></span>
          <span :class="`${prefixCls}__status`">{{
            rosConnected ? 'ROS 已连接' : 'ROS 未连接'
          }}</span>
          <el-input
            v-model="keyword"
            size="small"
            placeholder="搜索关键词"
            clearable
            :class="`${prefixCls}__search`"
          />
        </div>

        <div :class="`${prefixCls}__toolbar-right`">
          <el-button size="small" @click="paused = !paused">
            {{ paused ? '恢复' : '暂停' }}
          </el-button>
          <el-button size="small" @click="clearLogs">清空</el-button>
          <el-button size="small" type="primary" @click="exportLogs">导出</el-button>
        </div>
      </div>

      <div ref="listRef" :class="`${prefixCls}__list`">
        <LogItem v-for="item in filteredLogs" :key="item.id" :item="item" />
        <div v-if="filteredLogs.length === 0" :class="`${prefixCls}__empty`">暂无日志</div>
      </div>
    </template>
  </div>
</template>

<style scoped lang="less">
@prefix: v-rosout-panel;

.@{prefix} {
  position: relative;
  display: flex;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: var(--el-bg-color);
  flex-direction: column;

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
    font-size: 14px;
    color: #a6adc8;
    text-align: center;
  }

  &__toolbar {
    display: flex;
    padding: 8px;
    border-bottom: 1px solid var(--el-border-color);
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }

  &__toolbar-left {
    display: flex;
    min-width: 0;
    align-items: center;
    gap: 8px;
    flex: 1;
  }

  &__toolbar-right {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  &__dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;

    &--ok {
      background: #67c23a;
    }

    &--off {
      background: #f56c6c;
    }
  }

  &__status {
    font-size: 12px;
    color: var(--el-text-color-secondary);
    white-space: nowrap;
  }

  &__search {
    max-width: 220px;
  }

  &__list {
    overflow: auto;
    flex: 1;
  }

  &__empty {
    padding: 20px;
    text-align: center;
    color: var(--el-text-color-placeholder);
  }
}
</style>
