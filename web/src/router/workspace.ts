import { isWechatProduct } from '@/product'
export function canEnterAdmin(auth: { role: string; can: (permission: string) => boolean }) {
  return auth.role === 'super_admin' || auth.can('workspace.admin')
}
export function workspaceHome(auth: { role: string; can: (permission: string) => boolean }) {
  return isWechatProduct ? '/studio/wechat' : canEnterAdmin(auth) ? '/admin/dashboard' : isWechatWorkspaceOnly(auth) ? '/studio/wechat' : '/studio'
}
export function isWechatWorkspaceOnly(auth: { role: string; can: (permission: string) => boolean }) {
  return !canEnterAdmin(auth) && auth.can('wechat.read') && !['pet.read', 'history.read', 'novels.read', 'douyin.read', 'assets.read', 'distribution.read', 'accounts.read', 'workflows.read', 'tasks.read'].some(auth.can)
}

/** Return a same-origin absolute path suitable for a post-login redirect. */
export function safeReturnPath(candidate: unknown, origin: string): string | undefined {
  if (typeof candidate !== 'string' || !candidate.startsWith('/') || candidate.startsWith('//') || candidate.includes('\\')) return undefined
  try {
    const url = new URL(candidate, origin)
    if (url.origin !== origin) return undefined
    return `${url.pathname}${url.search}${url.hash}`
  } catch {
    return undefined
  }
}

const paths: Record<string, string> = {
  '/admin/dashboard': '/studio', '/admin/profile': '/studio/profile',
  '/admin/pet-series': '/studio/pets', '/admin/history-videos': '/studio/history',
  '/admin/novels': '/studio/novels', '/admin/novel/videos': '/studio/novel-video',
  '/admin/novel-writing/plans': '/studio/writing-plans', '/admin/assets/list': '/studio/assets',
  '/admin/director-studio': '/studio/delivery', '/admin/distribution': '/studio/publishing',
  '/admin/wechat/operations': '/studio/wechat', '/admin/douyin-promotion': '/studio/promotion',
  '/admin/content-calendar': '/studio/calendar', '/admin/risk/accounts': '/studio/accounts',
  '/admin/task/list': '/studio/activity', '/admin/workflow/center': '/studio/workflows',
}
export function customerPath(path: string) {
  if (paths[path]) return paths[path]
  if (path.startsWith('/admin/assets/detail/')) return path.replace('/admin/assets/detail/', '/studio/assets/')
  if (path.startsWith('/admin/task/trace/')) return path.replace('/admin/task/trace/', '/studio/activity/')
  return undefined
}
export function customerLink(url: string) {
  if (!url.startsWith('/admin/')) return url
  const index = url.search(/[?#]/)
  const path = index < 0 ? url : url.slice(0, index)
  return (customerPath(path) || '/studio/projects') + (index < 0 ? '' : url.slice(index))
}
