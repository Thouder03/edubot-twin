<script setup lang="ts">
import { Form, FormSchema } from '@/components/Form'
import { useForm } from '@/hooks/web/useForm'
import { PropType, reactive, ref } from 'vue'
import { useValidator } from '@/hooks/web/useValidator'
import { ElMessage, ElMessageBox, ElDivider } from 'element-plus'
import request from '@/axios'
import { getTokenApi } from '@/api/login'

interface PersonalUserInfo {
  id: number
  username: string
  realName: string
  email: string
}

const props = defineProps({
  userInfo: {
    type: Object as PropType<PersonalUserInfo | undefined>,
    default: () => undefined
  }
})

const { required, lengthRange } = useValidator()

const formSchema = reactive<FormSchema[]>([
  {
    field: 'password',
    label: '旧密码',
    component: 'InputPassword',
    colProps: {
      span: 24
    }
  },
  {
    field: 'newPassword',
    label: '新密码',
    component: 'InputPassword',
    colProps: {
      span: 24
    },
    componentProps: {
      strength: true
    }
  },
  {
    field: 'newPassword2',
    label: '确认新密码',
    component: 'InputPassword',
    colProps: {
      span: 24
    },
    componentProps: {
      strength: true
    }
  }
])

const rules = reactive({
  password: [required()],
  newPassword: [
    required(),
    lengthRange({ min: 6, max: 50, message: '密码长度需在6-50位之间' }),
    {
      asyncValidator: async (_, val, callback) => {
        const formData = await getFormData()
        const { newPassword2 } = formData
        if (val !== newPassword2) {
          callback(new Error('新密码与确认新密码不一致'))
        } else {
          callback()
        }
      }
    }
  ],
  newPassword2: [
    required(),
    {
      asyncValidator: async (_, val, callback) => {
        const formData = await getFormData()
        const { newPassword } = formData
        if (val !== newPassword) {
          callback(new Error('确认新密码与新密码不一致'))
        } else {
          callback()
        }
      }
    }
  ]
})

const { formRegister, formMethods } = useForm()
const { getFormData, getElFormExpose } = formMethods

const saveLoading = ref(false)
const save = async () => {
  const elForm = await getElFormExpose()
  const valid = await elForm?.validate().catch((err) => {
    console.log(err)
  })
  if (valid) {
    ElMessageBox.confirm('是否确认修改?', '提示', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      type: 'warning'
    })
      .then(async () => {
        try {
          saveLoading.value = true
          if (!props.userInfo?.id) {
            ElMessage.error('未获取到用户信息，暂无法修改密码')
            return
          }

          const formData = await getFormData<{ password: string; newPassword: string }>()

          const verifyRes = await getTokenApi({
            username: props.userInfo.username,
            password: formData.password
          })
          if (!verifyRes?.data?.access_token) {
            ElMessage.error('旧密码错误')
            return
          }

          await request.put({
            url: `/api/v1/students/${props.userInfo.id}`,
            data: { password: formData.newPassword }
          })
          ElMessage.success('修改成功')
        } catch (error) {
          console.log(error)
        } finally {
          saveLoading.value = false
        }
      })
      .catch(() => {})
  }
}
</script>

<template>
  <Form :rules="rules" @register="formRegister" :schema="formSchema" />
  <ElDivider />
  <BaseButton type="primary" :loading="saveLoading" @click="save">确认修改</BaseButton>
</template>
