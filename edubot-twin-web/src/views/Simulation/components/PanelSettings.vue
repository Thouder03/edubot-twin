<script setup lang="ts">
/**
 * PanelSettings - 设置面板内容区
 *
 * Lichtblick 风格的可折叠分组设置面板
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  ElForm,
  ElCollapse,
  ElCollapseItem,
  ElDropdown,
  ElDropdownMenu,
  ElDropdownItem
} from 'element-plus'
import { Icon } from '@/components/Icon'
import { usePanelState } from '../stores/panelState'
import type { SettingsTreeAction } from '../types/settings'
import SettingsNestedGroup from './SettingsNestedGroup.vue'

// ---------- 状态 ----------
const { state, selectedSettingsTree } = usePanelState()
const { t } = useI18n()

const hasSettings = computed(() => {
  return selectedSettingsTree.value !== null
})

const settingsNodes = computed(() => {
  if (!selectedSettingsTree.value) return []
  return Object.entries(selectedSettingsTree.value.nodes)
    .filter(([, node]) => node != null)
    .map(([key, node]) => ({
      key,
      label: node!.label || (key === 'undefined' ? t('threeDee.misc') : key),
      icon: node!.icon,
      collapsible: node!.collapsible ?? true,
      defaultExpanded: node!.defaultExpanded ?? false,
      rawNode: node
    }))
})

// 展开的分组（使用分组 key 作为值）
const expandedGroups = ref<string[]>(
  settingsNodes.value.filter((g) => g.defaultExpanded).map((g) => g.key)
)

// ---------- 字段变更处理 ----------
function handleFieldChange(path: string[], value: any, input: string) {
  if (!selectedSettingsTree.value) return
  const action: SettingsTreeAction = {
    action: 'update',
    payload: {
      path,
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
                      <ElDropdownItem command="reset">{{
                        t('threeDee.resetToDefault')
                      }}</ElDropdownItem>
                      <ElDropdownItem command="collapse-all">{{
                        t('threeDee.collapseAll')
                      }}</ElDropdownItem>
                    </ElDropdownMenu>
                  </template>
                </ElDropdown>
              </div>
            </div>
          </template>

          <!-- 递归渲染分组内容 -->
          <ElForm label-position="left" label-width="100px" size="small" class="settings-form">
            <SettingsNestedGroup
              :node-key="group.key"
              :node="group.rawNode as any"
              :path="[group.key]"
              :depth="0"
              @field-change="handleFieldChange"
            />
          </ElForm>
        </ElCollapseItem>
      </ElCollapse>
    </template>

    <!-- 空状态 -->
    <div v-else class="settings-empty">
      <Icon icon="vi-carbon:settings-adjust" :size="32" class="empty-icon" />
      <p>{{ t('threeDee.selectPanelToViewSettings') }}</p>
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

  // Custom Scrollbar
  &::-webkit-scrollbar {
    width: 6px;
    height: 6px;
  }
  &::-webkit-scrollbar-track {
    background: transparent;
  }
  &::-webkit-scrollbar-thumb {
    background: #45475a;
    border-radius: 3px;
  }
  &::-webkit-scrollbar-thumb:hover {
    background: #585b70;
  }

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
</style>
