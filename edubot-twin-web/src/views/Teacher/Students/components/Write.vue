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

const ROLE_OPTIONS = [
  { label: '学生', value: 'student', roleId: '10' },
  { label: '教师', value: 'teacher', roleId: '20' },
  { label: '管理员', value: 'admin', roleId: '30' }
]

const roleIdMap = ROLE_OPTIONS.reduce<Record<string, string>>((acc, item) => {
  acc[item.value] = item.roleId
  return acc
}, {})

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
    field: 'role_code',
    label: '角色',
    component: 'Select',
    value: 'student',
    componentProps: {
      options: ROLE_OPTIONS.map((item) => ({
        label: item.label,
        value: item.value
      })),
      on: {
        change: (value: string) => {
          setValues({
            role_code: value,
            role_id: roleIdMap[value] || '10'
          })
        }
      }
    }
  },
  {
    field: 'role_id',
    label: '角色ID',
    component: 'Input',
    value: '10',
    componentProps: {
      disabled: true
    }
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
  role_code: [required()],
  real_name: [],
  password: [
    {
      validator: (_rule: any, value: any, callback: any) => {
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
      validator: (_rule: any, value: any, callback: any) => {
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
      formData.role_id = roleIdMap[formData.role_code] || formData.role_id

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
    if (!currentRow) {
      setValues({
        role_code: 'student',
        role_id: '10',
        is_active: true
      })
      return
    }
    setValues({
      ...currentRow,
      role_code: currentRow.role_code || 'student',
      role_id: currentRow.role_id || roleIdMap[currentRow.role_code] || '10'
    })
  },
  {
    deep: true,
    immediate: true
  }
)

watch(
  () => props.actionType,
  (actionType) => {
    if (actionType === 'add') {
      setValues({
        role_code: 'student',
        role_id: '10',
        is_active: true
      })
    }
  },
  {
    immediate: true
  }
)
</script>

<template>
  <Form :rules="rules" @register="formRegister" :schema="formSchema" />
  <div style="margin-top: 20px; text-align: right">
    <ElButton @click="$emit('close')"> 取消 </ElButton>
    <ElButton type="primary" :loading="loading" @click="submit"> 保存 </ElButton>
  </div>
</template>
