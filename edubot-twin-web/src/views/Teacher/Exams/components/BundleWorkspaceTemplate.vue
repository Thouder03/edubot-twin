<script setup lang="ts" generic="T extends { id: number; name: string }">
/**
 * BundleWorkspaceTemplate.vue — 资源包三栏工作台模板（第11期）
 *
 * 通用模板，为所有教师端 Bundle 类资源（考试环境快照、考试文件快照、测评脚本包、
 * 实验环境包、实验文件包……）提供一致的「列表视图 ↔ 文件树+设置视图 + 右侧编辑器」
 * 三栏布局。
 *
 * 使用方式：
 *   父组件通过 props 传入 API 前缀工厂、列表数据、各类回调，并通过 slot 自定义：
 *     - #list-item       列表行自定义渲染
 *     - #tree-header     文件树上方操作按钮（如上传、刷新）
 *     - #settings-panel  左下「基本设置」表单内容
 *     - #header-extra    标题栏右侧附加按钮
 *     - #list-empty      空列表提示
 *     - #right-summary   列表视图下右侧摘要卡
 *
 * 架构设计：
 *   - 复用 useBundleWorkspace + useBundleEditorState 屏蔽不同资源的 files 子协议差异
 *   - 复用 FileTree.vue / EditorWorkbench.vue 与学生端编辑体验一致
 *   - 仅依赖 apiPrefix 字符串，不硬编码任何 bundle 类型
 */
import { computed, onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'
import { ContentWrap } from '@/components/ContentWrap'
import FileTree from '@/views/Simulation/panels/WorkspacePanel/FileTree.vue'
import EditorWorkbench from '@/views/Simulation/panels/WorkspacePanel/EditorWorkbench.vue'
import { useBundleWorkspace } from '@/views/Teacher/Experiments/composables/useBundleWorkspace'
import { useBundleEditorState } from '@/views/Teacher/Experiments/composables/useBundleEditorState'
import { useWorkspaceSettings } from '@/composables/useWorkspaceSettings'
import request from '@/axios'
import { ElButton, ElEmpty, ElMessageBox, ElScrollbar, ElSkeleton, ElTooltip } from 'element-plus'
import { onBeforeRouteLeave } from 'vue-router'

// ─── Props ───────────────────────────────────────────────────────────────────

interface Props {
  /** 页面标题 */
  title: string
  /** 资源列表 */
  items: T[]
  /** 列表加载状态 */
  listLoading?: boolean
  /** API 文件前缀工厂：根据选中项生成 `/api/v1/.../{id}/files` */
  buildApiPrefix: (item: T) => string
  /** 受保护的相对路径集合（不可删除，如 ['startup.sh']） */
  protectedPaths?: string[]
  /** 进入文件树视图后自动打开的相对路径（可选，如 'startup.sh'） */
  autoOpenPath?: string
  /** 保存文件后是否刷新列表统计（默认 true） */
  refreshListOnSave?: boolean
  /** 当前列表行是否高亮的判定 */
  isSelected?: (item: T, selected: T | null) => boolean
  /**
   * 只读模式（第14期）
   * - 隐藏标题栏的「保存」按钮
   * - 文件树上传区域默认不显示上传按钮
   */
  readonly?: boolean
  /**
   * 自动进入第一个条目的文件树视图（第14期）
   * 适用于列表只有单条目、无需选择的场景（如查看提交代码）
   */
  autoEnterFirst?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  listLoading: false,
  protectedPaths: () => [],
  autoOpenPath: undefined,
  refreshListOnSave: true,
  isSelected: (item, selected) => !!selected && item.id === selected.id,
  readonly: false,
  autoEnterFirst: false
})

// ─── Emits ───────────────────────────────────────────────────────────────────

const emit = defineEmits<{
  (e: 'refresh-list'): void
  (e: 'select', item: T): void
  (e: 'context-menu', event: MouseEvent, item: T): void
}>()

// ─── 视图状态 ────────────────────────────────────────────────────────────────

type ViewMode = 'list' | 'tree'
const viewMode = ref<ViewMode>('list')
const selectedItem = ref<T | null>(null) as Ref<T | null>

// ─── API 前缀（响应式） ──────────────────────────────────────────────────────

const fileApiPrefix = computed(() =>
  selectedItem.value ? props.buildApiPrefix(selectedItem.value) : ''
)

// ─── 文件树 & 编辑器状态 ─────────────────────────────────────────────────────

