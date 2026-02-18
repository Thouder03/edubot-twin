<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  ElFormItem,
  ElInput,
  ElInputNumber,
  ElRadioGroup,
  ElRadioButton,
  ElSelect,
  ElOption,
  ElColorPicker,
  ElTooltip
} from 'element-plus'
import { ArrowLeft, ArrowRight } from '@element-plus/icons-vue'
import { Icon } from '@/components/Icon'
import { SettingsTreeNode } from '../types/settings'

interface Props {
  nodeKey: string // Current node key (e.g. "base_laser_link")
  node: SettingsTreeNode
  path: string[] // Full path to this node (e.g. ["Transforms", "base_laser_link"])
  depth?: number
}

const props = withDefaults(defineProps<Props>(), {
  depth: 0
})

const emit = defineEmits<{
  (e: 'field-change', path: string[], value: any, input: string): void
}>()

// Collapsed state for this nested group
const isExpanded = ref(props.node.defaultExpanded ?? false)

function toggleExpand() {
  if (props.node.collapsible !== false) {
    isExpanded.value = !isExpanded.value
  }
}

// ---------- 可见性切换 ----------
/** 节点是否支持可见性切换（visible 字段不为 undefined） */
const supportsVisibility = computed(() => props.node.visible !== undefined)
/** 当前是否隐藏 */
const isHidden = computed(() => props.node.visible === false)
/** 鼠标是否悬浮在 header 上 */
const isHovered = ref(false)

/** 点击眼睛图标：切换 visible 状态，通过 field-change 事件上报 */
function handleVisibilityToggle(event: MouseEvent) {
  event.stopPropagation() // 不触发折叠/展开
  const newVisible = isHidden.value ? true : false
  // 使用特殊 input 标记 '__visible__'，由 PanelSettings 识别并转换为正确的 action
  emit('field-change', props.path, newVisible, '__visible__')
}

// Prepare fields with full path
const fields = computed(() => {
  return Object.entries(props.node.fields ?? {}).map(([key, field]) => ({
    key,
    path: [...props.path, key],
    ...field,
    label: field.label ?? key
  }))
})

// Prepare children nodes
const children = computed(() => {
  return Object.entries(props.node.children ?? {})
    .filter(([, child]) => child != null)
    .map(([key, child]) => ({
      key,
      path: [...props.path, key],
      node: child!
    }))
})

// Emits
function handleFieldChange(path: string[], value: any, input: string) {
  emit('field-change', path, value, input)
}
</script>

