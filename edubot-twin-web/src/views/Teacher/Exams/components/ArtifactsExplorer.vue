<template>
  <div class="artifacts-explorer">
    <div v-if="!tree" class="loading-state">
      <el-skeleton :rows="3" animated />
    </div>
    <div v-else-if="!tree.artifacts_available" class="no-artifacts">
      <el-empty description="artifacts 目录不存在或已清理" :image-size="60" />
    </div>
    <div v-else-if="tree.files.length === 0" class="no-artifacts">
      <el-empty description="artifacts 目录为空" :image-size="60" />
    </div>
    <ul v-else class="file-list">
      <li
        v-for="file in tree.files"
        :key="file.name"
        class="file-item"
        :class="{ 'is-trajectory': file.name === 'trajectory.json' }"
      >
        <span class="file-icon">{{ fileIcon(file) }}</span>
        <span class="file-name">{{ file.name }}</span>
        <span class="file-size">{{ formatSize(file.size) }}</span>
        <div class="file-actions">
          <template v-if="file.name === 'trajectory.json'">
            <el-button size="small" @click="emit('view-trajectory', file.name)">
              查看轨迹
            </el-button>
          </template>
          <template v-else-if="file.too_large">
            <el-tag type="warning" size="small">文件过大</el-tag>
          </template>
          <template
            v-else-if="file.preview_type !== 'unsupported' && file.preview_type !== 'download'"
          >
            <el-button size="small" @click="emit('preview', file.name)">预览</el-button>
          </template>
          <template v-else-if="file.preview_type === 'download'">
            <el-tag size="small">仅下载（.pgm）</el-tag>
          </template>
          <template v-else>
            <el-tag type="info" size="small">不支持预览</el-tag>
          </template>
        </div>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import type { ArtifactsTreeResponse, ArtifactFileInfo } from '@/api/exam/attempts'

defineProps<{
  tree: ArtifactsTreeResponse | null
}>()

const emit = defineEmits<{
  (e: 'preview', filename: string): void
  (e: 'view-trajectory', filename: string): void
}>()

function fileIcon(file: ArtifactFileInfo): string {
  const ext = file.name.split('.').pop()?.toLowerCase()
  if (['png', 'jpg', 'jpeg', 'gif', 'webp'].includes(ext ?? '')) return '🖼️'
  if (['json', 'yaml', 'yml'].includes(ext ?? '')) return '📄'
  if (['log', 'txt', 'md', 'csv'].includes(ext ?? '')) return '📝'
  if (['sh', 'py'].includes(ext ?? '')) return '⚙️'
  return '📁'
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`
}
</script>

<style scoped>
.file-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.file-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 4px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  font-size: 13px;
}
.file-item:last-child {
  border-bottom: none;
}
.file-item.is-trajectory {
  background: var(--el-color-primary-light-9);
  border-radius: 4px;
}
.file-icon {
  font-size: 16px;
  flex-shrink: 0;
}
.file-name {
  flex: 1;
  font-family: monospace;
}
.file-size {
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
  min-width: 60px;
  text-align: right;
}
.file-actions {
  flex-shrink: 0;
}
.loading-state,
.no-artifacts {
  padding: 16px 0;
}
</style>