const workspace = useBundleWorkspace(fileApiPrefix, props.protectedPaths)
const { settings } = useWorkspaceSettings()

const editor = useBundleEditorState(
  async (path: string) => {
    const prefix = fileApiPrefix.value
    const res = await request.get({ url: `${prefix}/read`, params: { path } })
    // 兼容 experiment/exam files 子协议返回格式
    const data = (res as { data?: { content?: string; modified_at?: number } }).data || {}
    return {
      content: data.content ?? '',
      modifiedAt: data.modified_at !== undefined ? Number(data.modified_at) : undefined
    }
  },
  async (path: string, content: string, modifiedAt?: number) => {
    const prefix = fileApiPrefix.value
    const res = await request.post({
      url: `${prefix}/save`,
      data: { path, content, ...(modifiedAt !== undefined ? { modified_at: modifiedAt } : {}) }
    })
    const data = (res as { data?: { modified_at?: number } }).data || {}
    if (props.refreshListOnSave) emit('refresh-list')
    return { newModifiedAt: data.modified_at }
  }
)

// ─── 单击 / 双击列表项 ───────────────────────────────────────────────────────

const handleItemClick = (item: T) => {
  selectedItem.value = item
  emit('select', item)
}

const handleItemDblClick = async (item: T) => {
  if (editor.hasAnyUnsavedChanges()) {
    const ok = await confirmLeave()
    if (!ok) return
  }
  selectedItem.value = item
  emit('select', item)
  viewMode.value = 'tree'
  workspace.clearSelection()
  // 关闭旧标签页
  closeAllTabs()
  await workspace.loadTree()
  // 自动打开指定文件
  if (props.autoOpenPath) {
    const node = workspace.findNodeByPath(workspace.treeData.value, props.autoOpenPath)
    if (node) await editor.openFile(props.autoOpenPath, false)
  }
}

// ─── 返回列表 ────────────────────────────────────────────────────────────────

const handleBackToList = async () => {
  const ok = await confirmLeave()
  if (!ok) return
  viewMode.value = 'list'
  closeAllTabs()
}

function closeAllTabs() {
  const allPaths = [
    ...editor.pinnedTabs.value,
    ...(editor.previewPath.value ? [editor.previewPath.value] : [])
  ]
  allPaths.forEach((p) => editor.closeTab(p))
}

// ─── 点击文件树节点 ──────────────────────────────────────────────────────────

const handleSelectFile = async (path: string) => {
  const node = workspace.findNodeByPath(workspace.treeData.value, path)
  if (!node || node.type === 'directory') return
  await editor.openFile(path, true)
}

// ─── 离开确认 ────────────────────────────────────────────────────────────────

const confirmLeave = async (): Promise<boolean> => {
  const dirtyPaths = editor.getDirtyPaths()
  if (dirtyPaths.length === 0) return true

  const fileNames = dirtyPaths.map((p) => p.split('/').pop()).join('、')
  try {
    await ElMessageBox.confirm(
      `以下文件有未保存的修改：${fileNames}，继续操作将丢弃修改`,
      '未保存修改',
      {
        confirmButtonText: '保存当前文件并继续',
        cancelButtonText: '放弃修改并继续',
        distinguishCancelAndClose: true,
        type: 'warning'
      }
    )
    await editor.saveCurrentFile()
    return true
  } catch (action) {
    if (action === 'cancel') return true
    return false
  }
}

onBeforeRouteLeave(async (_to, _from, next) => {
  const ok = await confirmLeave()
  next(ok ? undefined : false)
})

// ─── 自动进入第一个条目的文件树（autoEnterFirst）────────────────────────────

onMounted(async () => {
  if (props.autoEnterFirst && props.items.length > 0) {
    await handleItemDblClick(props.items[0])
  }
})

// ─── 可拖拽分隔（文件树 / 基本设置） ────────────────────────────────────────

const treeHeightPercent = ref(60)
const isDragging = ref(false)
const leftPanelRef = ref<HTMLElement | null>(null)

