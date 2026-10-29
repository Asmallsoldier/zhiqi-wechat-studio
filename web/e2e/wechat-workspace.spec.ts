import { test, expect } from '@playwright/test'

const account = { accountId: '11111111-1111-1111-1111-111111111111', accountName: '未来行业观察', platform: 'wechat_official', platformAccountId: 'gh_fixture', configured: true }
const plan = { planId: 'plan', version: 1, status: 'active', authorizationExpiresAt: '2099-10-20T00:00:00+08:00', settings: { accountId: account.accountId, workflowId: 'workflow', approvedFeedId: 'ai-china', dailyPublishTime: '09:00', startDate: '2026-10-13', endDate: '2026-11-10', deliveryMode: 'draft_only' } }
const runs = [
  { runId: 'draft', planId: 'plan', businessDate: '2026-10-13', status: 'draft_delivered', articleTitle: '从工具到协作伙伴：AI 正在改变企业的工作方式', auditStatus: 'passed', qualityScore: 92, coverSource: 'material', deliveryMode: 'draft_only', deliveryId: 'delivery', triggerKind: 'manual' },
  { runId: 'working', planId: 'plan', businessDate: '2026-10-13', status: 'generating', articleTitle: '机器人走进工厂，产业应用进入新阶段', auditStatus: 'pending', triggerKind: 'scheduled' },
  { runId: 'failed', planId: 'plan', businessDate: '2026-10-12', status: 'failed', articleTitle: '本周行业观察：寻找新的应用机会', auditStatus: 'passed', qualityScore: 88, reason: 'WECHAT_COVER_UNAVAILABLE', triggerKind: 'manual', workflowRunId: 'workflow-run', planVersion: 1, deliveryMode: 'draft_only' },
]
test.beforeEach(async ({ page }) => {
  await page.route('https://mmbiz.qpic.cn/workspace-fixture', route => route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="90"><rect width="160" height="90" fill="#e0e8d8"/></svg>' }))
  await page.addInitScript(() => sessionStorage.setItem('zhiqi-auth', JSON.stringify({ accessToken: 'fixture', refreshToken: '', userId: 'operator', role: 'wechat_operator', username: 'wechat_operator' })))
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname.replace('/api/v1', '')
    let data: any
    if (path === '/auth/me') data = { userId: 'operator', username: 'wechat_operator', displayName: '公众号运营员', role: 'wechat_operator', status: 'active', permissions: ['wechat.read', 'wechat.write', 'wechat.execute', 'wechat.publish', 'wechat.authorize'] }
    else if (path === '/wechat-workspace/accounts') data = [account]
    else if (path === '/wechat-workspace/workflows') data = [{ workflowId: 'workflow', name: 'AI 行业热点解读', workflowType: 'wechat_operations' }]
    else if (path === '/wechat-automation/status') data = { plans: [plan], runs }
    else if (path === '/wechat-operations/news-sources') data = [{ feedId: 'ai-china', name: '国内 AI 资讯合集', kind: 'domestic_collection', description: '从真实来源采集行业动态。' }]
    else if (path.endsWith('/credential')) data = { clientConfigured: true, authStatus: 'configured' }
    else if (path.endsWith('/materials')) data = { items: [{ mediaId: 'fixture-image', name: '产业观察默认封面', previewUrl: 'https://mmbiz.qpic.cn/workspace-fixture', isDefault: true }], defaultMediaId: 'fixture-image', total: 1, syncedAt: '2026-10-13T01:00:00Z' }
    else if (path === '/wechat-workspace/runs/draft') data = { title: runs[0].articleTitle, body: '这是一段用于界面验收的文章预览。\n\n文章正文、审核进度与投递结果在同一个面板中呈现。', articleBlocks: [{ kind: 'heading', text: '从需求开始理解变化' }, { kind: 'text', text: '这是一段用于界面验收的文章预览。' }, { kind: 'image', text: '图1 · 原创信息图（非现场照片）', url: 'https://mmbiz.qpic.cn/workspace-fixture' }], createTime: '2026-10-13T01:00:00Z', updateTime: '2026-10-13T01:05:00Z', stages: [{ stepName: '资料采集', status: 'success', finishedAt: '2026-10-13T01:01:00Z' }, { stepName: '独立写作', status: 'success', finishedAt: '2026-10-13T01:02:00Z' }, { stepName: '事实与质量审核', status: 'success', finishedAt: '2026-10-13T01:03:00Z' }], logs: [{ toStatus: 'draft_delivered', detail: '公众号草稿已送达', createTime: '2026-10-13T01:05:00Z' }], delivery: { deliveryId: 'delivery', status: 'awaiting_confirmation', remotePostId: 'fixture-draft-media-id', remoteUrl: '', deliveryMode: 'draft_only' } }
    else if (path.endsWith('/confirm-publication')) data = { status: 'published' }
    else if (path === '/client-errors') data = {}
    else return route.fulfill({ status: 404, json: { success: false, message: 'Fixture endpoint not defined' } })
    await route.fulfill({ json: { success: true, data } })
  })
})