<template>
  <div class="settings-nested-group">
    <!-- Group Header (Only if depth > 0, top level handled by Accordion) -->
    <div
      v-if="depth > 0"
      class="nested-header"
      :class="{ 'is-collapsed': !isExpanded, 'is-hidden': isHidden }"
      @click="toggleExpand"
      @mouseenter="isHovered = true"
      @mouseleave="isHovered = false"
    >
      <Icon
        icon="vi-carbon:chevron-down"
        class="expand-icon"
        :class="{ 'is-rotated': !isExpanded }"
      />
      <span class="nested-label">{{ node.label || nodeKey }}</span>
      <div class="nested-actions">
        <!-- 可见性切换眼睛图标 -->
        <button
          v-if="supportsVisibility && (isHovered || isHidden)"
          type="button"
          class="visibility-btn"
          :title="isHidden ? '点击显示' : '点击隐藏'"
          @click.stop="handleVisibilityToggle"
        >
          <Icon
            :icon="isHidden ? 'vi-carbon:view-off' : 'vi-carbon:view'"
            :size="14"
            class="visibility-icon"
            :class="{ 'is-hidden-icon': isHidden }"
          />
        </button>
      </div>
    </div>

    <!-- Content (Fields + Children) -->
    <div
      v-if="depth === 0 || isExpanded"
      class="nested-content"
      :class="{ 'is-root': depth === 0 }"
    >
      <!-- 1. Fields -->
      <div v-if="fields.length > 0" class="nested-fields">
        <ElFormItem
          v-for="field in fields"
          :key="field.key"
          :label="field.label"
          :error="field.error"
          class="settings-field"
        >
          <template #label>
            <ElTooltip
              :content="field.label"
              placement="top-start"
              :show-after="500"
              effect="light"
            >
              <span>{{ field.label }}</span>
            </ElTooltip>
          </template>
          <!-- Text Input -->
          <ElInput
            v-if="field.input === 'string'"
            :model-value="field.value"
            :placeholder="field.placeholder"
            :disabled="field.disabled"
            :input-style="{ textAlign: 'center' }"
            @update:model-value="handleFieldChange(field.path, $event, field.input)"
          />

          <!-- Color Picker Custom -->
          <div v-else-if="field.input === 'rgb'" class="custom-color-input">
            <ElInput
              :model-value="field.value"
              placeholder="#RRGGBB"
              :disabled="field.disabled"
              :input-style="{ textAlign: 'center' }"
              @update:model-value="handleFieldChange(field.path, $event, field.input)"
            >
              <template #prefix>
                <div class="color-preview">
                  <ElColorPicker
                    :model-value="field.value"
                    size="small"
                    class="embedded-picker"
                    @change="(val) => handleFieldChange(field.path, val, field.input)"
                  />
                  <!-- Cover element to show color -->
                  <div class="color-cover" :style="{ backgroundColor: field.value }"></div>
                </div>
              </template>
            </ElInput>
          </div>

          <!-- Number Input -->
          <ElInputNumber
            v-else-if="field.input === 'number'"
            :model-value="field.value"
            :min="field.min"
            :max="field.max"
            :step="field.step ?? 1"
            :disabled="field.disabled"
            class="custom-input-number"
            :decrease-icon="ArrowLeft"
            :increase-icon="ArrowRight"
            @update:model-value="handleFieldChange(field.path, $event, field.input)"
          />

          <!-- Boolean Switch / Toggle -->
          <ElRadioGroup
            v-else-if="field.input === 'boolean'"
            :model-value="field.value"
            :disabled="field.disabled"
            class="custom-boolean-toggle"
            @change="(val) => handleFieldChange(field.path, val, field.input)"
          >
            <ElRadioButton :label="false">Off</ElRadioButton>
            <ElRadioButton :label="true">On</ElRadioButton>
          </ElRadioGroup>

          <!-- Select -->
          <ElSelect
            v-else-if="field.input === 'select'"
            :model-value="field.value"
            :disabled="field.disabled"
            @update:model-value="handleFieldChange(field.path, $event, field.input)"
          >
            <ElOption
              v-for="opt in field.options ?? []"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </ElSelect>

          <!-- Vec3 Input -->
          <div v-else-if="field.input === 'vec3'" class="vec3-input">
            <div v-for="(label, idx) in ['X', 'Y', 'Z']" :key="label" class="vec3-item">
              <span class="vec3-label">{{ field.labels?.[idx] ?? label }}</span>
              <ElInputNumber
                :model-value="field.value?.[idx] ?? 0"
                :precision="field.precision ?? 3"
                :step="field.step ?? 0.1"
                :disabled="field.disabled"
                class="custom-input-number"
                :decrease-icon="ArrowLeft"
                :increase-icon="ArrowRight"
                @update:model-value="
                  (val) => {
                    const newValue = [...(field.value ?? [0, 0, 0])]
                    newValue[idx] = val
                    handleFieldChange(field.path, newValue, field.input)
                  }
                "
              />
            </div>
          </div>

          <!-- Help Text -->
          <template v-if="field.help" #help>
            <span class="field-help">{{ field.help }}</span>
          </template>
        </ElFormItem>
      </div>

      <!-- 2. Children (Recursive) -->
      <div v-if="children.length > 0" class="nested-children">
        <SettingsNestedGroup
          v-for="child in children"
          :key="child.key"
          :node-key="child.key"
          :node="child.node"
          :path="child.path"
          :depth="depth + 1"
          @field-change="handleFieldChange"
        />
      </div>
    </div>
  </div>
</template>

