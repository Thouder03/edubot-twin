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
      actions: node!.actions, // 自定义菜单项
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

  // 特殊处理：__visible__ 是可见性切换的内部标记
  // 将其转换为标准的 update action，path 去掉最后的 __visible__ 段
  if (input === '__visible__') {
    const action: SettingsTreeAction = {
      action: 'update',
      payload: {
        path: path, // path 已经是节点路径（不含 __visible__）
        value,
        input: 'boolean'
      }
    }
    selectedSettingsTree.value.actionHandler(action)
    return
  }

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
              <div v-if="group.actions?.length" class="group-actions">
                <ElDropdown trigger="click" @command="(cmd) => handleGroupAction(group.key, cmd)">
                  <Icon
                    icon="vi-carbon:overflow-menu-vertical"
                    :size="16"
                    class="group-menu-icon"
                    @click.stop
                  />
                  <template #dropdown>
                    <ElDropdownMenu>
                      <ElDropdownItem
                        v-for="action in group.actions"
                        :key="action.command"
                        :command="action.command"
                        :divided="action.divided"
                        :disabled="action.disabled"
                      >
                        <Icon v-if="action.icon" :icon="action.icon" :size="14" class="action-icon" />
                        {{ t(action.label) }}
                      </ElDropdownItem>
                    </ElDropdownMenu>
                  </template>
                </ElDropdown>
              </div>
            </div>
          </template>

          <!-- 递归渲染分组内容 -->
          <ElForm label-position="right" size="small" class="settings-form">
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
      transition: none !important; /* Disable animation */
    }

    :deep(.el-collapse-item__content) {
      padding: 0 12px 12px 12px;
      color: #cdd6f4;
    }

    :deep(.el-collapse-item__arrow) {
      color: #6c7086;
      transition: none !important;
    }
  }

  // Element Plus Form 暗色适配
  :deep(.el-form-item) {
    display: flex;
    margin-bottom: 8px;
    align-items: center; /* 垂直居中 */
  }

  :deep(.el-form-item__label) {
    color: #a6adc8 !important;
    font-size: 12px;
    padding-right: 12px;
    line-height: 28px;

    /* 标签对齐与尺寸 */
    flex: 0 0 35%; /* 固定 35% 宽度用于对齐 */
    max-width: 150px;
    display: inline-block; /* 确保 text-overflow 生效 */
    text-align: right; /* 文本右对齐 */
    display: flex;
    align-items: center;

    /* 省略号溢出处理 */
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;

    /* 允许文本选择 */
    user-select: text;
    cursor: text;
  }

  :deep(.el-form-item__content) {
    flex: 1;
    min-width: 0; /* 允许收缩 */
  }

  :deep(.el-input__wrapper) {
    background-color: #313244;
    box-shadow: none;
    border: 1px solid #45475a;
    // max-width: 140px; /* 移除固定宽度限制以填充空间 */
    width: 100%;
    .el-input__inner {
      color: #cdd6f4;
      text-align: right; /* 像属性面板一样文本右对齐 */
    }
  }

  :deep(.el-input-number) {
    width: 100%;
    .el-input__wrapper {
      max-width: 100%; /* InputNumber wrapper 处理宽度方式不同 */
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
      // max-width: 140px; /* 限制选择框宽度 */
    }
  }
}

.group-header {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  height: 15px;
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

// 菜单项图标
:deep(.el-dropdown-menu__item) {
  .action-icon {
    margin-right: 8px;
    vertical-align: middle;
  }
}
</style>
