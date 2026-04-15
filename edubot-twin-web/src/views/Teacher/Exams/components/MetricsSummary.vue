<template>
  <div v-if="metrics || hasSummary" class="metrics-summary">
    <div v-if="hasSummary" class="summary-text">{{ attempt?.summary }}</div>
    <el-descriptions v-if="metrics" :column="2" border size="small">
      <el-descriptions-item v-if="metrics.elapsed_seconds != null" label="总耗时">
        {{ metrics.elapsed_seconds.toFixed(1) }}s
      </el-descriptions-item>
      <el-descriptions-item v-if="metrics.goal_reached != null" label="目标到达">
        <el-tag :type="metrics.goal_reached ? 'success' : 'danger'" size="small">
          {{ metrics.goal_reached ? '✅ 是' : '❌ 否' }}
        </el-tag>
      </el-descriptions-item>
      <el-descriptions-item v-if="metrics.collision_count != null" label="碰撞次数">
        {{ metrics.collision_count }}
      </el-descriptions-item>
      <el-descriptions-item v-if="metrics.path_length != null" label="路径长度">
        {{ metrics.path_length.toFixed(2) }}m
      </el-descriptions-item>
      <el-descriptions-item v-if="metrics.stage_count != null" label="阶段">
        {{ metrics.stage_passed_count ?? 0 }} / {{ metrics.stage_count }}
      </el-descriptions-item>
    </el-descriptions>
  </div>
  <el-empty v-else description="暂无指标数据" :image-size="60" />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { TeacherAttemptFull } from '@/api/exam/attempts'

const props = defineProps<{
  attempt: TeacherAttemptFull | null
}>()

const metrics = computed(() => props.attempt?.result_json?.metrics ?? null)
const hasSummary = computed(() => !!props.attempt?.summary)
</script>

<style scoped>
.metrics-summary {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.summary-text {
  font-size: 14px;
  color: var(--el-text-color-regular);
  padding: 8px 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
}
</style>