<!-- Recursive component self-reference name -->
<script lang="ts">
export default {
  name: 'SettingsNestedGroup'
}
</script>

<style lang="less" scoped>
.settings-nested-group {
  width: 100%;
}

.nested-header {
  display: flex;
  align-items: center;
  cursor: pointer;
  padding: 4px 0;
  color: #cdd6f4;
  user-select: none;
  font-size: 13px;

  &:hover {
    color: #89b4fa;
    .expand-icon {
      color: #89b4fa;
    }
  }

  // 节点隐藏时整体变灰
  &.is-hidden {
    .nested-label {
      opacity: 0.4;
    }
    .expand-icon {
      opacity: 0.4;
    }
  }

  .expand-icon {
    transition: transform 0.2s;
    margin-right: 4px;
    font-size: 12px;
    color: #a6adc8;

    &.is-rotated {
      transform: rotate(-90deg);
    }
  }

  .nested-label {
    flex: 1;
    font-weight: 500;
  }
}

// 眼睛图标按钮
.visibility-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  background: transparent;
  border: none;
  border-radius: 3px;
  cursor: pointer;
  color: #6c7086;
  flex-shrink: 0;
  transition:
    color 0.15s,
    background 0.15s;

  &:hover {
    color: #cdd6f4;
    background: rgba(137, 180, 250, 0.12);
  }

  .visibility-icon {
    // 隐藏状态的图标用更明显的颜色
    &.is-hidden-icon {
      color: #585b70;
    }
  }
}

.nested-content {
  margin-left: 8px; // Indent children
  border-left: 1px solid #313244;

  &.is-root {
    margin-left: 0;
    border-left: none;
    padding-left: 0;
  }
}

.nested-fields {
  margin-bottom: 8px;
}

.nested-children {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

// Reuse styles from parent context via deep classes if possible,
// OR copy styles. For independence, copying main form styles here.

.vec3-input {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;

  .vec3-item {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 4px;
    min-width: 0;

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

.custom-boolean-toggle {
  width: 100%;
  display: flex;

  :deep(.el-radio-button) {
    flex: 1;
    .el-radio-button__inner {
      width: 100%;
      padding: 5px 0; /* Compact padding */
      background-color: #313244;
      border-color: #45475a;
      color: #cdd6f4;
      box-shadow: none;
    }
    &.is-active .el-radio-button__inner {
      background-color: #cdd6f4;
      color: #1e1e2e;
      border-color: #cdd6f4;
    }
  }
}

.custom-color-input {
  width: 100%;

  :deep(.el-input__prefix) {
    padding-left: 5px;
    display: flex;
    align-items: center;
  }

  .color-preview {
    position: relative;
    width: 18px;
    height: 18px;
    border-radius: 2px;
    overflow: hidden;
    border: 1px solid #45475a;
    cursor: pointer;

    /* The picker is hidden but clickable */
    .embedded-picker {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      opacity: 0;
      z-index: 10;
      padding: 0;

      :deep(.el-color-picker__trigger) {
        width: 100%;
        height: 100%;
        padding: 0;
        border: none;
      }
    }

    .color-cover {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      pointer-events: none; /* Let clicks pass to picker */
    }
  }

  :deep(.el-input__wrapper) {
    padding-left: 0;
  }
}

.field-help {
  color: #6c7086;
  font-size: 11px;
}

.custom-input-number {
  width: 100%;

  /* Hide controls by default */
  :deep(.el-input-number__decrease),
  :deep(.el-input-number__increase) {
    display: none;
    background: transparent;
    border: none;
    color: #a6adc8;

    &:hover {
      color: #cdd6f4;
    }
  }

  /* Show controls on hover */
  &:hover {
    :deep(.el-input-number__decrease),
    :deep(.el-input-number__increase) {
      display: flex;
    }
  }

  :deep(.el-input__wrapper) {
    padding-left: 30px !important; /* Space for left arrow */
    padding-right: 30px !important; /* Space for right arrow */
  }

  :deep(.el-input__inner) {
    text-align: center;
  }
}
</style>
