<script setup lang="ts">
/**
 * CodeEditor.vue — 独立代码编辑器页面
 *
 * 支持通过 query 参数 ?path=xxx 直接打开指定文件。
 * 设置与 FileManager / WorkspacePanel 共享同一 localStorage key。
 */
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  ElIcon,
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

const { getPrefixCls } = useDesign()
const prefixCls = getPrefixCls('code-editor-page')

const route = useRoute()
const { settings, resetSettings } = useWorkspaceSettings()

// 设置抽屉
const showSettings = ref(false)

// 如有 path query，通知 WorkspacePanel 打开
const initialPath = route.query.path as string | undefined
</script>

<template>
  <div :class="prefixCls">
    <!-- 顶部标题栏 -->
    <div :class="`${prefixCls}__topbar`">
      <div :class="`${prefixCls}__topbar-title`">
        <el-icon><i class="vi-carbon:code"></i></el-icon>
        <span>代码编辑器</span>
        <span v-if="initialPath" :class="`${prefixCls}__topbar-path`">
          {{ initialPath }}
        </span>
      </div>
      <div :class="`${prefixCls}__topbar-actions`">
        <el-tooltip content="编辑器设置" placement="bottom">
          <el-button type="info" text size="small" @click="showSettings = true">
            <el-icon><i class="vi-ep:setting"></i></el-icon>
            设置
          </el-button>
        </el-tooltip>
      </div>
    </div>

    <!-- WorkspacePanel 主体 -->
    <div :class="`${prefixCls}__body`">
      <WorkspacePanel />
    </div>

    <!-- 设置抽屉（与 FileManager 共享同一配置 key） -->
    <el-drawer
      v-model="showSettings"
      title="编辑器设置"
      direction="rtl"
      size="320px"
      :append-to-body="true"
    >
      <div :class="`${prefixCls}__settings`">
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

        <div :class="`${prefixCls}__setting-item`">
          <label>编辑器主题</label>
          <el-radio-group v-model="settings.theme" size="small">
            <el-radio-button value="vs-dark">深色</el-radio-button>
            <el-radio-button value="vs">浅色</el-radio-button>
            <el-radio-button value="hc-black">高对比</el-radio-button>
          </el-radio-group>
        </div>

        <div :class="`${prefixCls}__setting-item`">
          <label>自动换行</label>
          <el-switch v-model="settings.wordWrap" active-value="on" inactive-value="off" />
        </div>

        <div :class="`${prefixCls}__setting-item`">
          <label>显示小地图</label>
          <el-switch v-model="settings.minimap" />
        </div>

        <div :class="`${prefixCls}__setting-item`">
          <label>Tab 大小</label>
          <el-radio-group v-model="settings.tabSize" size="small">
            <el-radio-button :value="2">2 空格</el-radio-button>
            <el-radio-button :value="4">4 空格</el-radio-button>
          </el-radio-group>
        </div>

        <el-divider />
        <el-button size="small" @click="resetSettings">恢复默认设置</el-button>
      </div>
    </el-drawer>
  </div>
</template>

<style lang="less" scoped>
@prefix: v-code-editor-page;

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

    &-path {
      font-size: 12px;
      color: var(--el-text-color-secondary);
      font-weight: 400;
      background: var(--el-fill-color);
      padding: 2px 8px;
      border-radius: 4px;
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
