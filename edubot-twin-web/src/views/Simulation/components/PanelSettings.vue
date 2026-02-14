<script setup lang="ts">
/**
 * PanelSettings - 设置面板内容区
 *
 * Lichtblick 风格的可折叠分组设置面板
 */
import { computed, ref } from 'vue'
import {
  ElForm,
  ElFormItem,
  ElInput,
  ElInputNumber,
  ElSwitch,
  ElSelect,
  ElOption,
  ElColorPicker,
  ElCollapse,
  ElCollapseItem,
  ElDropdown,
  ElDropdownMenu,
  ElDropdownItem
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
  return Object.entries(selectedSettingsTree.value.nodes)
    .filter(([, node]) => node != null)
    .map(([key, node]) => ({
      key,
      label: node!.label || (key === 'undefined' ? 'Misc' : key),
      icon: node!.icon,
      collapsible: node!.collapsible ?? true,
      defaultExpanded: node!.defaultExpanded ?? false,
      fields: Object.entries(node!.fields ?? {}).map(([fieldKey, field]) => ({
        key: fieldKey,
        groupKey: key,
        ...field,
        label: field.label ?? fieldKey
      }))
    }))
})

// 展开的分组（使用分组 key 作为值）
const expandedGroups = ref<string[]>(
  settingsNodes.value.filter((g) => g.defaultExpanded).map((g) => g.key)
)

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

// ---------- 分组菜单处理 ----------
function handleGroupAction(groupKey: string, action: string) {
  console.log('[PanelSettings] Group action:', groupKey, action)
  // TODO: 实现重置、折叠等操作
}
</script>

<template>
  <div class="panel-settings">
    <template v-if="state.selectedPanelId && hasSettings">
      <!-- Accordion 分组 -->
      <ElCollapse v-model="expandedGroups" class="settings-collapse">
        <ElCollapseItem
          v-for="group in settingsNodes"
          :key="group.key"
          :name="group.key"
          :disabled="!group.collapsible"
        >
          <template #title>
            <div class="group-header">
              <Icon v-if="group.icon" :icon="group.icon" :size="16" class="group-icon" />
              <span class="group-label">{{ group.label }}</span>
              <span v-if="group.fields.length > 0" class="group-count"
                >({{ group.fields.length }})</span
              >
              <div class="group-actions">
                <ElDropdown @command="(cmd) => handleGroupAction(group.key, cmd)">
                  <Icon
                    icon="vi-carbon:overflow-menu-vertical"
                    :size="16"
                    class="group-menu-icon"
                    @click.stop
                  />
                  <template #dropdown>
                    <ElDropdownMenu>
                      <ElDropdownItem command="reset">Reset to default</ElDropdownItem>
                      <ElDropdownItem command="collapse-all">Collapse all</ElDropdownItem>
                    </ElDropdownMenu>
                  </template>
                </ElDropdown>
              </div>
            </div>
          </template>

          <!-- 字段表单 -->
          <ElForm label-position="left" label-width="90px" size="small" class="settings-form">
            <ElFormItem
              v-for="field in group.fields"
              :key="field.key"
              :label="field.label"
              :error="field.error"
              class="settings-field"
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

              <!-- Vec3 输入 -->
              <div v-else-if="field.input === 'vec3'" class="vec3-input">
                <div v-for="(label, idx) in ['X', 'Y', 'Z']" :key="label" class="vec3-item">
                  <span class="vec3-label">{{ field.labels?.[idx] ?? label }}</span>
                  <ElInputNumber
                    :model-value="field.value?.[idx] ?? 0"
                    :precision="field.precision ?? 3"
                    :step="field.step ?? 0.1"
                    :disabled="field.disabled"
                    controls-position="right"
                    @update:model-value="
                      (val) => {
                        const newValue = [...(field.value ?? [0, 0, 0])]
                        newValue[idx] = val
                        handleFieldChange(field.groupKey, field.key, newValue, field.input)
                      }
                    "
                  />
                </div>
              </div>

              <!-- help text -->
              <template v-if="field.help" #help>
                <span class="field-help">{{ field.help }}</span>
              </template>
            </ElFormItem>
          </ElForm>
        </ElCollapseItem>
      </ElCollapse>
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

  // Element Plus Collapse 暗色适配
  .settings-collapse {
    border: none;
    background: transparent;

    :deep(.el-collapse-item) {
      border-bottom: 1px solid #313244;
    }

    :deep(.el-collapse-item__header) {
      background: transparent;
      border: none;
      color: #cdd6f4;
      padding: 12px;
      height: auto;
      line-height: 1.4;
      font-size: 13px;

      &:hover {
        background: #313244;
      }
    }

    :deep(.el-collapse-item__wrap) {
      background: transparent;
      border: none;
    }

    :deep(.el-collapse-item__content) {
      padding: 0 12px 12px 12px;
      color: #cdd6f4;
    }

    :deep(.el-collapse-item__arrow) {
      color: #6c7086;
    }
  }

  // Element Plus Form 暗色适配
  :deep(.el-form-item__label) {
    color: #a6adc8 !important;
    font-size: 12px;
    padding-right: 12px;
    line-height: 28px;
  }

  :deep(.el-input__wrapper) {
    background-color: #313244;
    box-shadow: none;
    border: 1px solid #45475a;
    max-width: 140px; /* Limit input width */
    .el-input__inner {
      color: #cdd6f4;
      text-align: right; /* Align text to right like properties panel */
    }
  }

  :deep(.el-input-number) {
    width: 100%;
    .el-input__wrapper {
      max-width: 100%; /* InputNumber wrapper handles width differently */
      padding-left: 0;
      padding-right: 0;
    }
    .el-input__inner {
      text-align: center;
    }
  }

  :deep(.el-select) {
    width: 100%;
    .el-select__wrapper {
      background-color: #313244;
      box-shadow: none;
      border: 1px solid #45475a;
      // max-width: 140px; /* Limit select width */
    }
  }

  :deep(.el-form-item) {
    margin-bottom: 12px;
  }
}

.group-header {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  user-select: none;

  .group-icon {
    color: #89b4fa;
  }

  .group-label {
    flex: 1;
    font-weight: 500;
  }

  .group-count {
    color: #6c7086;
    font-size: 11px;
  }

  .group-actions {
    margin-left: auto;
    display: flex;
    align-items: center;

    .group-menu-icon {
      color: #6c7086;
      cursor: pointer;
      padding: 4px;
      border-radius: 4px;

      &:hover {
        color: #cdd6f4;
        background: rgba(137, 180, 250, 0.1);
      }
    }
  }
}

.settings-form {
  .settings-field {
    :deep(.el-form-item__content) {
      flex: 1;
    }
  }
}

.vec3-input {
  display: flex;
  gap: 8px;
  width: 100%;

  .vec3-item {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 4px;
    min-width: 0; // 防止 flex item 溢出

    .vec3-label {
      font-size: 10px;
      color: #6c7086;
      text-transform: uppercase;
    }

    :deep(.el-input-number) {
      width: 100%;
      .el-input__wrapper {
        padding-left: 0;
        padding-right: 0;
      }
    }
  }
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
