<script setup lang="ts">
import { Form, FormSchema } from '@/components/Form'
import { useForm } from '@/hooks/web/useForm'
import { PropType, reactive, watch, ref } from 'vue'
import { useValidator } from '@/hooks/web/useValidator'
import { createStudentApi, updateStudentApi } from '@/api/teacher'
import { ElButton, ElMessage } from 'element-plus'

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
  real_name: [],
  password: [
    {
      validator: (rule: any, value: any, callback: any) => {
        if (props.actionType === 'add' && (!value || value.length < 6)) {
          callback(new Error('密码至少需要6个字符'))
        } else if (props.actionType === 'edit' && value && value.length < 6) {
          callback(new Error('密码至少需要6个字符'))
        } else {
          callback()
        }
      },
      trigger: 'blur'
    }
  ],
  email: [
    {
      validator: (rule: any, value: any, callback: any) => {
        if (value && value.trim() !== '') {
          const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
          if (!emailRegex.test(value)) {
            callback(new Error('请输入有效的邮箱地址'))
          } else {
            callback()
          }
        } else {
          callback()
        }
      },
      trigger: 'blur'
    }
  ]
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

      // email如果是空字符串，Pydantic EmailStr验证会报错422，需要删除
      if (formData.email === '') {
        delete formData.email
      }

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
      ElMessage.success(props.actionType === 'add' ? '添加成功' : '更新成功')
      emit('submit')
    } catch (e: any) {
      // axios 拦截器已经显示了通用错误，这里不再重复显示
      // 只在有详细错误信息时才覆盖显示
      if (e?.response?.data?.detail) {
        ElMessage.error(e.response.data.detail)
      }
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
