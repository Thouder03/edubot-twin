<script setup lang="ts">
/**
 * FileManager.vue — 独立文件管理页面
 *
 * 以全屏方式展示 WorkspacePanel，提供顶部操作栏和设置入口。
 * 设置通过 useWorkspaceSettings 与 WorkspacePanel（仿真页面内嵌版）共享。
 */
import { ref } from 'vue'
import {
  ElButton,
  ElTooltip,
  ElDrawer,
  ElSlider,
  ElRadioGroup,
  ElRadioButton,
  ElSwitch,
  ElDivider
} from 'element-plus'
import WorkspacePanel from '@/views/Simulation/panels/WorkspacePanel/index.vue'
import { useWorkspaceSettings } from '@/composables/useWorkspaceSettings'
import { useDesign } from '@/hooks/web/useDesign'
import { Icon } from '@/components/Icon'

const { getPrefixCls } = useDesign()
const prefixCls = getPrefixCls('file-manager-page')

const { settings, resetSettings } = useWorkspaceSettings()

// 设置抽屉
const showSettings = ref(false)
</script>

<template>
  <div :class="prefixCls">
    <!-- 顶部标题栏 -->
    <div :class="`${prefixCls}__topbar`">
      <div :class="`${prefixCls}__topbar-title`">
        <Icon icon="vi-carbon:folder-open" />
        <span>文件管理</span>
      </div>
      <div :class="`${prefixCls}__topbar-actions`">
        <el-tooltip content="编辑器设置" placement="bottom">
          <el-button type="info" text size="small" @click="showSettings = true">
            <Icon icon="vi-ep:setting" />
            设置
          </el-button>
        </el-tooltip>
      </div>
    </div>

    <!-- WorkspacePanel 主体 -->
    <div :class="`${prefixCls}__body`">
      <WorkspacePanel />
    </div>

    <!-- 设置抽屉（与 WorkspacePanel 面板共享同一配置 key） -->
    <el-drawer
      v-model="showSettings"
      title="编辑器设置"
      direction="rtl"
      size="320px"
      :append-to-body="true"
    >
      <div :class="`${prefixCls}__settings`">
        <!-- 字体大小 -->
        <div :class="`${prefixCls}__setting-item`">
          <label>字体大小</label>
          <el-slider
            v-model="settings.fontSize"
            :min="10"
            :max="20"
            :step="1"
            show-input
            size="small"
          />
        </div>

        <!-- 编辑器主题 -->
        <div :class="`${prefixCls}__setting-item`">
          <label>编辑器主题</label>
          <el-radio-group v-model="settings.theme" size="small">
            <el-radio-button value="vs-dark">深色</el-radio-button>
            <el-radio-button value="vs">浅色</el-radio-button>
            <el-radio-button value="hc-black">高对比</el-radio-button>
          </el-radio-group>
        </div>

        <!-- 自动换行 -->
        <div :class="`${prefixCls}__setting-item`">
          <label>自动换行</label>
          <el-switch v-model="settings.wordWrap" active-value="on" inactive-value="off" />
        </div>

        <!-- 显示小地图 -->
        <div :class="`${prefixCls}__setting-item`">
          <label>显示小地图</label>
          <el-switch v-model="settings.minimap" />
        </div>

        <!-- Tab 大小 -->
        <div :class="`${prefixCls}__setting-item`">
          <label>Tab 大小</label>
          <el-radio-group v-model="settings.tabSize" size="small">
            <el-radio-button :value="2">2 空格</el-radio-button>
            <el-radio-button :value="4">4 空格</el-radio-button>
          </el-radio-group>
        </div>

        <!-- 分隔线 -->
        <el-divider />

        <!-- 重置 -->
        <el-button size="small" @click="resetSettings"> 恢复默认设置 </el-button>
      </div>
    </el-drawer>
  </div>
</template>

<style lang="less" scoped>
@prefix: v-file-manager-page;

.@{prefix} {
  width: 100%;
  height: calc(100vh - var(--top-tool-height, 50px) - var(--tags-view-height, 34px));
  display: flex;
  flex-direction: column;
  overflow: hidden;

  &__topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 20px;
    background: var(--el-bg-color-page);
    border-bottom: 1px solid var(--el-border-color);
    flex-shrink: 0;

    &-title {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 15px;
      font-weight: 600;
      color: var(--el-text-color-primary);

      .el-icon {
        color: var(--el-color-primary);
        font-size: 18px;
      }
    }

    &-actions {
      display: flex;
      align-items: center;
      gap: 8px;
    }
  }

  &__body {
    flex: 1;
    overflow: hidden;
  }

  &__settings {
    display: flex;
    flex-direction: column;
    gap: 20px;
    padding: 4px 0;
  }

  &__setting-item {
    display: flex;
    flex-direction: column;
    gap: 8px;

    label {
      font-size: 13px;
      font-weight: 500;
      color: var(--el-text-color-regular);
    }
  }
}
</style>
