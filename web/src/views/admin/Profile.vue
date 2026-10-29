<template>
  <el-card>
    <template #header>个人设置</template>
    <el-alert v-if="auth.mustChangePassword" title="首次登录或密码已重置，请先修改密码" type="warning" :closable="false" style="margin-bottom: 20px" />
    <el-descriptions :column="1" style="margin-bottom: 20px">
      <el-descriptions-item label="账号">{{ auth.username }}</el-descriptions-item>
      <el-descriptions-item label="姓名">{{ auth.displayName || '未设置' }}</el-descriptions-item>
    </el-descriptions>
    <el-form :model="form" label-width="110px" style="max-width: 560px" @submit.prevent="submit">
      <el-form-item label="当前密码" :error="errors.currentPassword">
        <el-input v-model="form.currentPassword" type="password" autocomplete="current-password" show-password />
      </el-form-item>
      <el-form-item label="新密码" :error="errors.newPassword">
        <el-input v-model="form.newPassword" type="password" autocomplete="new-password" show-password />
        <div class="hint">至少 12 个字符 · 最多 72 个 UTF-8 字节 · 不得为空白或默认密码</div>
        <div class="hint">当前：{{ form.newPassword.length }} 个字符，{{ newPasswordBytes }} 个 UTF-8 字节</div>
      </el-form-item>
      <el-form-item label="确认新密码" :error="errors.confirmPassword">
        <el-input v-model="form.confirmPassword" type="password" autocomplete="new-password" show-password />
      </el-form-item>
      <el-form-item><el-button type="primary" native-type="submit" :loading="saving">修改密码并重新登录</el-button></el-form-item>
    </el-form>
  </el-card>
</template>
<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { changePassword } from '@/api'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const form = reactive({ currentPassword: '', newPassword: '', confirmPassword: '' })
const errors = reactive({ currentPassword: '', newPassword: '', confirmPassword: '' })
const saving = ref(false)
const newPasswordBytes = computed(() => new TextEncoder().encode(form.newPassword).length)
function validate() {
  errors.currentPassword = form.currentPassword ? '' : '请输入当前密码'
  errors.newPassword = form.newPassword.length < 12 ? '至少需要 12 个字符'
    : newPasswordBytes.value > 72 ? '不能超过 72 个 UTF-8 字节'
    : !form.newPassword.trim() ? '不能仅包含空白字符'
    : ''
  errors.confirmPassword = form.confirmPassword === form.newPassword ? '' : '两次输入的新密码不一致'
  return !Object.values(errors).some(Boolean)
}
async function submit() {
  if (saving.value || !validate()) return
  saving.value = true
  try {
    const result: any = await changePassword({ currentPassword: form.currentPassword, newPassword: form.newPassword })
    if (!result.success) {
      errors.newPassword = result.message || '密码修改失败'
      return
    }
    auth.clearAuth()
    ElMessage.success('密码已修改，请重新登录')
    await router.replace('/login')
  } catch (error: any) {
    const body = error?.response?.data
    const field = body?.field || body?.data?.field
    const validation = body?.data?.errors || body?.errors
    if (field === 'currentPassword') errors.currentPassword = body.message || '当前密码不正确'
    else if (field === 'newPassword') errors.newPassword = body.message || '密码修改失败'
    else if (validation?.currentPassword?.[0]) errors.currentPassword = validation.currentPassword[0]
    else if (validation?.newPassword?.[0]) errors.newPassword = validation.newPassword[0]
    else errors.newPassword = body?.message || '密码修改失败，请重试'
  } finally {
    form.currentPassword = form.newPassword = form.confirmPassword = ''
    saving.value = false
  }
}
</script>
<style scoped>.hint { color: #777; font-size: 12px; line-height: 1.5; width: 100%; }</style>
