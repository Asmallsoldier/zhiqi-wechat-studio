import type { Router } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

export interface Breadcrumb {
  type: string
  label: string
  time: string
}

const breadcrumbs: Breadcrumb[] = []
let reporting = false

const clean = (value: string, max = 128) => value
  .replace(/(password|token|secret|cookie|authorization|key)=[^&\s]+/gi, '$1=***')
  .slice(0, max)

export const addBreadcrumb = (type: string, label: string) => {
  breadcrumbs.push({ type: clean(type, 32), label: clean(label), time: new Date().toISOString() })
  if (breadcrumbs.length > 30) breadcrumbs.splice(0, breadcrumbs.length - 30)
}

const report = async (message: string, stack: string, errorType: string) => {
  if (reporting) return
  const auth = useAuthStore()
  if (!auth.accessToken) return
  reporting = true
  try {
    await fetch('/api/v1/ops/client-errors', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${auth.accessToken}`,
        'X-Request-Id': `${Date.now()}-client-error`,
        'X-Operation-Id': `${Date.now()}-browser`,
      },
      body: JSON.stringify({
        errorId: crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`,
        errorType,
        message: clean(message, 4000),
        stack: clean(stack, 16000),
        page: `${location.origin}${location.pathname}`,
        release: import.meta.env.VITE_RELEASE_VERSION || 'development',
        breadcrumbs: breadcrumbs.slice(-30),
      }),
    })
  } catch {
    // 避免遥测失败再次触发全局错误。
  } finally {
    reporting = false
  }
}

export const setupBrowserObservability = (router: Router) => {
  router.afterEach((to) => addBreadcrumb('route', String(to.name || to.path)))
  document.addEventListener('click', (event) => {
    const target = event.target as HTMLElement | null
    if (!target) return
    const label = target.getAttribute('aria-label') || target.getAttribute('data-testid') || target.tagName.toLowerCase()
    addBreadcrumb('click', label)
  }, { capture: true })
  window.addEventListener('error', (event) => {
    void report(event.message || 'JavaScript error', event.error?.stack || '', 'javascript')
  })
  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason instanceof Error ? event.reason : new Error(String(event.reason))
    void report(reason.message, reason.stack || '', 'unhandledrejection')
  })
}

export const getBreadcrumbsForTest = () => [...breadcrumbs]
