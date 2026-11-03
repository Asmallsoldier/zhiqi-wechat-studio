import { defineStore } from 'pinia'
import { ref } from 'vue'
import request from '@/utils/request'
import {basePath} from '@/utils/basePath'

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref('')
  const refreshToken = ref('')
  const userId = ref('')
  const role = ref('')      // super_admin | admin | readonly_admin
  const username = ref('')
  const displayName = ref('')
  const status = ref('')
  const mustChangePassword = ref(false)
  const permissions = ref<string[]>([])
  const profileLoaded = ref(false)

  function setAuth(data: {
    userId: string
    role: string
    accessToken: string
    refreshToken: string
    username?: string
  }) {
    userId.value = data.userId
    role.value = data.role
    accessToken.value = data.accessToken
    refreshToken.value = data.refreshToken
    if (data.username) username.value = data.username
    profileLoaded.value = false
  }

  async function loadProfile() {
    const response: any = await request.get('/auth/me')
    if (!response.success) throw new Error(response.message || '无法获取用户资料')
    const profile = response.data
    userId.value = profile.userId
    username.value = profile.username
    displayName.value = profile.displayName || ''
    role.value = profile.role
    status.value = profile.status
    mustChangePassword.value = !!profile.mustChangePassword
    permissions.value = profile.permissions || []
    profileLoaded.value = true
  }

  function can(permission: string) {
    return role.value === 'super_admin' || permissions.value.includes(permission)
  }

  function updateAccessToken(token: string, rotatedRefresh?: string) {
    accessToken.value = token
    if (rotatedRefresh) refreshToken.value = rotatedRefresh
  }

  function clearAuth() {
    accessToken.value = ''
    refreshToken.value = ''
    userId.value = ''
    role.value = ''
    username.value = ''
    displayName.value = ''
    status.value = ''
    mustChangePassword.value = false
    permissions.value = []
    profileLoaded.value = false
  }

  return { accessToken, refreshToken, userId, role, username, displayName, status, mustChangePassword, permissions, profileLoaded, setAuth, loadProfile, can, updateAccessToken, clearAuth }
}, {
  persist: {
    key: basePath==='/' ? 'zhiqi-auth' : `zhiqi-auth:${basePath}`,
    storage: sessionStorage,
    paths: ['accessToken', 'refreshToken', 'userId', 'role', 'username', 'displayName', 'status', 'mustChangePassword', 'permissions'],
  },
})
