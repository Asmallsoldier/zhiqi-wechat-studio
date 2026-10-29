import axios from 'axios'
import type { AxiosInstance, InternalAxiosRequestConfig, AxiosResponse } from 'axios'
import { useAuthStore } from '@/stores/auth'
import { addBreadcrumb } from '@/utils/observability'

const request: AxiosInstance = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})
let refreshing: Promise<any> | null = null

// 请求拦截器
request.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const authStore = useAuthStore()
  if (authStore.accessToken) {
    config.headers.Authorization = `Bearer ${authStore.accessToken}`
  }
  // requestId 透传
  config.headers['X-Request-Id'] = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
  const method = (config.method || 'get').toLowerCase()
  if (['post', 'put', 'patch', 'delete'].includes(method) && !config.headers['X-Operation-Id']) {
    config.headers['X-Operation-Id'] = `${Date.now()}-op-${Math.random().toString(36).slice(2, 12)}`
  }
  return config
})

// 响应拦截器
request.interceptors.response.use(
  (response: AxiosResponse) => response.data,
  async (error) => {
    addBreadcrumb('http_error', `${error.config?.method || 'GET'} ${String(error.config?.url || '').split('?')[0]} ${error.response?.status || 'NETWORK'}`)
    if (error.response?.status === 401) {
      const authStore = useAuthStore()
      // 尝试刷新 token
      if (authStore.refreshToken && !error.config._retry) {
        error.config._retry = true
        try {
          if (!refreshing) refreshing = axios.post('/api/v1/auth/refresh', {
            refreshToken: authStore.refreshToken,
          }).finally(() => { refreshing = null })
          const res = await refreshing
          if (res.data?.success) {
            authStore.updateAccessToken(res.data.data.accessToken, res.data.data.refreshToken)
            error.config.headers.Authorization = `Bearer ${res.data.data.accessToken}`
            return request(error.config)
          }
        } catch {
          // refresh 也失败，跳转登录
        }
      }
      authStore.clearAuth()
      window.location.href = '/login'
    }
    return Promise.reject(error)
  },
)

export default request
