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

// ---------- 节点动作处理 ----------
function handleNodeAction(path: string[], command: string) {
  if (!selectedSettingsTree.value) return

  const action: SettingsTreeAction = {
    action: 'perform-node-action',
    payload: {
      id: command,
      path
    }
  }
  selectedSettingsTree.value.actionHandler(action)
}

// ---------- 分组菜单处理 ----------
function handleGroupAction(groupKey: string, action: string) {
  if (!selectedSettingsTree.value) return

  const actionObj: SettingsTreeAction = {
    action: 'perform-node-action',
    payload: {
      id: action,
      path: [groupKey]
    }
  }
  selectedSettingsTree.value.actionHandler(actionObj)
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
              <Icon
                icon="vi-carbon:caret-right"
                class="expand-icon"
                :class="{ 'is-rotated': expandedGroups.includes(group.key) }"
              />
              <Icon v-if="group.icon" :icon="group.icon" :size="16" class="group-icon" />
              <span class="group-label">{{ group.label }}</span>
              <div v-if="group.actions?.length" class="group-actions">
                <ElDropdown trigger="click" @command="(cmd) => handleGroupAction(group.key, cmd)">
                  <Icon
                    icon="vi-carbon:overflow-menu-vertical"
                    :size="18"
                    class="group-menu-icon"
                    @click.stop
                  />
                  <template #dropdown>
                    <ElDropdownMenu>
                      <ElDropdownItem
                        v-for="action in group.actions"
                        :key="action.id"
                        :command="action.id"
                        :divided="action.divided"
                        :disabled="action.disabled"
                      >
                        <Icon
                          v-if="action.icon"
                          :icon="action.icon"
                          :size="14"
                          class="action-icon"
                        />
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
              @node-action="handleNodeAction"
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
  padding: 0;
  overflow-y: auto;
  background: #1e1e2e;

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
    background: transparent;
    border: none;

    :deep(.el-collapse-item) {
      border-bottom: 1px solid #313244;
    }

    :deep(.el-collapse-item__header) {
      display: flex;
      height: 35px;
      padding: 4px 8px 4px 22px;
      font-size: 12px;
      line-height: 1;
      color: #cdd6f4;
      background: transparent;
      border: none;
      justify-content: flex-start;
      align-items: center;

      &:hover {
        background: rgb(49 50 68 / 60%); /* 更柔和的 hover */
      }
    }

    :deep(.el-collapse-item__wrap) {
      background: transparent;
      border: none;
      transition: none !important;
    }

    :deep(.el-collapse-item__content) {
      padding: 4px 8px 8px; /* Lichtblick: 上间距 4px，左右 8px */
      color: #cdd6f4;
    }

    :deep(.el-collapse-item__arrow) {
      display: none;
    }
  }

  // Element Plus Form - Grid 布局（Lichtblick 样式）
  :deep(.el-form-item) {
    display: grid;
    grid-template-columns: minmax(20px, 128px) minmax(120px, 1fr); /* label 最小 50px 最大 40%，控件最小 120px 占剩余空间 */
    column-gap: 8px; /* Lichtblick: theme.spacing(1) */
    margin-bottom: 5px; /* Lichtblick: 紧凑间距 */
    align-items: center; /* 垂直居中对齐 */
  }

  :deep(.el-form-item__label) {
    min-width: 0; /* 允许压缩到 grid 的 minmax 最小值 */
    padding-right: 0; /* Grid 已处理间距 */
    overflow: hidden;
    font-size: 12px;
    line-height: 1.5;
    color: #a6adc8 !important;
    text-align: right;
    text-overflow: ellipsis;

    /* 省略号溢出处理 */
    white-space: nowrap;
    cursor: text;

    /* 允许文本选择 */
    user-select: text;
  }

  :deep(.el-form-item__content) {
    min-width: 120px; /* 控件列最小宽度，防止被压缩 */
    margin-right: 4px; /* Lichtblick: theme.spacing(0.5) */
  }

  :deep(.el-input__wrapper) {
    width: 100%;
    min-height: 28px; /* 恢复合适的最小高度 */
    background-color: #313244;
    border: 1px solid rgb(69 71 90 / 50%); /* 更柔和的边框 */
    box-shadow: none;
    transition: border-color 0.2s;
    padding-block: 4px; /* 调整内边距 */

    &:hover {
      border-color: #45475a;
    }

    &:focus-within {
      border-color: #89b4fa;
    }

    .el-input__inner {
      height: auto;
      line-height: 1.5;
      color: #cdd6f4;
      text-align: right;
    }
  }

  :deep(.el-input-number) {
    width: 100%;

    .el-input__wrapper {
      max-width: 100%;
      min-height: 28px; /* 恢复合适的最小高度 */
      padding-right: 0;
      padding-left: 0;
      padding-block: 4px; /* 调整内边距 */
    }

    .el-input__inner {
      height: auto;
      line-height: 1.5;
      text-align: center;
    }
  }

  :deep(.el-select) {
    width: 100%;

    .el-select__wrapper {
      min-height: 28px; /* 恢复合适的最小高度 */
      background-color: #313244;
      border: 1px solid rgb(69 71 90 / 50%);
      box-shadow: none;
      transition: border-color 0.2s;
      padding-block: 4px; /* 调整内边距 */

      &:hover {
        border-color: #45475a;
      }
    }
  }
}

.group-header {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  height: 100%;
  user-select: none;

  .expand-icon {
    font-size: 12px;
    color: #a6adc8;
    transition: transform 0.2s;
    flex-shrink: 0;

    &.is-rotated {
      transform: rotate(90deg);
    }
  }

  .group-icon {
    color: #89b4fa;
    flex-shrink: 0;
  }

  .group-label {
    overflow: hidden;
    font-weight: 600;
    text-align: left;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1;
  }

  .group-actions {
    display: flex;
    margin-left: auto;
    align-items: center;

    .group-menu-icon {
      padding: 2px;
      color: #6c7086;
      cursor: pointer;
      border-radius: 4px;
      transition: all 0.2s;

      &:hover {
        color: #cdd6f4;
        background: rgb(137 180 250 / 15%);
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
  display: flex;
  width: 100%;
  height: 100%;
  color: #585b70;
  flex-direction: column;
  align-items: center;
  justify-content: center;

  .empty-icon {
    margin-bottom: 12px;
  }

  p {
    font-size: 12px;
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
