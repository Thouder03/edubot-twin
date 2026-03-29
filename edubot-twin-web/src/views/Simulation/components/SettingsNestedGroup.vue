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
  ElTooltip,
  ElAutocomplete,
  ElDropdown,
  ElDropdownMenu,
  ElDropdownItem
} from 'element-plus'
import { ArrowLeft, ArrowRight } from '@element-plus/icons-vue'
import { Icon } from '@/components/Icon'
import { SettingsTreeNode } from '../types/settings'
import { useI18n } from '@/hooks/web/useI18n'

const { t } = useI18n()

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
  (e: 'node-action', path: string[], command: string): void
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

/** 处理菜单命令 */
function handleActionCommand(command: string) {
  emit('node-action', props.path, command)
}

/** 冒泡处理子节点的 node-action 事件 */
function handleNodeAction(path: string[], command: string) {
  emit('node-action', path, command)
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

function handleGradientChange(
  path: string[],
  value: readonly string[] | undefined,
  index: 0 | 1,
  newColor: string | null
) {
  const newValue = [...(value ?? ['#ffffff', '#ffffff'])]
  newValue[index] = newColor || '#ffffff'
  emit('field-change', path, newValue, 'gradient')
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
        icon="vi-carbon:caret-right"
        class="expand-icon"
        :class="{ 'is-rotated': isExpanded }"
      />
      <span class="nested-label">{{ node.label || nodeKey }}</span>
      <div class="nested-actions">
        <!-- 可见性切换眼睛图标 -->
        <button
          v-if="supportsVisibility && (isHovered || isHidden)"
          type="button"
          class="visibility-btn"
          :title="isHidden ? t('settings.clickToShow') : t('settings.clickToHide')"
          @click.stop="handleVisibilityToggle"
        >
          <Icon
            :icon="isHidden ? 'vi-carbon:view-off' : 'vi-carbon:view'"
            :size="14"
            class="visibility-icon"
            :class="{ 'is-hidden-icon': isHidden }"
          />
        </button>

        <!-- 菜单按钮 -->
        <ElDropdown v-if="node.actions?.length" trigger="click" @command="handleActionCommand">
          <button type="button" class="menu-btn" @click.stop>
            <Icon icon="vi-carbon:overflow-menu-vertical" :size="18" />
          </button>
          <template #dropdown>
            <ElDropdownMenu>
              <ElDropdownItem
                v-for="action in node.actions"
                :key="action.id"
                :command="action.id"
                :divided="action.divided"
                :disabled="action.disabled"
              >
                <Icon v-if="action.icon" :icon="action.icon" :size="14" class="action-icon" />
                {{ action.label }}
              </ElDropdownItem>
            </ElDropdownMenu>
          </template>
        </ElDropdown>
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
          class="settings-field"
          :class="{ 'has-error': field.error }"
        >
          <template #label>
            <div class="label-with-error" @click.prevent>
              <ElTooltip
                :content="field.help ?? field.label"
                placement="top-start"
                :show-after="500"
                effect="light"
              >
                <span class="label-text">{{ field.label }}</span>
              </ElTooltip>
              <ElTooltip v-if="field.error" :content="field.error" placement="top" effect="light">
                <Icon icon="vi-carbon:warning-filled" :size="14" class="error-icon" />
              </ElTooltip>
            </div>
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
            :precision="field.precision"
            :placeholder="field.placeholder ?? ''"
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
            :placeholder="field.placeholder ?? ''"
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
                :step="field.step ?? 1"
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

          <!-- Vec2 Input -->
          <div v-else-if="field.input === 'vec2'" class="vec3-input">
            <div v-for="(label, idx) in ['X', 'Y']" :key="label" class="vec3-item">
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
                    const newValue = [...(field.value ?? [0, 0])]
                    newValue[idx] = val
                    handleFieldChange(field.path, newValue, field.input)
                  }
                "
              />
            </div>
          </div>

          <!-- RGBA Color Picker（带透明度） -->
          <div v-else-if="field.input === 'rgba'" class="custom-color-input">
            <ElInput
              :model-value="field.value"
              placeholder="#RRGGBBAA"
              :disabled="field.disabled"
              :input-style="{ textAlign: 'center' }"
              @update:model-value="handleFieldChange(field.path, $event, field.input)"
            >
              <template #prefix>
                <div class="color-preview">
                  <ElColorPicker
                    :model-value="field.value"
                    size="small"
                    show-alpha
                    color-format="hex"
                    class="embedded-picker"
                    @change="(val) => handleFieldChange(field.path, val, field.input)"
                  />
                  <div class="color-cover" :style="{ backgroundColor: field.value }"></div>
                </div>
              </template>
            </ElInput>
          </div>

          <!-- Gradient 渐变颜色（双颜色选择器） -->
          <div v-else-if="field.input === 'gradient'" class="gradient-input">
            <ElColorPicker
              :model-value="field.value?.[0] ?? '#ffffff'"
              size="small"
              show-alpha
              color-format="hex"
              @change="
                (val: string | null) => handleGradientChange(field.path, field.value, 0, val)
              "
            />
            <span class="gradient-arrow">→</span>
            <ElColorPicker
              :model-value="field.value?.[1] ?? '#ffffff'"
              size="small"
              show-alpha
              color-format="hex"
              @change="
                (val: string | null) => handleGradientChange(field.path, field.value, 1, val)
              "
            />
          </div>

          <!-- Autocomplete（带候选项的文本输入，用于 followTf 等帧选择） -->
          <ElAutocomplete
            v-else-if="field.input === 'autocomplete'"
            :model-value="field.value ?? ''"
            :fetch-suggestions="
              (query: string, cb: (results: { value: string }[]) => void) => {
                const opts = (field.options ?? []).map((o) => ({ value: String(o.value) }))
                cb(query ? opts.filter((o) => o.value.includes(query)) : opts)
              }
            "
            :placeholder="field.placeholder ?? ''"
            :disabled="field.disabled"
            clearable
            class="autocomplete-input"
            @select="
              (item: { value: string }) => handleFieldChange(field.path, item.value, field.input)
            "
            @change="(val: string) => handleFieldChange(field.path, val, field.input)"
          />

          <!-- Readonly 只读文本展示 -->
          <ElInput
            v-else-if="field.readonly === true"
            :model-value="field.value != null ? String(field.value) : '—'"
            :disabled="true"
            :input-style="{ textAlign: 'center', color: '#6c7086' }"
          />

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
          @node-action="handleNodeAction"
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
  min-width: 0;
  padding: 4px 8px 4px 22px;
  font-size: 12px;
  color: #cdd6f4;
  cursor: pointer;
  border-radius: 4px;
  user-select: none;
  align-items: center;

  &:hover {
    background: rgb(49 50 68 / 60%); /* Lichtblick: 更柔和的 hover */

    .expand-icon {
      color: #89b4fa;
    }
  }

  // 节点隐藏时整体变灰
  &.is-hidden {
    opacity: 0.6; /* Lichtblick: 整体透明度 */
  }

  .expand-icon {
    margin-right: 4px;
    font-size: 12px;
    color: #a6adc8;
    transition: transform 0.2s;
    flex-shrink: 0;

    &.is-rotated {
      transform: rotate(90deg);
    }
  }

  .nested-label {
    min-width: 0;
    overflow: hidden;
    font-weight: 600;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .nested-actions {
    display: flex;
    align-items: center;
    gap: 4px;
    margin-left: auto;
    flex-shrink: 0;
  }
}

// 眼睛图标按钮
.visibility-btn {
  display: flex;
  width: 20px;
  height: 20px;
  padding: 0;
  color: #6c7086;
  cursor: pointer;
  background: transparent;
  border: none;
  border-radius: 3px;
  transition:
    color 0.15s,
    background 0.15s;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;

  &:hover {
    color: #cdd6f4;
    background: rgb(137 180 250 / 15%);
  }

  .visibility-icon {
    // 隐藏状态的图标用更明显的颜色
    &.is-hidden-icon {
      color: #585b70;
    }
  }
}

// 菜单按钮
.menu-btn {
  display: flex;
  width: 20px;
  height: 20px;
  padding: 0;
  color: #6c7086;
  cursor: pointer;
  background: transparent;
  border: none;
  border-radius: 3px;
  transition:
    color 0.15s,
    background 0.15s;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;

  &:hover {
    color: #cdd6f4;
    background: rgb(137 180 250 / 15%);
  }
}

.nested-content {
  margin-top: 4px; // Lichtblick 样式：标题与内容间距 4px

  &.is-root {
    padding-left: 0;
    margin-top: 4px; // Lichtblick 样式：标题与内容间距 4px
    margin-left: 0;
    border-left: none;
  }
}

.nested-fields {
  display: flex;
  flex-direction: column;
  gap: 2px; /* Lichtblick: 紧凑间距 */
}

// Label 区域布局（支持错误图标）
.label-with-error {
  display: flex;
  align-items: center;
  gap: 4px;
  width: 100%;
  min-width: 0;

  .label-text {
    min-width: 0;
    overflow: hidden;
    text-align: right;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1;
  }

  .error-icon {
    color: #f38ba8;
    flex-shrink: 0;
    cursor: help;
  }
}

// 错误状态的表单项
:deep(.el-form-item.has-error) {
  .el-input__wrapper,
  .el-select__wrapper {
    border-color: #f38ba8 !important;
  }

  .el-input-number .el-input__wrapper {
    border-color: #f38ba8 !important;
  }
}

.nested-children {
  display: flex;
  flex-direction: column;
  gap: 2px; /* Lichtblick: 紧凑间距 */
}

.vec3-input {
  display: flex;
  flex-direction: column;
  gap: 2px; /* Lichtblick: 紧凑间距 */
  width: 100%;

  .vec3-item {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 8px; /* Lichtblick: theme.spacing(1) */
    min-width: 0;

    .vec3-label {
      font-size: 10px;
      color: #6c7086;
      text-transform: uppercase;
    }

    :deep(.el-input-number) {
      width: 100%;

      .el-input__wrapper {
        min-height: 28px; /* 恢复合适的最小高度 */
        padding-right: 0;
        padding-left: 0;
        padding-block: 4px; /* 调整内边距 */
      }
    }
  }
}

// Autocomplete 输入框
.autocomplete-input {
  width: 100%;

  :deep(.el-input__wrapper) {
    min-height: 28px; /* 恢复合适的最小高度 */
    background-color: #313244;
    border: 1px solid rgb(69 71 90 / 50%);
    transition: border-color 0.2s;
    padding-block: 4px; /* 调整内边距 */

    &:hover {
      border-color: #45475a;
    }
  }

  :deep(.el-input__inner) {
    height: auto;
    line-height: 1.5;
    color: #cdd6f4;
    text-align: center;
  }
}

.custom-boolean-toggle {
  display: flex;
  width: 100%;
  min-height: 28px; /* 确保最小高度 */
  padding: 3px; /* 调整内边距 */
  background-color: #313244; /* Lichtblick: action.hover */
  border-radius: 4px;
  gap: 2px; /* Lichtblick: theme.spacing(0.25) */

  :deep(.el-radio-button) {
    flex: 1;

    .el-radio-button__inner {
      width: 100%;
      padding: 4px 12px; /* 调整垂直内边距 */
      line-height: 1.5; /* 调整行高 */
      color: #cdd6f4;
      background-color: transparent;
      border: none;
      border-radius: 4px;
      box-shadow: none;
      transition: background 0.2s;
    }

    &.is-active .el-radio-button__inner {
      color: #cdd6f4;
      background-color: #1e1e2e; /* Lichtblick: background.paper */
      box-shadow: none;
    }
  }
}

.custom-color-input {
  width: 100%;

  :deep(.el-input__prefix) {
    display: flex;
    padding-left: 5px;
    align-items: center;
  }

  .color-preview {
    position: relative;
    width: 18px;
    height: 18px;
    overflow: hidden;
    cursor: pointer;
    border: 1px solid rgb(69 71 90 / 50%);
    border-radius: 2px;

    .embedded-picker {
      position: absolute;
      top: 0;
      left: 0;
      z-index: 10;
      width: 100%;
      height: 100%;
      padding: 0;
      opacity: 0;

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
      pointer-events: none;
    }
  }

  :deep(.el-input__wrapper) {
    min-height: 28px; /* 恢复合适的最小高度 */
    padding-left: 0;
    border: 1px solid rgb(69 71 90 / 50%);
    transition: border-color 0.2s;
    padding-block: 4px; /* 调整内边距 */

    &:hover {
      border-color: #45475a;
    }
  }

  :deep(.el-input__inner) {
    height: auto;
    line-height: 1.5;
  }
}

.field-help {
  font-size: 12px;
  color: #6c7086;
}

.custom-input-number {
  width: 100%;

  /* Hide controls by default */
  :deep(.el-input-number__decrease),
  :deep(.el-input-number__increase) {
    display: none;
    color: #a6adc8;
    background: transparent;
    border: none;
    transition: color 0.2s;

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
    min-height: 28px; /* 恢复合适的最小高度 */
    padding-right: 30px !important;
    padding-left: 30px !important;
    border: 1px solid rgb(69 71 90 / 50%);
    transition: border-color 0.2s;
    padding-block: 4px; /* 调整内边距 */

    &:hover {
      border-color: #45475a;
    }
  }

  :deep(.el-input__inner) {
    height: auto;
    line-height: 1.5;
    text-align: center;
  }
}

.gradient-input {
  display: flex;
  align-items: center;
  gap: 8px; /* Lichtblick: theme.spacing(1) */
  width: 100%;
  justify-content: center;

  .gradient-arrow {
    font-size: 14px;
    color: #6c7086;
    user-select: none;
  }

  :deep(.el-color-picker__trigger) {
    width: 50px;
    min-height: 28px; /* 恢复合适的最小高度 */
    padding: 4px; /* 调整内边距 */
    border: 1px solid rgb(69 71 90 / 50%);
    transition: border-color 0.2s;

    &:hover {
      border-color: #45475a;
    }
  }
}
</style>
