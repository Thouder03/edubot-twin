<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  ElFormItem,
  ElInput,
  ElInputNumber,
  ElSwitch,
  ElSelect,
  ElOption,
  ElColorPicker
} from 'element-plus'
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
// Default to respects node.defaultExpanded, or false
const isExpanded = ref(props.node.defaultExpanded ?? false)

function toggleExpand() {
  if (props.node.collapsible !== false) {
    isExpanded.value = !isExpanded.value
  }
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
      :class="{ 'is-collapsed': !isExpanded }"
      @click="toggleExpand"
    >
      <Icon
        icon="vi-carbon:chevron-down"
        class="expand-icon"
        :class="{ 'is-rotated': !isExpanded }"
      />
      <span class="nested-label">{{ node.label || nodeKey }}</span>
      <div class="nested-actions">
        <!-- Optional: Add menu actions here specifically for this nested node -->
      </div>
    </div>

    <!-- Content (Fields + Children) -->
    <div
      v-show="depth === 0 || isExpanded"
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
          <!-- Text Input -->
          <ElInput
            v-if="field.input === 'string'"
            :model-value="field.value"
            :placeholder="field.placeholder"
            :disabled="field.disabled"
            @update:model-value="handleFieldChange(field.path, $event, field.input)"
          />

          <!-- Color Picker -->
          <ElColorPicker
            v-else-if="field.input === 'rgb'"
            :model-value="field.value"
            :show-alpha="true"
            @change="(val) => handleFieldChange(field.path, val, field.input)"
          />

          <!-- Number Input -->
          <ElInputNumber
            v-else-if="field.input === 'number'"
            :model-value="field.value"
            :min="field.min"
            :max="field.max"
            :step="field.step ?? 1"
            :disabled="field.disabled"
            controls-position="right"
            @update:model-value="handleFieldChange(field.path, $event, field.input)"
          />

          <!-- Boolean Switch -->
          <ElSwitch
            v-else-if="field.input === 'boolean'"
            :model-value="field.value"
            :disabled="field.disabled"
            @update:model-value="handleFieldChange(field.path, $event, field.input)"
          />

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
                controls-position="right"
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

.nested-content {
  margin-left: 12px; // Indent children
  border-left: 1px solid #313244;
  padding-left: 12px;

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

.field-help {
  color: #6c7086;
  font-size: 11px;
}
</style>
