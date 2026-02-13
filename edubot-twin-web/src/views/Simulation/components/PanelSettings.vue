<script setup lang="ts">
/**
 * PanelSettings - 设置面板内容区
 *
 * 动态渲染选中面板的设置树表单。
 * 由 SettingsSidebar 包裹使用，不再作为 GL 组件。
 */
import { computed } from 'vue'
import {
  ElForm,
  ElFormItem,
  ElInput,
  ElInputNumber,
  ElSwitch,
  ElSelect,
  ElOption,
  ElColorPicker
} from 'element-plus'
import { Icon } from '@/components/Icon'
import { usePanelState } from '../stores/panelState'
import type { SettingsTreeAction } from '../types/settings'

// ---------- 状态 ----------
const { state, selectedSettingsTree } = usePanelState()

const hasSettings = computed(() => {
  return selectedSettingsTree.value !== null
})

const settingsNodes = computed(() => {
  if (!selectedSettingsTree.value) return []
  return Object.entries(selectedSettingsTree.value.nodes).map(([key, node]) => ({
    key,
    label: node.label ?? key,
    fields: Object.entries(node.fields).map(([fieldKey, field]) => ({
      key: fieldKey,
      groupKey: key,
      ...field
    }))
  }))
})

// ---------- 字段变更处理 ----------
function handleFieldChange(groupKey: string, fieldKey: string, value: any, input: string) {
  if (!selectedSettingsTree.value) return
  const action: SettingsTreeAction = {
    action: 'update',
    payload: {
      path: [groupKey, fieldKey],
      value,
      input
    }
  }
  selectedSettingsTree.value.actionHandler(action)
}
</script>

<template>
  <div class="panel-settings">
    <template v-if="state.selectedPanelId && hasSettings">
      <!-- 设置组 -->
      <div v-for="group in settingsNodes" :key="group.key" class="settings-group">
        <div class="settings-group-label">{{ group.label }}</div>
        <ElForm label-position="top" size="small" class="settings-form">
          <ElFormItem
            v-for="field in group.fields"
            :key="field.key"
            :label="field.label"
            :error="field.error"
          >
            <!-- 文本输入 -->
            <ElInput
              v-if="field.input === 'string'"
              :model-value="field.value"
              :placeholder="field.placeholder"
              :disabled="field.disabled"
              @update:model-value="
                handleFieldChange(field.groupKey, field.key, $event, field.input)
              "
            />

            <!-- 颜色选择器 -->
            <ElColorPicker
              v-else-if="field.input === 'rgb'"
              :model-value="field.value"
              :show-alpha="true"
              @change="(val) => handleFieldChange(field.groupKey, field.key, val, field.input)"
            />

            <!-- 数字输入 -->
            <ElInputNumber
              v-else-if="field.input === 'number'"
              :model-value="field.value"
              :min="field.min"
              :max="field.max"
              :step="field.step ?? 1"
              :disabled="field.disabled"
              controls-position="right"
              @update:model-value="
                handleFieldChange(field.groupKey, field.key, $event, field.input)
              "
            />

            <!-- 布尔开关 -->
            <ElSwitch
              v-else-if="field.input === 'boolean'"
              :model-value="field.value"
              :disabled="field.disabled"
              @update:model-value="
                handleFieldChange(field.groupKey, field.key, $event, field.input)
              "
            />

            <!-- 选择框 -->
            <ElSelect
              v-else-if="field.input === 'select'"
              :model-value="field.value"
              :disabled="field.disabled"
              @update:model-value="
                handleFieldChange(field.groupKey, field.key, $event, field.input)
              "
            >
              <ElOption
                v-for="opt in field.options ?? []"
                :key="opt.value"
                :label="opt.label"
                :value="opt.value"
              />
            </ElSelect>

            <!-- help text -->
            <template v-if="field.help" #[`help`]>
              <span class="field-help">{{ field.help }}</span>
            </template>
          </ElFormItem>
        </ElForm>
      </div>
    </template>

    <!-- 空状态 -->
    <div v-else class="settings-empty">
      <Icon icon="vi-carbon:settings-adjust" :size="32" class="empty-icon" />
      <p>选择一个面板以查看设置</p>
    </div>
  </div>
</template>

<style lang="less" scoped>
.panel-settings {
  width: 100%;
  height: 100%;
  background: #1e1e2e;
  overflow-y: auto;
  padding: 0;
  user-select: none;

  // Element Plus 暗色适配
  :deep(.el-form-item__label) {
    color: #a6adc8 !important;
    font-size: 12px;
    padding-bottom: 4px;
  }

  :deep(.el-input__wrapper) {
    background-color: #313244;
    box-shadow: none;
    border: 1px solid #45475a;
    .el-input__inner {
      color: #cdd6f4;
    }
  }
  :deep(.el-input__wrapper:hover) {
    border-color: #585b70;
  }
  :deep(.el-input__wrapper.is-focus) {
    border-color: #89b4fa;
  }

  :deep(.el-input-number) {
    width: 100%;
    .el-input__wrapper {
      background-color: #313244;
      box-shadow: none;
      border: 1px solid #45475a;
    }
  }

  :deep(.el-select) {
    width: 100%;
    .el-select__wrapper {
      background-color: #313244;
      box-shadow: none;
      border: 1px solid #45475a;
    }
  }

  :deep(.el-form-item) {
    margin-bottom: 14px;
  }
}

.settings-group {
  padding: 8px 12px;
  border-bottom: 1px solid #313244;
}

.settings-group-label {
  color: #6c7086;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
}

.settings-empty {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #585b70;

  .empty-icon {
    margin-bottom: 12px;
  }
  p {
    font-size: 13px;
  }
}

.field-help {
  color: #6c7086;
  font-size: 11px;
}
</style>
