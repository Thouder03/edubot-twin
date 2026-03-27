<script setup lang="ts">
import { Form } from '@/components/Form'
import { reactive, ref } from 'vue'
import { createStudentApi, updateStudentApi } from '@/api/student'
import { ElMessage } from 'element-plus'
import type { FormSchema } from '@/components/Form'

const props = defineProps({
  currentRow: {
    type: Object,
    default: () => null
  },
  actionType: {
    type: String,
    default: 'add'
  }
})

const emit = defineEmits(['submit'])

const schema = reactive<FormSchema[]>([
  {
    field: 'username',
    label: '用户名',
    component: 'Input',
    componentProps: {
      placeholder: '请输入用户名'
    },
    formItemProps: {
      rules: [{ required: true, message: '请输入用户名' }]
    }
  },
  {
    field: 'password',
    label: '密码',
    component: 'Input',
    componentProps: {
      type: 'password',
      placeholder: props.actionType === 'edit' ? '留空则不修改' : '请输入密码'
    },
    formItemProps: {
      rules: props.actionType === 'add' ? [{ required: true, message: '请输入密码' }] : []
    }
  },
  {
    field: 'real_name',
    label: '姓名',
    component: 'Input',
    componentProps: {
      placeholder: '请输入姓名'
    },
    formItemProps: {
      rules: [{ required: true, message: '请输入姓名' }]
    }
  },
  {
    field: 'email',
    label: '邮箱',
    component: 'Input',
    componentProps: {
      placeholder: '请输入邮箱'
    }
  }
])

const formRef = ref()
const loading = ref(false)

const submit = async () => {
  const form = formRef.value
  await form?.validate()
  const data = await form?.getFormData()
  
  loading.value = true
  try {
    if (props.actionType === 'add') {
      await createStudentApi(data)
      ElMessage.success('创建成功')
    } else {
      await updateStudentApi(props.currentRow.id, data)
      ElMessage.success('更新成功')
    }
    emit('submit')
  } finally {
    loading.value = false
  }
}

defineExpose({ submit })
</script>

<template>
  <Form
    ref="formRef"
    :schema="schema"
    :model="currentRow"
    label-width="80px"
  />
</template>