test('operator lands in WeChat, reads article and receipts without other-module APIs', async ({ page }) => {
  const businessCalls: string[] = []
  page.on('request', req => { if (req.url().includes('/api/v1/')) businessCalls.push(new URL(req.url()).pathname) })
  await page.goto('/studio')
  await expect(page).toHaveURL(/\/studio\/wechat$/)
  await expect(page.getByRole('heading', { name: '公众号，也可以从容运营。' })).toBeVisible()
  await expect(page.getByRole('navigation', { name: '创作者导航' }).getByRole('link')).toHaveCount(5)
  await page.getByRole('button', { name: '待发表', exact: false }).click()
  await expect(page.locator('.wx-run-card')).toHaveCount(1)
  await page.getByRole('button', { name: '预览文章', exact: true }).click()
  await expect(page.locator('.wx-reading')).toContainText('文章预览')
  await expect(page.locator('.wx-article-figure img')).toBeVisible()
  await expect(page.locator('.wx-article-figure')).toContainText('原创信息图')
  await page.getByRole('dialog', { name: '文章与投递详情' }).getByText('处理记录', { exact: true }).click()
  await expect(page.locator('.wx-timeline')).toContainText('事实与质量审核')
  await page.getByRole('dialog', { name: '文章与投递详情' }).getByText('投递结果', { exact: true }).click()
  await expect(page.locator('.wx-receipt')).toContainText('fixture-draft-media-id')
  await page.getByLabel('正式文章链接', { exact: true }).fill('https://mp.weixin.qq.com.evil.test/s/invalid')
  await expect(page.getByRole('button', { name: '登记人工发表结果', exact: true })).toBeDisabled()
  await page.getByLabel('正式文章链接', { exact: true }).fill('https://mp.weixin.qq.com/s/fixture-article')
  await page.getByRole('button', { name: '登记人工发表结果', exact: true }).click()
  expect(businessCalls.every(path => path.includes('/wechat-') || path.includes('/auth/') || path.includes('/client-errors'))).toBe(true)
})

