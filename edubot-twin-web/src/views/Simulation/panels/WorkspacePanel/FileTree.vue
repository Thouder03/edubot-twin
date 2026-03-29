<script setup lang="ts">
/**
 * FileTree.vue — 文件树入口包装组件 (Phase 1 瘦身版)
 *
 * 现已降阶为展示与事件转发层：
 * 内部将复杂拖拽、树形选区与右键交给子组件和 Composables 处理。
 */
import { ref } from 'vue'
import { ElIcon } from 'element-plus'
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
  mkdir: [path: string]
  upload: [file: File, targetPath: string]
}>()

// 取消本地的 useWorkspace()，统一使用 props.workspace

// 右键菜单组件引用
const contextMenuRef = ref<InstanceType<typeof WorkspaceContextMenu> | null>(null)

function onSelectFile(path: string, event: MouseEvent) {
  props.workspace.toggleSelection(path, event.metaKey || event.ctrlKey || event.shiftKey)
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
</script>

<template>
  <div :class="prefixCls">
    <!-- 工具栏 -->
    <div :class="`${prefixCls}__toolbar`">
      <span :class="`${prefixCls}__title`">WORKSPACE</span>
      <el-icon :class="`${prefixCls}__action`" @click.stop="emit('mkdir', '.')">
        <Icon icon="vi-ep:folder-add" />
      </el-icon>
    </div>

    <!-- 树主体容器 -->
    <FileTreeContainer
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

  &__action {
    color: var(--el-text-color-secondary);
    cursor: pointer;
    transition: color 0.2s;

    &:hover {
      color: var(--el-color-primary);
    }
  }
}
</style>
