<template>
  <div class="score-overview">
    <el-card class="score-card" :class="{ 'is-loading': !attempt }">
      <div class="score-item">
        <div class="score-label">客观分</div>
        <div class="score-value objective">
          {{ attempt?.objective_score != null ? attempt.objective_score.toFixed(1) : '-' }}
        </div>
      </div>
    </el-card>
    <el-card class="score-card">
      <div class="score-item">
        <div class="score-label">人工分</div>
        <div class="score-value manual">
          {{ attempt?.manual_score != null ? attempt.manual_score.toFixed(1) : '-' }}
        </div>
      </div>
    </el-card>
    <el-card class="score-card">
      <div class="score-item">
        <div class="score-label">最终分</div>
        <div class="score-value final">
          {{ attempt?.final_score != null ? attempt.final_score.toFixed(1) : '-' }}
        </div>
      </div>
    </el-card>
    <el-card class="score-card">
      <div class="score-item">
        <div class="score-label">通过</div>
        <div class="score-value pass">
          <el-tag
            v-if="attempt?.pass != null"
            :type="attempt.pass ? 'success' : 'danger'"
            size="large"
          >
            {{ attempt.pass ? '✅ 通过' : '❌ 未通过' }}
          </el-tag>
          <span v-else>-</span>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import type { TeacherAttemptFull } from '@/api/exam/attempts'

defineProps<{
  attempt: TeacherAttemptFull | null
}>()
</script>

<style scoped>
.score-overview {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}
.score-card {
  text-align: center;
}
.score-item {
  padding: 8px 0;
}
.score-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}
.score-value {
  font-size: 28px;
  font-weight: 700;
}
.score-value.objective {
  color: var(--el-color-primary);
}
.score-value.manual {
  color: var(--el-color-warning);
}
.score-value.final {
  color: var(--el-color-success);
}
.score-value.pass {
  font-size: 20px;
}
</style>
