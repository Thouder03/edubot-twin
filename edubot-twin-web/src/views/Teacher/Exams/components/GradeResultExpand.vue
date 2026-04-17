<script setup lang="ts">
/**
 * GradeResultExpand - 教师成绩预览行展开面板（第16期，第17期重构）
 *
 * 三区并排：
 *   左  ── 固定字段（result_json_display，已去掉 artifacts / metrics）
 *   中  ── 指标（metrics 独立字段，使用 MetricsKvTable）
 *   右  ── 自定义字段（custom_fields）
 */
import type { GradePreviewItem } from '@/api/exam/gradePreview'
import { getFieldLabel } from '@/constants/resultJsonLabels'
import MetricsKvTable from '@/components/Grade/MetricsKvTable.vue'

const props = defineProps<{
  row: GradePreviewItem
}>()

/** result_json_display 中的固定字段（已不含 metrics / custom_fields） */
function getFixedFields(): Array<{ label: string; value: unknown }> {
  const data = props.row.result_json_display
  if (!data) return []
  return Object.entries(data)
    .filter(([k]) => k !== 'custom_fields')
    .map(([k, v]) => ({ label: getFieldLabel(k), value: v }))
}

function getCustomFields(): Array<{ key: string; value: unknown }> {
  const cf = props.row.custom_fields
  if (!cf) return []
  return Object.entries(cf).map(([k, v]) => ({ key: k, value: v }))
}

function formatValue(v: unknown): string {
  if (v === null || v === undefined) return '-'
  if (typeof v === 'boolean') return v ? '✅ 是' : '❌ 否'
  if (typeof v === 'number') return String(v)
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}
</script>

<template>
  <div class="grade-expand px-4 py-3 bg-#f8f9fa rounded">
    <div
      v-if="!row.result_json_display && !row.metrics && !row.custom_fields"
      class="text-#909399 text-13px"
    >
      暂无评测数据
    </div>
    <div v-else class="flex gap-6">
      <!-- 固定字段 -->
      <div class="flex-1">
        <div class="section-title">📊 固定字段</div>
        <table class="kv-table" v-if="getFixedFields().length > 0">
          <tbody>
            <tr v-for="item in getFixedFields()" :key="item.label">
              <td class="kv-key">{{ item.label }}</td>
              <td class="kv-val">{{ formatValue(item.value) }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="text-#bbb text-12px">无固定字段</div>
      </div>

      <!-- 指标 -->
      <div class="flex-1">
        <div class="section-title">📈 指标</div>
        <MetricsKvTable :metrics="row.metrics" />
      </div>

      <!-- 自定义字段 -->
      <div class="flex-1">
        <div class="section-title">📋 自定义字段</div>
        <table class="kv-table" v-if="getCustomFields().length > 0">
          <tbody>
            <tr v-for="item in getCustomFields()" :key="item.key">
              <td class="kv-key">{{ item.key }}</td>
              <td class="kv-val">{{ formatValue(item.value) }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="text-#bbb text-12px">无自定义字段</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.section-title {
  font-size: 12px;
  font-weight: 600;
  color: #606266;
  margin-bottom: 6px;
}
.kv-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.kv-table tr:hover {
  background: #f0f2f5;
}
.kv-key {
  color: #606266;
  padding: 3px 12px 3px 0;
  white-space: nowrap;
  width: 40%;
}
.kv-val {
  color: #303133;
  padding: 3px 0;
  word-break: break-all;
}
</style>
