<script lang="ts" setup>
import { FormSchema, Form } from '@/components/Form'
import { useForm } from '@/hooks/web/useForm'
import { useValidator } from '@/hooks/web/useValidator'
import { PropType, reactive, ref, watch } from 'vue'
import { ElDivider, ElMessage, ElMessageBox } from 'element-plus'
import request from '@/axios'

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

const emit = defineEmits<{
  updated: []
}>()

const { email } = useValidator()

const formSchema = reactive<FormSchema[]>([
  {
    field: 'username',
    label: '账号',
    component: 'Input',
    colProps: {
      span: 24
    },
    componentProps: {
      disabled: true
    }
  },
  {
    field: 'realName',
    label: '昵称',
    component: 'Input',
    colProps: {
      span: 24
    },
    componentProps: {
      disabled: true
    }
  },
  {
    field: 'email',
    label: '邮箱',
    component: 'Input',
    colProps: {
      span: 24
    }
  }
])

const rules = reactive({
  email: [email()]
})

const { formRegister, formMethods } = useForm()
const { setValues, getElFormExpose } = formMethods

watch(
  () => props.userInfo,
  (value) => {
    setValues(value ?? {})
  },
  {
    immediate: true,
    deep: true
  }
)

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
            ElMessage.error('未获取到用户信息，暂无法保存')
            return
          }
          const formData = await formMethods.getFormData<{ email?: string }>()
          const payload: { email?: string } = {
            email: formData.email?.trim() || undefined
          }
          await request.put({ url: `/api/v1/students/${props.userInfo.id}`, data: payload })
          ElMessage.success('修改成功')
          emit('updated')
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
  <BaseButton type="primary" @click="save">保存</BaseButton>
</template>
