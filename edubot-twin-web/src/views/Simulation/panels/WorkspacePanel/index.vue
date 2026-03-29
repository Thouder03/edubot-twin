<script setup lang="ts">
/**
 * WorkspacePanel/index.vue — 工作区面板（左右分栏）
 *
 * 左侧: FileTree（文件树）
 * 右侧: MonacoEditor（代码编辑器）
 *
 * 可作为仿真页面 Golden Layout 面板，也可内嵌到独立页面。
 */
import { onMounted, ref, onUnmounted, watch } from 'vue'
import { ElMessage, ElButton, ElTooltip } from 'element-plus'
import FileTree from './FileTree.vue'
import MonacoEditor from '@/components/Monaco/MonacoEditor.vue'
import { useWorkspace } from './composables/useWorkspace'
import { useWorkspaceSettings, type WorkspaceSettings } from '@/composables/useWorkspaceSettings'
import { useDesign } from '@/hooks/web/useDesign'
import { Icon } from '@/components/Icon'
import { usePanelState } from '@/views/Simulation/stores/panelState'
import { buildSettingsTree, createActionHandler } from './settings'

const { getPrefixCls } = useDesign()
const prefixCls = getPrefixCls('workspace-panel')

// ─── Props（面板集成时可传入 panelId 显示状态）
interface Props {
  panelId?: string
}
const props = defineProps<Props>()

// ─── Composables
const {
  treeData,
  currentFile,
  loading,
  saving,
  currentFileExtension,
  loadTree,
  loadChildren,
  openFile,
  saveCurrentFile,
  onContentChange,
  handleUpload,
  handleDelete,
  handleMkdir
} = useWorkspace()

const { settings, resetSettings } = useWorkspaceSettings()
const { registerPanel, unregisterPanel, updateSettingsTree } = usePanelState()

// ─── Settings Tree
function saveSettings(newConfig: Partial<WorkspaceSettings>) {
  settings.value = { ...settings.value, ...newConfig }
}

function refreshSettingsTree() {
  if (!props.panelId) return
  updateSettingsTree(props.panelId, {
    actionHandler: createActionHandler(saveSettings, resetSettings),
    nodes: buildSettingsTree(settings.value)
  })
}

watch(
  () => settings.value,
  () => {
    if (props.panelId) refreshSettingsTree()
  },
  { deep: true }
)

// ─── 可拖拽分隔线
const splitRatio = ref(25) // 左侧宽度百分比
const isResizing = ref(false)
const panelRef = ref<HTMLDivElement>()

function startResize(e: MouseEvent) {
  isResizing.value = true
  e.preventDefault()
}

function onMouseMove(e: MouseEvent) {
  if (!isResizing.value || !panelRef.value) return
  const rect = panelRef.value.getBoundingClientRect()
  const ratio = ((e.clientX - rect.left) / rect.width) * 100
  splitRatio.value = Math.min(Math.max(ratio, 15), 50)
}

function stopResize() {
  isResizing.value = false
}

// ─── 文件操作
async function onSave(content: string) {
  await saveCurrentFile(content)
}

async function onUpload(file: File, targetPath: string) {
  await handleUpload(file, targetPath)
}

// ─── 顶部上传按钮
const uploaderRef = ref<HTMLInputElement>()

function triggerUpload() {
  uploaderRef.value?.click()
}

async function onFileInputChange(e: Event) {
  const input = e.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  for (const file of files) {
    await handleUpload(file, '.')
  }
  input.value = ''
}

// ─── 格式化
const monacoRef = ref<{ format: () => void; getValue: () => string } | null>(null)

function formatCode() {
  monacoRef.value?.format()
}

// ─── 生命周期
onMounted(() => {
  if (props.panelId) {
    registerPanel(props.panelId, 'WorkspacePanel')
    refreshSettingsTree()
  }
  loadTree()
  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', stopResize)
})

onUnmounted(() => {
  if (props.panelId) {
    unregisterPanel(props.panelId)
  }
  document.removeEventListener('mousemove', onMouseMove)
  document.removeEventListener('mouseup', stopResize)
})
</script>

