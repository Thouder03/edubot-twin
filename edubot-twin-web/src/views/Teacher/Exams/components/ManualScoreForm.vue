<template>
  <el-form :model="form" label-position="top" class="manual-score-form">
    <div class="breakdown-grid">
      <el-form-item label="操作规范性">
        <el-slider v-model="form.breakdown.operation_quality" :min="0" :max="100" show-input />
      </el-form-item>
      <el-form-item label="路径合理性">
        <el-slider v-model="form.breakdown.path_rationality" :min="0" :max="100" show-input />
      </el-form-item>
      <el-form-item label="恢复能力">
        <el-slider v-model="form.breakdown.recovery_ability" :min="0" :max="100" show-input />
      </el-form-item>
      <el-form-item label="运行稳定性">
        <el-slider v-model="form.breakdown.stability" :min="0" :max="100" show-input />
      </el-form-item>
    </div>

    <el-form-item label="综合人工分" required>
      <el-input-number
        v-model="form.manual_score"
        :min="0"
        :max="100"
        :precision="1"
        :step="1"
        class="score-input"
      />
    </el-form-item>

    <el-form-item label="教师评语">
      <el-input
        v-model="form.comment"
        type="textarea"
        :rows="3"
        maxlength="1000"
        show-word-limit
        placeholder="可选，评语将展示在复核记录中"
      />
    </el-form-item>

    <div class="form-footer">
      <el-button
        type="primary"
        :loading="submitting"
        :disabled="form.manual_score == null"
        @click="handleSubmit"
      >
        提交评分
      </el-button>
    </div>
  </el-form>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { TeacherAttemptFull } from '@/api/exam/attempts'
import { submitManualScoreApi } from '@/api/exam/attempts'

const props = defineProps<{
  attempt: TeacherAttemptFull | null
}>()

const emit = defineEmits<{
  (e: 'submitted', updated: TeacherAttemptFull): void
}>()

const submitting = ref(false)

interface FormBreakdown {
  operation_quality: number
  path_rationality: number
  recovery_ability: number
  stability: number
  extra_comment: string | null
}

interface ManualScoreForm {
  manual_score: number
  breakdown: FormBreakdown
  comment: string | null
}

const form = reactive<ManualScoreForm>({
  manual_score: 0,
  breakdown: {
    operation_quality: 80,
    path_rationality: 80,
    recovery_ability: 80,
    stability: 80,
    extra_comment: null
  },
  comment: null
})

// 加载已有人工分（复评场景）
watch(
  () => props.attempt,
  (a) => {
    if (!a) return
    if (a.manual_score != null) form.manual_score = a.manual_score
    if (a.breakdown_json) {
      const bd = a.breakdown_json as Record<string, unknown>
      form.breakdown.operation_quality = (bd.operation_quality as number) ?? 80
      form.breakdown.path_rationality = (bd.path_rationality as number) ?? 80
      form.breakdown.recovery_ability = (bd.recovery_ability as number) ?? 80
      form.breakdown.stability = (bd.stability as number) ?? 80
    }
    if (a.teacher_comment) form.comment = a.teacher_comment
  },
  { immediate: true }
)

async function handleSubmit() {
  if (!props.attempt) return
  submitting.value = true
  try {
    const res = await submitManualScoreApi(props.attempt.attempt_id, {
      manual_score: form.manual_score,
      breakdown: {
        operation_quality: form.breakdown.operation_quality,
        path_rationality: form.breakdown.path_rationality,
        recovery_ability: form.breakdown.recovery_ability,
        stability: form.breakdown.stability,
        extra_comment: form.breakdown.extra_comment
      },
      comment: form.comment || undefined
    })
    ElMessage.success('评分提交成功')
    emit('submitted', res.data!)
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: { message?: string } } } }
    ElMessage.error(err?.response?.data?.detail?.message ?? '提交失败')
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.manual-score-form {
  width: 100%;
}
.breakdown-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 24px;
}
.score-input {
  width: 160px;
}
.form-footer {
  margin-top: 8px;
  text-align: right;
}
</style>