test('account configuration and responsive workspace remain usable', async ({ page }) => {
  await page.goto('/studio/wechat/accounts')
  await page.getByRole('button', { name: '管理账号', exact: true }).click()
  await expect(page.getByText('已加密保存', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '检测连接', exact: true })).toBeEnabled()
  await expect(page.getByText('产业观察默认封面', { exact: true })).toBeVisible()
  await expect.poll(() => page.getByAltText('产业观察默认封面', { exact: true }).evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0)
  await page.screenshot({ path: 'test-results/wechat-account-desktop.png', fullPage: true })
  await page.goto('/studio/wechat')
  await page.setViewportSize({ width: 1440, height: 1100 })
  await expect(page.locator('.wx-run-card')).toHaveCount(3)
  await page.screenshot({ path: 'test-results/wechat-workspace-desktop.png', fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await expect.poll(async () => (await page.locator('.creator-sidebar').boundingBox())!.x + (await page.locator('.creator-sidebar').boundingBox())!.width).toBeLessThanOrEqual(0)
  await expect(page.getByRole('heading', { name: '公众号，也可以从容运营。' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: 'test-results/wechat-workspace-mobile.png', fullPage: true })
  await page.getByRole('button', { name: '打开导航' }).click()
  await expect(page.getByRole('button', { name: '关闭导航' })).toBeVisible()
  await page.getByRole('navigation', { name: '创作者导航' }).getByRole('link', { name: '公众号账号' }).click()
  await expect(page).toHaveURL(/\/studio\/wechat\/accounts$/)
  await expect(page.getByRole('button', { name: '关闭导航' })).not.toBeVisible()
  await page.goto('/studio/novels')
  await expect(page).toHaveURL(/\/studio\/wechat$/)
})

test('create plan opens from the overview and saves a paused plan', async ({ page }) => {
  let saved: any
  await page.route('**/api/v1/wechat-automation/plans', async route => {
    saved = route.request().postDataJSON()
    await route.fulfill({ json: { success: true, data: { ...plan, status: 'paused' } } })
  })
  await page.goto('/studio/wechat')
  await expect(page.locator('.wx-run-card')).toHaveCount(3)
  await page.getByRole('button', { name: '创建内容计划', exact: true }).click()
  await expect(page).toHaveURL(/\/studio\/wechat\/plans$/)
  const form = page.getByRole('dialog', { name: '新建运营计划' })
  await expect(form).toBeVisible()
  await expect(form.getByText('未来行业观察', { exact: true })).toBeVisible()
  await form.locator('.el-checkbox__label').click()
  await expect(form.getByRole('checkbox')).toBeChecked()
  await form.getByRole('button', { name: '保存为暂停计划', exact: true }).click()
  await expect(form).not.toBeVisible()
  expect(saved.accountId).toBe(account.accountId)
  expect(saved.deliveryMode).toBe('draft_only')
})

test('new operator can add an account, save credentials and check its connection', async ({ page }) => {
  let accountRequest: any, credentialRequest: any
  await page.route('**/api/v1/wechat-workspace/accounts', async route => {
    if (route.request().method() === 'POST') {
      accountRequest = route.request().postDataJSON()
      return route.fulfill({ json: { success: true, data: { accountId: accountRequest.requestId } } })
    }
    await route.fulfill({ json: { success: true, data: accountRequest ? [{ ...accountRequest, accountId: accountRequest.requestId, platform: 'wechat_official' }] : [] } })
  })
  await page.route('**/api/v1/wechat-workspace/accounts/*/credential', async route => {
    if (route.request().method() === 'PUT') credentialRequest = route.request().postDataJSON()
    await route.fulfill({ json: { success: true, data: { clientConfigured: !!credentialRequest } } })
  })
  await page.route('**/api/v1/wechat-workspace/accounts/*/probe', async route => route.fulfill({ json: { success: true, data: { tokenConnected: true, draftAccessible: true } } }))
  await page.goto('/studio/wechat')
  await expect(page.locator('.wx-run-card')).toHaveCount(3)
  await page.getByRole('button', { name: '创建内容计划', exact: true }).click()
  const create = page.getByRole('dialog', { name: '添加公众号' })
  await expect(create).toBeVisible()
  await create.getByLabel('公众号名称', { exact: true }).fill('我的行业周刊')
  await create.getByRole('button', { name: '创建并配置' }).click()
  const settings = page.getByRole('dialog', { name: '我的行业周刊' })
  await expect(settings).toBeVisible()
  await settings.getByLabel('AppID', { exact: true }).fill('wx_fixture')
  await settings.getByLabel('AppSecret', { exact: true }).fill('fixture-only-secret')
  await settings.getByRole('button', { name: '保存凭据' }).click()
  await expect(settings.getByLabel('AppSecret', { exact: true })).toHaveValue('')
  await settings.getByRole('button', { name: '检测连接' }).click()
  await expect(settings).toContainText('连接正常，可访问公众号草稿箱')
  expect(accountRequest).not.toHaveProperty('ownerId')
  expect(credentialRequest).toEqual({ appId: 'wx_fixture', appSecret: 'fixture-only-secret' })
})
