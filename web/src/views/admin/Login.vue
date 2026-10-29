<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-brand">智</div><p class="login-eyebrow">{{ isWechatProduct ? 'ZHIQI WECHAT STUDIO' : 'ZHIQI CREATOR STUDIO' }}</p><h2>{{ isWechatProduct ? '让好内容，持续到达读者' : '欢迎回到你的创作空间' }}</h2><p class="login-description">{{ isWechatProduct ? '连接公众号，开始原创图文与日常运营。' : '登录智启无人，继续下一件作品。' }}</p>
      <el-form :model="form" @submit.prevent="handleLogin" label-position="top">
        <el-form-item label="账号">
          <el-input v-model="form.username" prefix-icon="User" placeholder="请输入账号" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" prefix-icon="Lock" placeholder="请输入密码" show-password />
        </el-form-item>
        <el-button type="primary" :loading="loading" style="width: 100%" @click="handleLogin">
          登 录
        </el-button>
      </el-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { isWechatProduct } from '@/product'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { login } from '@/api'
import { safeReturnPath, workspaceHome } from '@/router/workspace'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const loading = ref(false)
const form = reactive({ username: '', password: '' })

function postLoginPath() {
  const candidate = safeReturnPath(route.query.redirect, window.location.origin)
  if (!candidate) return undefined
  const resolved = router.resolve(candidate)
  if (!resolved.matched.length || resolved.name === 'NotFound' || ['/login', '/admin/login', '/403'].includes(resolved.path)) return undefined
  return resolved.fullPath
}

const handleLogin = async () => {
  if (!form.username || !form.password) {
    ElMessage.warning('请输入账号和密码')
    return
  }
  loading.value = true
  try {
    const res: any = await login(form)
    if (res.success) {
      authStore.setAuth({
        userId: res.data.userId,
        role: res.data.role,
        accessToken: res.data.accessToken,
        refreshToken: res.data.refreshToken,
        username: form.username,
      })

      // localStorage.setItem('token', res.data.accessToken)

      ElMessage.success('登录成功')
      await authStore.loadProfile()
      const target = postLoginPath()
      router.push(authStore.mustChangePassword ? (workspaceHome(authStore).startsWith('/admin') ? '/admin/profile' : '/studio/profile') : target || workspaceHome(authStore))
    } else {
      ElMessage.error(res.message || '登录失败')
    }
  } catch (e: any) {
    ElMessage.error('网络异常，请重试')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100dvh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: radial-gradient(ellipse at 25% 30%, #e4ead9, transparent 50%), #f6f7f1;
  --el-color-primary: #526449;
}
.login-card {
  width: min(380px, calc(100vw - 32px));
  box-sizing: border-box;
  padding: clamp(20px, 5vw, 40px);
  background: rgba(255, 255, 255, 0.95);
  border-radius: 20px;
  border: 1px solid #e1e7d8;
  box-shadow: 0 16px 64px rgba(72, 92, 48, 0.08);
}
.login-card h2 {
  text-align: center;
  margin: 14px 0 10px;
  color: #34432b;
  font-size: 21px;
  font-weight: 600;
}
.login-brand { width: 48px; height: 48px; margin: 0 auto 18px; background: #526449; border-radius: 14px; color: white; font-size: 28px; display: grid; place-items: center; }
.login-eyebrow { text-align: center; font-size: 9px; letter-spacing: 2px; color: #98a38b; }
.login-description { text-align: center; font-size: 12px; color: #919d82; margin: 0 0 28px; }
</style>
