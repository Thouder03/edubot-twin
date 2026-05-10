<script setup lang="ts">
/**
 * MetricsKvTable - 评测指标键值表格（共用组件）
 *
 * 接收 metrics 对象，渲染为带中文标签的键值表格。
 * 供教师端成绩预览展开行和学生端成绩页共享使用。
 */
import { computed } from 'vue'
import { getFieldLabel } from '@/constants/resultJsonLabels'

const props = defineProps<{
  metrics: Record<string, unknown> | null | undefined
}>()

const entries = computed<Array<{ label: string; value: unknown }>>(() => {
  if (!props.metrics) return []
  return Object.entries(props.metrics).map(([k, v]) => ({
    label: getFieldLabel(k, true),
    value: v
  }))
})

function formatValue(v: unknown): string {
  if (v === null || v === undefined) return '-'
  if (typeof v === 'boolean') return v ? '✅ 是' : '❌ 否'
  if (typeof v === 'number') return String(v)
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}
</script>

<template>
  <table v-if="entries.length > 0" class="metrics-kv-table">
    <tbody>
      <tr v-for="item in entries" :key="item.label">
        <td class="kv-key">{{ item.label }}</td>
        <td class="kv-val">{{ formatValue(item.value) }}</td>
      </tr>
    </tbody>
  </table>
  <div v-else class="text-#bbb text-12px">无指标数据</div>
</template>

<style scoped>
.metrics-kv-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.metrics-kv-table tr:hover {
  background: #f0f2f5;
}
.kv-key {
  color: #606266;
  padding: 3px 12px 3px 0;
  white-space: nowrap;
  width: 45%;
}
.kv-val {
  color: #303133;
  padding: 3px 0;
  word-break: break-all;
}
</style>
