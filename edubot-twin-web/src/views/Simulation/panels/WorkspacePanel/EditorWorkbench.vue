<script setup lang="ts">
import { computed } from 'vue'
import MonacoEditor from '@/components/Monaco/MonacoEditor.vue'
import { Icon } from '@/components/Icon'
import { ElMessageBox } from 'element-plus'

const props = defineProps<{
  previewPath: string | null
  activePath: string | null
  pinnedTabs: string[]
  fileCache: Record<string, any>
  dirtyMap: Record<string, boolean>
}>()

const emit = defineEmits<{
  'content-change': [content: string]
  save: [content: string]
  'select-tab': [path: string, asPreview?: boolean]
  'close-tab': [path: string]
}>()

function safeCloseTab(path: string) {
  if (props.dirtyMap[path]) {
    ElMessageBox.confirm('该文件有未保存的修改，直接关闭将丢失内容。确定关闭吗？', '提示', {
      type: 'warning',
      confirmButtonText: '确定关闭',
      cancelButtonText: '取消'
    })
      .then(() => {
        emit('close-tab', path)
      })
      .catch(() => {})
  } else {
    emit('close-tab', path)
  }
}

function getFilename(path: string) {
  const parts = path.split('/')
  return parts[parts.length - 1]
}

// 收集当前所有的 Tab 路径
const currentTabs = computed(() => {
  const tabs = [...props.pinnedTabs]
  if (props.previewPath && !tabs.includes(props.previewPath)) {
    tabs.push(props.previewPath)
  }
  return tabs
})
</script>

<template>
  <div class="editor-workbench">
    <div class="tabs-header">
      <div
        v-for="path in currentTabs"
        :key="path"
        class="tab"
        :class="{
          'is-active': activePath === path,
          'is-preview': previewPath === path
        }"
        @click="emit('select-tab', path, previewPath === path)"
        @dblclick="emit('select-tab', path, false)"
      >
        <!-- Tab 标题 -->
        <span class="tab-title" :title="path">{{ getFilename(path) }}</span>

        <!-- 脏标记 或 关闭按钮 -->
        <div class="tab-actions" @click.stop="safeCloseTab(path)">
          <span v-if="dirtyMap[path]" class="dirty-mark">●</span>
          <Icon v-else icon="vi-ep:close" class="close-icon" />
        </div>
      </div>
    </div>

    <div class="editor-container">
      <MonacoEditor
        v-if="activePath && activePath in fileCache"
        :model-value="fileCache[activePath]?.content || ''"
        :language="fileCache[activePath]?.extension || 'plaintext'"
        @update:model-value="emit('content-change', $event)"
        @save="emit('save', $event)"
      />
      <div v-else class="empty-workbench"> 请选择一个文件 </div>
    </div>
  </div>
</template>

<style lang="less" scoped>
.editor-workbench {
  display: flex;
  height: 100%;
  background-color: var(--el-bg-color);
  flex-direction: column;

  .tabs-header {
    display: flex;
    height: 35px;
    overflow-x: auto;
    background-color: var(--el-fill-color-light);

    .tab {
      display: inline-flex;
      height: 35px;
      max-width: 200px;
      min-width: 100px;
      padding: 0 10px 0 15px;
      font-size: 13px;
      color: var(--el-text-color-secondary);
      cursor: pointer;
      border-right: 1px solid var(--el-border-color);
      user-select: none;
      align-items: center;

      &:hover {
        background-color: var(--el-fill-color);

        .tab-actions {
          .dirty-mark {
            display: none;
          }

          .close-icon {
            display: block;
          }
        }
      }

      &.is-active {
        color: var(--el-text-color-primary);
        background-color: var(--el-bg-color);
        border-top: 1px solid var(--el-color-primary);
      }

      &.is-preview {
        font-style: italic;
      }

      .tab-title {
        margin-right: 6px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        flex: 1;
      }

      .tab-actions {
        display: flex;
        width: 16px;
        height: 16px;
        border-radius: 4px;
        align-items: center;
        justify-content: center;

        &:hover {
          background-color: var(--el-fill-color-darker);
        }

        .dirty-mark {
          font-size: 14px;
        }

        .close-icon {
          display: none; // 默认隐藏，在hover时显示或者未脏时一直隐藏直到hover
        }
      }

      // 如果没有脏数据，默认也只在 active 或者 hover 时显示 close
      &:not(:hover) {
        .close-icon {
          display: none !important;
        }
      }

      &.is-active {
        .close-icon {
          display: block; // active 状态下默认显示关闭按钮(如果没有脏)
        }
      }
    }
  }

  .editor-container {
    flex: 1;
    overflow: hidden;
  }

  .empty-workbench {
    display: flex;
    height: 100%;
    color: var(--el-text-color-secondary);
    align-items: center;
    justify-content: center;
  }
}
</style>
