<template>
  <div class="override-section">
    <el-collapse>
      <el-collapse-item title="⚙ 高级：覆盖客观分 / pass">
        <div v-if="!canOverrideObjective && !canOverridePass" class="no-override">
          <el-alert
            type="info"
            title="当前考试 scoring_policy 不允许任何覆盖操作"
            :closable="false"
          />
        </div>
        <el-form v-else :model="form" label-position="top" class="override-form">
          <el-form-item v-if="canOverrideObjective" label="覆盖客观分">
            <el-input-number
              v-model="form.objective_score"
              :min="0"
              :max="100"
              :precision="1"
              placeholder="留空则不覆盖"
            />
          </el-form-item>
          <el-form-item v-if="canOverridePass" label="覆盖 pass 标记">
            <el-select v-model="form.pass_flag" placeholder="留空则不覆盖" clearable>
              <el-option :value="true" label="通过" />
              <el-option :value="false" label="未通过" />
            </el-select>
          </el-form-item>
          <el-form-item label="覆盖原因" required>
            <el-input
              v-model="form.override_reason"
              type="textarea"
              :rows="2"
              maxlength="500"
              placeholder="必填，写入审计日志"
            />
          </el-form-item>
          <div class="form-footer">
            <el-button
              type="warning"
              :loading="submitting"
              :disabled="!form.override_reason.trim()"
              @click="handleSubmit"
            >
              确认覆盖
            </el-button>
          </div>
        </el-form>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import type { TeacherAttemptFull } from '@/api/exam/attempts'
import { overrideScoresApi } from '@/api/exam/attempts'

const props = defineProps<{
  attempt: TeacherAttemptFull | null
}>()

const emit = defineEmits<{
  (e: 'overridden', updated: TeacherAttemptFull): void
}>()

const submitting = ref(false)

const form = reactive({
  objective_score: undefined as number | undefined,
  pass_flag: undefined as boolean | undefined,
  override_reason: ''
})

const scoringPolicy = computed(
  () => (props.attempt?.attempt_scoring_policy_json ?? {}) as Record<string, unknown>
)
const canOverrideObjective = computed(() => !!scoringPolicy.value.allow_override_objective)
const canOverridePass = computed(() => !!scoringPolicy.value.allow_override_pass_flag)

async function handleSubmit() {
  if (!props.attempt) return
  if (!form.override_reason.trim()) {
    ElMessage.warning('请填写覆盖原因')
    return
  }
  submitting.value = true
  try {
    const res = await overrideScoresApi(props.attempt.attempt_id, {
      objective_score: form.objective_score,
      pass_flag: form.pass_flag,
      override_reason: form.override_reason
    })
    ElMessage.success('覆盖操作已记录')
    emit('overridden', res.data!)
    form.override_reason = ''
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: { message?: string } } } }
    ElMessage.error(err?.response?.data?.detail?.message ?? '覆盖操作失败')
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.override-section {
  margin-top: 16px;
}
.override-form {
  margin-top: 12px;
}
.no-override {
  padding: 8px 0;
}
.form-footer {
  text-align: right;
}
</style>
