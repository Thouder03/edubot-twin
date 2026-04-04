<script setup lang="ts">
/**
 * FileTree.vue — 文件树入口包装组件 (Phase 1 瘦身版)
 *
 * 现已降阶为展示与事件转发层：
 * 内部将复杂拖拽、树形选区与右键交给子组件和 Composables 处理。
 */
import { ref, computed } from 'vue'
import { ElIcon, ElTooltip } from 'element-plus'
import FileTreeContainer from './FileTreeContainer.vue'
import WorkspaceContextMenu from './WorkspaceContextMenu.vue'
import { Icon } from '@/components/Icon'
import { useDesign } from '@/hooks/web/useDesign'

const { getPrefixCls } = useDesign()
const prefixCls = getPrefixCls('file-tree')

// 从顶层 useWorkspace 注入，也可以由 props 接收
// 为保证向下兼容 index.vue 和其他页面的老写法，我们在这先保留 Props 发射形式，或者直接接管
const props = defineProps<{
  treeData: any[]
  loading?: boolean
  workspace: any
}>()

const emit = defineEmits<{
  'select-file': [path: string]
  delete: [path: string, name: string]
  upload: [file: File, targetPath: string]
}>()

// 取消本地的 useWorkspace()，统一使用 props.workspace

// 右键菜单组件引用
const contextMenuRef = ref<InstanceType<typeof WorkspaceContextMenu> | null>(null)

// FileTreeContainer 组件引用，用于获取扁平可见节点列表（Shift 范围选）
const containerRef = ref<InstanceType<typeof FileTreeContainer> | null>(null)

// 多选模式快捷访问
const isMultiSelectMode = computed(() => props.workspace.multiSelectMode?.value ?? false)

function onSelectFile(path: string, event: MouseEvent) {
  const isMulti = event.metaKey || event.ctrlKey
  const isShift = event.shiftKey
  const flatPaths = isShift ? (containerRef.value?.getFlatVisiblePaths() ?? []) : []
  props.workspace.toggleSelection(path, isMulti, isShift, flatPaths)
  const node = props.workspace.findNodeByPath(props.treeData, path)
  // 目录展开由 FileTreeContainer 内部通过 he-tree addMulti API 处理
  if (!node || node.type === 'file') {
    emit('select-file', path)
  }
}

function onOpenFilePinned(path: string) {
  const node = props.workspace.findNodeByPath(props.treeData, path)
  if (node && node.type === 'file') {
    props.workspace.openFile(path, false)
  }
}

function onNodeContextMenu(node: any, event: MouseEvent) {
  event.preventDefault()
  props.workspace.determineContextMenuSelection(node.path)
  contextMenuRef.value?.show(event, node)
}

function onDropExternal(files: FileList, targetPath: string) {
  Array.from(files).forEach((file) => {
    emit('upload', file, targetPath)
  })
}

function onMoveInternal(sourcePaths: string[], targetDir: string) {
  props.workspace.moveCommand(sourcePaths, targetDir)
}

async function onManualRefresh() {
  await props.workspace.refreshExpandedDirectories()
}
</script>

<template>
  <div :class="prefixCls">
    <!-- 工具栏 -->
    <div :class="`${prefixCls}__toolbar`">
      <span :class="`${prefixCls}__title`">WORKSPACE</span>
      <div :class="`${prefixCls}__toolbar-actions`">
        <!-- 多选模式切换 -->
        <el-tooltip
          :content="isMultiSelectMode ? '关闭多选模式' : '开启多选模式（可用快捷键）'"
          placement="top"
        >
          <el-icon
            :class="[`${prefixCls}__action`, isMultiSelectMode && `${prefixCls}__action--active`]"
            @click.stop="props.workspace.toggleMultiSelectMode?.()"
          >
            <Icon icon="vi-carbon:list-checked" />
          </el-icon>
        </el-tooltip>

        <!-- 刷新 -->
        <el-tooltip content="刷新文件树" placement="top">
          <el-icon :class="`${prefixCls}__action`" @click.stop="onManualRefresh">
            <Icon icon="vi-ep:refresh" />
          </el-icon>
        </el-tooltip>
      </div>
    </div>

    <!-- 树主体容器 -->
    <FileTreeContainer
      ref="containerRef"
      :tree-data="treeData"
      :loading="loading"
      :selected-paths="props.workspace.selectedPaths.value"
      @select-file="onSelectFile"
      @open-file-pinned="onOpenFilePinned"
      @node-contextmenu="onNodeContextMenu"
      @drop-external="onDropExternal"
      @move-internal="onMoveInternal"
      @rename-submit="props.workspace.renameCommand"
      @rename-cancel="props.workspace.cancelRenameCommand"
    />

    <!-- 右键菜单 -->
    <WorkspaceContextMenu ref="contextMenuRef" :commands="props.workspace" />
  </div>
</template>

<style lang="less" scoped>
@prefix: v-file-tree;

.@{prefix} {
  display: flex;
  width: 100%;
  height: 100%;
  background: var(--el-bg-color-page);
  border-right: 1px solid var(--el-border-color);
  flex-direction: column;

  &__toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 12px;
    border-bottom: 1px solid var(--el-border-color-lighter);
  }

  &__title {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.08em;
    color: var(--el-text-color-secondary);
  }

  &__toolbar-actions {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  &__action {
    color: var(--el-text-color-secondary);
    cursor: pointer;
    transition: color 0.2s;

    &:hover {
      color: var(--el-color-primary);
    }

    &--active {
      color: var(--el-color-primary) !important;
      background-color: var(--el-color-primary-light-9);
      border-radius: 3px;
    }
  }
}
</style>
