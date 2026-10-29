export const wechatBusyStatuses = new Set(['pending', 'evidence_ready', 'running', 'generating', 'generated', 'waiting', 'checking', 'ready', 'cover_resolving', 'cover_ready', 'submitting', 'reviewing', 'reconciling'])
export function articleUrl(value: string) {
  try { const url = new URL(value); return url.protocol === 'https:' && url.hostname === 'mp.weixin.qq.com' && (url.pathname.startsWith('/s/') || url.pathname === '/s') && !url.username && !url.password } catch { return false }
}
export function statusLabel(status: string) {
  return ({ active: '定时运行中', paused: '已暂停', pending: '等待开始', running: '创作中', evidence_ready: '选题已准备', generating: '正在写作', generated: '文章已生成', waiting: '等待处理', checking: '内容审核中', ready: '等待投递', cover_resolving: '准备封面', cover_ready: '封面已就绪', submitting: '正在投递', reviewing: '微信处理中', reconciling: '结果待核对', draft_delivered: '草稿已送达', no_publication: '本次未选题', canceled: '已取消', failed: '需要处理', rejected: '审核未通过', expired: '已过期', published: '已发表', success: '已完成', skipped: '已跳过', passed: '审核通过' } as Record<string, string>)[status] || status || '等待处理'
}
export function runGroup(run: any) {
  if ((run.status === 'published' || run.manualPublicationConfirmed) && articleUrl(run.publishedUrl)) return 'published'
  if (run.status === 'draft_delivered' && !run.manualPublicationConfirmed) return 'draft'
  if (['failed', 'rejected', 'reconciling'].includes(run.status)) return 'attention'
  if (wechatBusyStatuses.has(run.status)) return 'progress'
  return 'other'
}
export function runTitle(run: any) { return run.articleTitle || (run.revisionOfRunId ? `文章修订 · 第 ${run.revisionNumber || 2} 版` : `${run.businessDate || ''} 资讯文章`) }
export function errorMessage(cause: any, fallback: string) { return cause?.response?.data?.message || cause?.message || fallback }
export function workspaceFailure(reason = '') {
  const messages: Record<string, string> = {
    WECHAT_COVER_UNAVAILABLE: '未找到可用封面，请到公众号账号中同步素材并设置默认封面。',
    WECHAT_CREDENTIAL_MISSING: '尚未配置公众号凭据，请到公众号账号中完成接入。',
  }
  return messages[reason] || ''
}
export function beijingTime(value: string) { return value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }) : '尚未开始' }