<template>
  <div ref="panelRef" :class="[prefixCls, isResizing && `${prefixCls}--resizing`]">
    <!-- 隐藏上传 input -->
    <input
      ref="uploaderRef"
      type="file"
      multiple
      style="display: none"
      @change="onFileInputChange"
    />

    <!-- 顶部工具栏 -->
    <div :class="`${prefixCls}__header`">
      <div :class="`${prefixCls}__header-left`">
        <Icon icon="vi-carbon:folder" />
        <span>{{ currentFile ? currentFile.name : '文件管理' }}</span>
        <span v-if="currentFile?.isDirty" :class="`${prefixCls}__dirty`" title="有未保存修改"
          >●</span
        >
      </div>

      <div :class="`${prefixCls}__header-right`">
        <!-- 上传 -->
        <el-tooltip content="上传文件" placement="top">
          <el-button text size="small" @click="triggerUpload">
            <Icon icon="vi-ep:upload" />
          </el-button>
        </el-tooltip>

        <!-- 格式化 -->
        <el-tooltip content="格式化代码" placement="top">
          <el-button text size="small" :disabled="!currentFile" @click="formatCode">
            <Icon icon="vi-carbon:code" />
          </el-button>
        </el-tooltip>

        <!-- 保存 -->
        <el-button
          type="primary"
          size="small"
          :loading="saving"
          :disabled="!currentFile || !currentFile.isDirty"
          @click="saveCurrentFile()"
        >
          <Icon icon="vi-ep:check" />
          保存
        </el-button>
      </div>
    </div>

    <!-- 主体：左树 + 分隔线 + 右编辑器 -->
    <div :class="`${prefixCls}__body`">
      <!-- 左侧文件树 -->
      <div :class="`${prefixCls}__left`" :style="{ width: `${splitRatio}%` }">
        <FileTree
          :tree-data="treeData"
          :loading="loading"
          :load-children="loadChildren"
          @select-file="openFile"
          @delete="handleDelete"
          @mkdir="handleMkdir"
          @upload="onUpload"
        />
      </div>

      <!-- 分隔拖拽线 -->
      <div :class="`${prefixCls}__divider`" @mousedown="startResize"></div>

      <!-- 右侧 Monaco 编辑器 -->
      <div :class="`${prefixCls}__right`" :style="{ width: `${100 - splitRatio}%` }">
        <MonacoEditor
          ref="monacoRef"
          :model-value="currentFile?.content ?? ''"
          :language="currentFileExtension"
          :settings="settings"
          :placeholder="'← 从左侧文件树中选择文件开始编辑'"
          @update:model-value="onContentChange"
          @save="onSave"
        />
      </div>
    </div>
  </div>
</template>

<style lang="less" scoped>
@prefix: v-workspace-panel;

.@{prefix} {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color);
  overflow: hidden;
  user-select: none;

  &--resizing {
    cursor: col-resize;
  }

  &__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 6px 12px;
    border-bottom: 1px solid var(--el-border-color);
    background: var(--el-bg-color-page);
    flex-shrink: 0;
    height: 40px;

    &-left {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 13px;
      font-weight: 500;
      color: var(--el-text-color-primary);
      overflow: hidden;

      .el-icon {
        flex-shrink: 0;
        color: var(--el-color-warning);
      }

      span {
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
    }

    &-right {
      display: flex;
      align-items: center;
      gap: 4px;
      flex-shrink: 0;
    }
  }

  &__dirty {
    color: var(--el-color-warning) !important;
    font-size: 16px;
    line-height: 1;
  }

  &__body {
    flex: 1;
    display: flex;
    overflow: hidden;
  }

  &__left {
    height: 100%;
    overflow: hidden;
    flex-shrink: 0;
    min-width: 140px;
  }

  &__divider {
    width: 4px;
    height: 100%;
    background: var(--el-border-color-lighter);
    cursor: col-resize;
    flex-shrink: 0;
    transition: background 0.2s;

    &:hover,
    .@{prefix}--resizing & {
      background: var(--el-color-primary-light-5);
    }
  }

  &__right {
    flex: 1;
    height: 100%;
    overflow: hidden;
    min-width: 0;
  }
}
</style>