const startDrag = (e: MouseEvent) => {
  isDragging.value = true
  const startY = e.clientY
  const startPercent = treeHeightPercent.value
  const onMove = (ev: MouseEvent) => {
    if (!leftPanelRef.value) return
    const delta = ((ev.clientY - startY) / leftPanelRef.value.clientHeight) * 100
    treeHeightPercent.value = Math.max(20, Math.min(80, startPercent + delta))
  }
  const onUp = () => {
    isDragging.value = false
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

// ─── 上传（顶部按钮，直接调用 workspace API） ──────────────────────────────

const uploadInputRef = ref<HTMLInputElement | null>(null)
const triggerUpload = () => uploadInputRef.value?.click()
const handleUploadChange = async (e: Event) => {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  await workspace.uploadExternalCommand(file, '.')
  emit('refresh-list')
  target.value = ''
}

// ─── 文件树上下文菜单 ───────────────────────────────────────────────────────
// FileTree.vue 内部已经接管右键菜单；此处不再额外处理

// ─── 选中项变化时同步重载文件树 ─────────────────────────────────────────────

watch(fileApiPrefix, async (newPrefix) => {
  if (newPrefix && viewMode.value === 'tree') {
    await workspace.loadTree()
  }
})

// ─── 对外暴露：供父组件调用 ─────────────────────────────────────────────────

defineExpose({
  refreshTree: () => workspace.loadTree(),
  backToList: handleBackToList,
  selectedItem,
  viewMode
})

// ─── 清理 ───────────────────────────────────────────────────────────────────

onBeforeUnmount(() => {
  closeAllTabs()
})
</script>

<template>
  <ContentWrap>
    <!-- 标题栏 -->
    <div class="mb-16px flex items-center justify-between">
      <div class="flex items-center gap-12px">
        <ElButton v-if="viewMode === 'tree'" link @click="handleBackToList">← 返回列表</ElButton>
        <div class="text-18px font-600">
          {{ title }}
          <span v-if="viewMode === 'tree' && selectedItem" class="text-14px color-#909399 ml-8px">
            / {{ selectedItem.name }}
          </span>
        </div>
      </div>
      <div class="flex items-center gap-8px">
        <ElButton
          v-if="!props.readonly && viewMode === 'tree' && editor.activePath.value"
          type="primary"
          size="small"
          :disabled="!editor.dirtyMap[editor.activePath.value]"
          @click="editor.saveCurrentFile()"
        >
          保存 (Ctrl+S)
        </ElButton>
        <slot name="header-extra" :view-mode="viewMode" :selected-item="selectedItem"></slot>
      </div>
    </div>

    <div class="bundle-template-layout">
      <!-- ─── 左侧面板 ─── -->
      <div ref="leftPanelRef" class="bundle-template-left">
        <!-- 状态 A：列表视图 -->
        <template v-if="viewMode === 'list'">
          <ElSkeleton v-if="listLoading" :rows="4" animated class="pa-12px" />
          <template v-else>
            <div v-if="items.length === 0" class="empty-hint">
              <slot name="list-empty">
                <ElEmpty description="暂无数据" />
              </slot>
            </div>
            <template v-else>
              <div class="list-hint text-12px color-#909399">
                💡 单击选中，<strong>双击</strong>进入文件树 | 右键可重命名/删除
              </div>
              <ElScrollbar class="list-scroll">
                <div
                  v-for="item in items"
                  :key="item.id"
                  :class="['list-item', isSelected(item, selectedItem) && 'list-item--selected']"
                  @click="handleItemClick(item)"
                  @dblclick="handleItemDblClick(item)"
                  @contextmenu="emit('context-menu', $event, item)"
                >
                  <slot name="list-item" :item="item">
                    <span class="list-item__icon">📦</span>
                    <div class="list-item__info">
                      <div class="list-item__name">{{ item.name }}</div>
                    </div>
                  </slot>
                </div>
              </ElScrollbar>
            </template>
          </template>
        </template>

        <!-- 状态 B：文件树 + 基本设置 -->
        <template v-if="viewMode === 'tree'">
          <!-- 文件树区域 -->
          <div class="file-tree-area" :style="{ height: treeHeightPercent + '%' }">
            <div class="tree-header">
              <div class="tree-header__name">文件树</div>
              <slot name="tree-header" :selected-item="selectedItem">
                <ElTooltip v-if="!props.readonly" content="上传文件">
                  <ElButton link type="primary" @click="triggerUpload">↑ 上传</ElButton>
                </ElTooltip>
              </slot>
              <input
                ref="uploadInputRef"
                type="file"
                style="display: none"
                @change="handleUploadChange"
              />
            </div>
            <div class="file-tree-wrap">
              <FileTree
                :tree-data="workspace.treeData.value"
                :loading="workspace.loading.value"
                :workspace="workspace"
                @select-file="handleSelectFile"
                @upload="
                  (file, targetPath) => {
                    workspace.uploadExternalCommand(file, targetPath)
                    emit('refresh-list')
                  }
                "
              />
            </div>
          </div>

          <!-- 拖拽分隔条 -->
          <div
            class="drag-divider"
            :class="{ 'drag-divider--active': isDragging }"
            @mousedown="startDrag"
          >
            <span class="drag-divider__hint">↕</span>
          </div>

          <!-- 基本设置区 -->
          <div class="settings-area">
            <div class="settings-header">基本设置</div>
            <div class="settings-body">
              <slot name="settings-panel" :selected-item="selectedItem"></slot>
            </div>
          </div>
        </template>
      </div>

      <!-- ─── 右侧面板：EditorWorkbench ─── -->
      <div class="bundle-template-right">
        <div v-if="viewMode === 'list'" class="right-placeholder">
          <slot name="right-summary" :selected-item="selectedItem">
            <div v-if="!selectedItem" class="color-#bbb text-14px">请先选择一个资源</div>
            <div v-else class="item-summary">
              <div class="item-summary__name">📦 {{ selectedItem.name }}</div>
              <div class="mt-16px color-#909399 text-13px"> 双击资源行可进入文件树编辑模式 </div>
            </div>
          </slot>
        </div>

        <EditorWorkbench
          v-else
          :preview-path="editor.previewPath.value"
          :active-path="editor.activePath.value"
          :pinned-tabs="editor.pinnedTabs.value"
          :file-cache="editor.fileCache"
          :dirty-map="editor.dirtyMap"
          :settings="settings"
          @content-change="editor.handleContentChange($event)"
          @save="editor.saveActiveFile($event)"
          @select-tab="editor.handleSelectTab($event, false)"
          @close-tab="editor.closeTab($event)"
        />
      </div>
    </div>

    <!-- 状态栏 -->
    <div class="bundle-template-statusbar">
      <template v-if="viewMode === 'list'">共 {{ items.length }} 条</template>
      <template v-else>
        {{ selectedItem?.name }}
        <span v-if="editor.getDirtyPaths().length > 0" class="statusbar-dirty">
          ● {{ editor.getDirtyPaths().length }} 个文件未保存
        </span>
      </template>
    </div>
  </ContentWrap>
</template>

<style lang="less" scoped>
.bundle-template-layout {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 12px;
  height: calc(100vh - 260px);
  min-height: 500px;
}

.bundle-template-left,
.bundle-template-right {
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color);
}

.list-scroll {
  flex: 1;
}

.list-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  cursor: pointer;
  border-bottom: 1px solid var(--el-border-color-lighter);
  transition: background 0.2s;
  user-select: none;

  &:hover {
    background: var(--el-fill-color-light);
  }

  &--selected {
    background: var(--el-color-primary-light-9);
    border-left: 3px solid var(--el-color-primary);
  }

  &__icon {
    font-size: 20px;
    flex-shrink: 0;
  }

  &__info {
    flex: 1;
    min-width: 0;
  }

  &__name {
    font-size: 14px;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.list-hint {
  padding: 8px 14px 4px;
}

.empty-hint {
  padding: 40px 20px;
  text-align: center;
}

.tree-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--el-border-color);
  background: var(--el-fill-color-lighter);
  flex-shrink: 0;

  &__name {
    flex: 1;
    font-size: 13px;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.file-tree-area {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex-shrink: 0;
}

.file-tree-wrap {
  flex: 1;
  overflow: hidden;
  position: relative;
}

.drag-divider {
  height: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: row-resize;
  background: var(--el-fill-color);
  border-top: 1px solid var(--el-border-color-light);
  border-bottom: 1px solid var(--el-border-color-light);
  flex-shrink: 0;
  transition: background 0.2s;

  &:hover,
  &--active {
    background: var(--el-color-primary-light-8);
  }

  &__hint {
    font-size: 12px;
    color: var(--el-text-color-secondary);
    line-height: 1;
  }
}

.settings-area {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.settings-header {
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--el-text-color-secondary);
  text-transform: uppercase;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-lighter);
}

.settings-body {
  padding: 12px;
}

.right-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

.item-summary {
  text-align: center;

  &__name {
    font-size: 18px;
    font-weight: 600;
    margin-bottom: 12px;
  }
}

.bundle-template-statusbar {
  margin-top: 8px;
  padding: 6px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.statusbar-dirty {
  color: var(--el-color-warning);
  margin-left: 8px;
}
</style>
