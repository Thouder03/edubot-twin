<script setup lang="ts">
import { Form, FormSchema } from '@/components/Form'
import { useForm } from '@/hooks/web/useForm'
import { PropType, reactive, watch, ref } from 'vue'
import { useValidator } from '@/hooks/web/useValidator'
import { createStudentApi, updateStudentApi } from '@/api/student'
import { ElButton } from 'element-plus'

const { required } = useValidator()

const props = defineProps({
  currentRow: {
    type: Object as PropType<any>,
    default: () => undefined
  },
  actionType: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['submit', 'close'])

const formSchema = reactive<FormSchema[]>([
  {
    field: 'username',
    label: '用户名',
    component: 'Input'
  },
  {
    field: 'password',
    label: '密码',
    component: 'InputPassword',
    componentProps: {
      placeholder: props.actionType === 'edit' ? '留空表示不修改' : '请输入密码'
    }
  },
  {
    field: 'real_name',
    label: '姓名',
    component: 'Input'
  },
  {
    field: 'email',
    label: '邮箱',
    component: 'Input'
  },
  {
    field: 'is_active',
    label: '状态',
    component: 'Switch',
    value: true,
    remove: props.actionType === 'add' // 只有编辑时显示状态开关
  }
])

const rules = reactive({
  username: [required()],
  real_name: [required()]
})

const { formRegister, formMethods } = useForm()
const { setValues, getFormData, getElFormExpose } = formMethods

const loading = ref(false)

const submit = async () => {
  const elForm = await getElFormExpose()
  const valid = await elForm?.validate().catch((err) => {
    console.log(err)
  })
  if (valid) {
    loading.value = true
    try {
      const formData = await getFormData()
      if (props.actionType === 'add') {
        if (!formData.password) {
          // 这里如果是增加必须有密码
          formData.password = '123456'
        }
        await createStudentApi(formData as any)
      } else {
        // 如果密码留空则不更新
        if (!formData.password) {
          delete formData.password
        }
        await updateStudentApi(props.currentRow?.id, formData as any)
      }
      emit('submit')
    } catch (e) {
      console.error(e)
    } finally {
      loading.value = false
    }
  }
}

watch(
  () => props.currentRow,
  (currentRow) => {
    if (!currentRow) return
    setValues(currentRow)
  },
  {
    deep: true,
    immediate: true
  }
)
</script>

<template>
  <Form :rules="rules" @register="formRegister" :schema="formSchema" />
  <div style="text-align: right; margin-top: 20px">
    <ElButton @click="$emit('close')"> 取消 </ElButton>
    <ElButton type="primary" :loading="loading" @click="submit"> 保存 </ElButton>
  </div>
</template>
