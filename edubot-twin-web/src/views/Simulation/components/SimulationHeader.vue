<script setup lang="ts">
/**
 * SimulationHeader.vue - 仿真页面顶部工具栏
 *
 * 集成 SimControlBar 仿真控制栏（中间区域）
 */
import { ElButton, ElDropdown, ElDropdownMenu, ElDropdownItem, ElDivider } from 'element-plus'
import { Icon } from '@/components/Icon'
import { layoutPresets, availablePanels } from '../config/predefined-layouts'
import SimControlBar from './SimControlBar.vue'
import type { LayoutConfig } from 'golden-layout'
import { confirmExit } from '../composables/useExitConfirm'

interface ExperimentContext {
  experiment_name?: string
  version_name?: string
  environment_key?: string
}

interface Emits {
  (e: 'layoutChange', config: LayoutConfig): void
  (e: 'addPanel', type: string, title: string): void
  (e: 'back', mode: 'temporary' | 'stopAndExit'): void
}

const props = defineProps<{
  experimentContext?: ExperimentContext | null
}>()

const emit = defineEmits<Emits>()

function handleBack() {
  confirmExit((mode) => emit('back', mode))
}

function handleLayoutChange(key: string) {
  const preset = layoutPresets.find((p) => p.key === key)
  if (preset) {
    emit('layoutChange', preset.config)
  }
}

function handleAddPanel(type: string, label: string) {
  emit('addPanel', type, label)
}
</script>

<template>
  <div class="simulation-header">
    <!-- 左侧: 返回 + 标题 -->
    <div class="header-left">
      <ElButton text :icon="undefined" class="back-btn" @click="handleBack">
        <Icon icon="vi-carbon:arrow-left" :size="18" class="mr-4px" />
        返回
      </ElButton>
      <ElDivider direction="vertical" />
      <div class="header-title-wrap">
        <span class="header-title">
          <Icon icon="vi-carbon:cube" :size="18" class="mr-6px" />
          机器人仿真工作台
        </span>
        <span
          v-if="props.experimentContext?.experiment_name || props.experimentContext?.version_name"
          class="header-subtitle"
        >
          {{ props.experimentContext?.experiment_name || '-' }} /
          {{ props.experimentContext?.version_name || '-' }}
          <template v-if="props.experimentContext?.environment_key">
            ({{ props.experimentContext.environment_key }})
          </template>
        </span>
      </div>
    </div>

    <!-- 中间: 仿真控制栏 -->
    <SimControlBar />

    <!-- 右侧: 布局切换 + 添加面板 -->
    <div class="header-right">
      <!-- 布局预设 -->
      <ElDropdown trigger="click" @command="handleLayoutChange">
        <ElButton text class="header-action-btn">
          <Icon icon="vi-carbon:grid" :size="16" class="mr-4px" />
          布局
        </ElButton>
        <template #dropdown>
          <ElDropdownMenu>
            <ElDropdownItem v-for="preset in layoutPresets" :key="preset.key" :command="preset.key">
              {{ preset.label }}
            </ElDropdownItem>
          </ElDropdownMenu>
        </template>
      </ElDropdown>

      <!-- 添加面板 -->
      <ElDropdown
        trigger="click"
        @command="
          (cmd: string) => {
            const panel = availablePanels.find((p) => p.type === cmd)
            if (panel) handleAddPanel(panel.type, panel.label)
          }
        "
      >
        <ElButton text class="header-action-btn">
          <Icon icon="vi-carbon:add" :size="16" class="mr-4px" />
          添加面板
        </ElButton>
        <template #dropdown>
          <ElDropdownMenu>
            <ElDropdownItem
              v-for="panel in availablePanels"
              :key="panel.type"
              :command="panel.type"
            >
              {{ panel.label }}
            </ElDropdownItem>
          </ElDropdownMenu>
        </template>
      </ElDropdown>
    </div>
  </div>
</template>

<style lang="less" scoped>
.simulation-header {
  display: flex;
  height: 40px;
  padding: 0 12px;
  background: #181825;
  border-bottom: 1px solid #313244;
  user-select: none;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 4px;

  .back-btn {
    font-size: 13px;
    color: #bac2de;

    &:hover {
      color: #cdd6f4;
    }
  }

  .header-title-wrap {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .header-title {
    display: flex;
    font-size: 14px;
    font-weight: 500;
    color: #cdd6f4;
    align-items: center;
  }

  .header-subtitle {
    margin-left: 24px;
    color: #a6adc8;
    font-size: 12px;
    line-height: 1;
  }
}

.header-right {
  display: flex;
  align-items: center;
  gap: 4px;

  .header-action-btn {
    font-size: 13px;
    color: #bac2de;

    &:hover {
      color: #cdd6f4;
    }
  }
}

:deep(.el-divider--vertical) {
  height: 16px;
  margin: 0 8px;
  border-color: #45475a;
}
</style>
