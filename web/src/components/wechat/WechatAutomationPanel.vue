<template>
  <section class="wx-automation">
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <section v-if="view !== 'articles'" class="wx-plans-section">
      <div class="wx-section-head"><div><h2>运营计划</h2><p>选择内容方向，让每一次创作有明确的节奏。</p></div><div class="wx-actions"><t-button variant="outline" :loading="loading" @click="load">刷新</t-button><t-button v-if="access.can('wechat.write')" :disabled="!accounts.length" @click="openCreate">新建计划</t-button></div></div>
      <el-alert v-if="access.can('wechat.write') && !access.can('wechat.publish')" title="可保存、编辑和暂停计划。启用计划或投递公众号草稿需要公众号投递权限；保存不会启动生成或投递。" type="info" :closable="false" />
      <div v-if="state && !state.plans.length" class="wx-empty"><h3>{{ accounts.length ? '安排你的第一篇内容' : '先连接一个公众号' }}</h3><p>{{ accounts.length ? '选择账号、内容方向和每日投递时间，保存后可按需启用。' : '到公众号账号页面接入账号，再创建运营计划。' }}</p><t-button v-if="accounts.length && access.can('wechat.write')" @click="openCreate">新建运营计划</t-button></div>
      <div class="wx-plan-grid"><article v-for="plan in state?.plans || []" :key="plan.planId" class="wx-plan-card">
        <div class="wx-card-top"><span class="wx-kicker">{{ accountName(plan.settings.accountId) }}</span><span class="wx-pill" :class="plan.status === 'active' ? 'success' : 'neutral'">{{ label(plan.status) }}</span></div>
        <h3>{{ workflowName(plan.settings.workflowId) }}</h3><p>{{ feedName(plan.settings.approvedFeedId) }}</p><div class="wx-plan-time"><strong>{{ plan.settings.dailyPublishTime }}</strong><span>每日投递 · 北京时间<small>{{ plan.settings.startDate }} — {{ plan.settings.endDate }}</small></span></div>
        <p v-if="plan.reason" class="wx-inline-warning">{{ formatAutomationFailure(plan.reason) }}</p>
        <div class="wx-plan-actions"><el-button v-if="access.can('wechat.write')" link @click="edit(plan)">编辑</el-button><el-button v-if="plan.status === 'active' ? access.can('wechat.write') : access.can('wechat.publish')" link :disabled="busyId === plan.planId || (plan.status !== 'active' && plan.settings.deliveryMode !== 'draft_only')" @click="toggle(plan)">{{ plan.status === 'active' ? '暂停' : '启用' }}</el-button><t-button v-if="access.can('wechat.publish') && access.can('wechat.execute')" size="small" :loading="submittingId === plan.planId" :disabled="!canRun(plan) || !!submittingId" @click="runOnce(plan)">立即生成并投递</t-button></div>
      </article></div>
      <p class="wx-footnote">文章通过审核后送达公众号草稿箱，由负责人在微信后台发表。新建和修改后的计划保持暂停。</p>
    </section>
    <section v-if="view !== 'plans'" class="wx-runs-section">
      <div class="wx-section-head"><div><h2>内容与投递记录</h2><p>预览文章、了解处理进度，查看每次投递的实际结果。</p></div><t-button variant="outline" :loading="loading" @click="load">刷新记录</t-button></div>
      <div class="wx-record-toolbar"><div class="wx-filter-tabs" role="group" aria-label="筛选文章状态"><button v-for="item in filters" :key="item.value" :class="{ selected: runFilter === item.value }" @click="runFilter = item.value">{{ item.label }}<span>{{ countFor(item.value) }}</span></button></div><el-input v-model="runSearch" clearable placeholder="搜索标题或公众号" aria-label="搜索文章" /></div>
      <div v-if="state && !filteredRuns.length" class="wx-empty"><h3>{{ state.runs.length ? '没有符合条件的内容' : '你的内容会出现在这里' }}</h3><p>{{ state.runs.length ? '试试其他状态或关键词。' : '运行计划后，即可查看文章、审核进度和投递记录。' }}</p></div>
      <div class="wx-run-list"><article v-for="run in filteredRuns" :key="run.runId" class="wx-run-card">
        <div class="wx-run-mark" :class="runGroup(run)">{{ runGroup(run) === 'published' ? '✓' : runGroup(run) === 'attention' ? '!' : '文' }}</div>
        <div class="wx-run-content"><div class="wx-run-meta"><span>{{ accountForRun(run) }}</span><span>·</span><span>{{ run.businessDate }} · {{ run.triggerKind === 'manual' ? '手动运行' : '定时运行' }}</span><span class="wx-pill" :class="runGroup(run)">{{ runLabel(run) }}</span></div><button class="wx-title-button" @click="openDetail(run, 'article')">{{ runTitle(run) }}</button><p v-if="run.reason" class="wx-run-reason">{{ runReason(run) }}</p><div class="wx-run-facts"><span>审核 {{ label(run.auditStatus) }}</span><span v-if="run.qualityScore != null">质量 {{ run.qualityScore }} 分</span><span v-if="run.coverSource">{{ coverLabel(run.coverSource) }}</span><span v-if="run.revisionOfRunId">编辑版本 {{ run.revisionNumber || 2 }}</span></div>
        <div class="wx-run-actions"><t-button size="small" variant="text" @click="openDetail(run, 'article')">预览文章</t-button><t-button size="small" variant="text" @click="openDetail(run, 'logs')">处理记录</t-button><t-button v-if="run.deliveryId" size="small" variant="text" @click="openDetail(run, 'receipt')">{{ run.manualPublicationConfirmed ? '发表结果' : run.status === 'draft_delivered' ? '查看草稿与登记发表' : '投递详情' }}</t-button><el-button v-if="canRequestResume(run)" link type="warning" :loading="resumeLoadingId === run.runId" :disabled="!!resumeLoadingId" @click="resumeRun(run)">从失败步骤继续</el-button><el-button v-if="canOfferDraftEdit(run)" link type="primary" :loading="draftLoadingId === run.runId" :disabled="!!draftLoadingId" @click="openDraftEditor(run)">编辑并重新审核</el-button><a v-if="(run.status === 'published' || run.manualPublicationConfirmed) && isArticleUrl(run.publishedUrl)" :href="run.publishedUrl" target="_blank" rel="noopener noreferrer" class="wx-text-link">查看正式文章 ↗</a></div></div>
      </article></div>
    </section>
    <el-drawer class="wx-overlay" v-model="formVisible" :title="form.planId ? '编辑运营计划' : '新建运营计划'" size="560px" :close-on-click-modal="false">
    <el-form v-if="access.can('wechat.write')" label-position="top">
      <div class="plan-fields">
        <el-form-item label="公众号账号"><el-select v-model="form.accountId" placeholder="选择公众号"><el-option v-for="a in accounts.filter(a => a.platform === 'wechat_official')" :key="a.accountId" :label="a.accountName" :value="a.accountId" /></el-select></el-form-item>
        <WechatContentDirectionPicker v-if="formVisible" :workflows="workflows" :feeds="feeds" @choose="chooseContentDirection" />
        <el-form-item label="文章生成工作流"><div class="workflow-choice"><el-select v-model="form.workflowId" placeholder="选择系统公众号工作流" style="flex:1"><el-option v-for="w in workflows.filter(w => w.workflowType === 'wechat_operations')" :key="w.workflowId" :label="w.name" :value="w.workflowId" /></el-select><router-link v-if="access.can('workflows.read')" to="/admin/workflow/center">查看与编辑工作流</router-link></div><small>系统已准备好采集、写作、审核和封面流程，选择适合的内容方向即可。</small></el-form-item>
        <el-form-item label="真实资讯来源"><el-select v-model="form.approvedFeedId" placeholder="请选择已批准的资讯来源" filterable style="width:100%"><el-option v-for="feed in feeds" :key="feed.feedId" :label="feed.name" :value="feed.feedId"><span>{{ feed.name }}</span><small style="float:right;color:#84929a">{{ feed.kind === 'domestic_collection' ? '国内资讯' : feed.kind === 'official_collection' ? '官方合集' : '已批准' }}</small></el-option></el-select><small>{{ feeds.find(feed => feed.feedId === form.approvedFeedId)?.description }}</small></el-form-item>
        <div><el-button v-if="access.can('wechat.execute')" :disabled="!form.approvedFeedId" :loading="checkingFeed" @click="checkFeed">检测新闻源可用性</el-button><p v-if="feedStatus">{{ feedStatus }}</p></div>
        <el-form-item label="开始日期（北京时间）"><el-date-picker v-model="form.startDate" value-format="YYYY-MM-DD" type="date" /></el-form-item>
        <el-form-item label="结束日期（最多30天）"><el-date-picker v-model="form.endDate" value-format="YYYY-MM-DD" type="date" /></el-form-item>
        <el-form-item label="每天投递时间（北京时间）"><el-time-select v-model="form.dailyPublishTime" start="00:00" end="23:55" step="00:05" /></el-form-item>
        <el-form-item label="最低质量分（审核仍须通过）"><el-input-number v-model="form.minimumQualityScore" :min="0" :max="100" /></el-form-item>
      </div>
      <el-alert title="交付方式：自动生成并投递到公众号草稿箱，负责人审核后人工发表；保存计划不会直接运行。" type="info" :closable="false" />
      <el-checkbox v-model="form.acknowledgeAutomaticPublishing">确认以上账号、新闻源、工作流、日期和时间范围内可自动生成并投递草稿</el-checkbox>
      <div><el-button type="primary" :loading="saving" :disabled="!form.acknowledgeAutomaticPublishing" @click="save">保存为暂停计划</el-button><el-button @click="formVisible = false">取消</el-button></div>
    </el-form>
    </el-drawer>
    <el-drawer class="wx-overlay" v-model="draftEditorVisible" title="编辑文章并重新审核" size="680px" :close-on-click-modal="false">
      <el-alert v-if="draftEditorError" :title="draftEditorError" type="error" :closable="false" />
      <template v-if="draftEditor">
        <el-alert type="info" :closable="false" title="仅支持当日仍待人工发表的已投递草稿；保存会创建新版本并重新进行事实、质量审核。审核通过后才会投递新草稿，旧文章和旧草稿会保留。此操作会产生审校费用。" />
        <p>版本 {{ draftEditor.revisionNumber }} · 审核 {{ label(draftEditor.auditStatus) }} · 质量 {{ draftEditor.qualityScore ?? '—' }}</p>
        <p v-if="draftEditor.sourceUrls?.length">本版来源：<template v-for="(url, index) in draftEditor.sourceUrls" :key="url"><a v-if="safeSourceUrl(url)" :href="url" target="_blank" rel="noopener noreferrer">来源 {{ Number(index) + 1 }}</a><span v-if="Number(index) < draftEditor.sourceUrls.length - 1"> · </span></template></p>
        <el-form label-position="top">
          <el-form-item label="标题"><el-input v-model="draftEdit.title" maxlength="200" show-word-limit /></el-form-item>
          <el-form-item label="摘要"><el-input v-model="draftEdit.summary" type="textarea" :rows="3" maxlength="500" show-word-limit /></el-form-item>
          <el-form-item label="正文"><el-input v-model="draftEdit.body" type="textarea" :rows="16" maxlength="20000" show-word-limit /></el-form-item>
        </el-form>
      </template>
      <template #footer><el-button @click="draftEditorVisible = false">关闭</el-button><el-button v-if="draftEditor?.canEdit && access.can('wechat.write') && access.can('wechat.publish')" type="primary" :loading="draftSaving" :disabled="!draftEdit.title.trim() || !draftEdit.body.trim()" @click="saveDraftRevision">确认修改并重新审核</el-button></template>
    </el-drawer>
    <WechatArticleDrawer v-model="detailVisible" :run="selectedRun" :initial-tab="detailTab" @updated="load" />
  </section>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { Button as TButton } from 'tdesign-vue-next'
import WechatArticleDrawer from './WechatArticleDrawer.vue'
import { runGroup, runTitle, wechatBusyStatuses } from './workspacePresentation'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { articleUrl, workspaceFailure } from './workspacePresentation'
import { formatAutomationFailure } from '@/utils/automationFailure'
import WechatContentDirectionPicker from './WechatContentDirectionPicker.vue'
const access = useAuthStore()
import { runWechatAutomationPlanOnce, checkWechatNewsSource, getWechatAutomation, getWechatNewsSources, getWechatAutomationResumeOptions, resumeWechatAutomationRun, getWechatDraftEditor, reviseWechatDraft, saveWechatAutomationPlan, setWechatAutomationEnabled } from '@/api/wechatAutomation'
const props = withDefaults(defineProps<{ accounts: any[]; workflows: any[]; view?: 'all' | 'plans' | 'articles' }>(), { view: 'all' })
const emit = defineEmits<{ login: [planId: string]; updated: [state: any] }>()
const state = ref<any>(null)
const detailVisible = ref(false), selectedRun = ref<any>(null), detailTab = ref('article')
const runSearch = ref(''), runFilter = ref('all'), submittingId = ref('')
const filters = [{ value: 'all', label: '全部' }, { value: 'draft', label: '待发表' }, { value: 'progress', label: '处理中' }, { value: 'attention', label: '需处理' }, { value: 'published', label: '已发表' }]
const countFor = (filter: string) => (state.value?.runs || []).filter((run: any) => filter === 'all' || runGroup(run) === filter).length
const accountForRun = (run: any) => accountName(state.value?.plans.find((plan: any) => plan.planId === run.planId)?.settings.accountId || '')
const filteredRuns = computed(() => (state.value?.runs || []).filter((run: any) => (runFilter.value === 'all' || runGroup(run) === runFilter.value) && `${runTitle(run)} ${accountForRun(run)}`.toLowerCase().includes(runSearch.value.trim().toLowerCase())))
const workflowName = (id: string) => props.workflows.find(w => w.workflowId === id)?.name || '公众号内容计划'
function openDetail(run: any, tab: string) { selectedRun.value = run; detailTab.value = tab; detailVisible.value = true }
let timer: ReturnType<typeof setInterval> | undefined
let disposed = false
watch(state, value => { if (value) emit('updated', value) })
const canRun = (plan: any) => plan.status === 'active' && plan.settings?.deliveryMode === 'draft_only' && new Date(plan.authorizationExpiresAt || 0).getTime() > Date.now() && !(state.value?.runs || []).some((run: any) => run.planId === plan.planId && wechatBusyStatuses.has(run.status))
async function runOnce(plan: any) {
  if (!canRun(plan) || submittingId.value || !access.can('wechat.publish') || !access.can('wechat.execute')) return
  try { await ElMessageBox.confirm('将采集资讯、生成并审核文章，审核通过后投递至该公众号草稿箱。此操作会产生模型费用。', '生成并投递草稿', { confirmButtonText: '开始生成', cancelButtonText: '取消' }) } catch { return }
  submittingId.value = plan.planId
  const key = `wechat-run-once:${plan.planId}:${plan.version}`
  const requestId = sessionStorage.getItem(key) || crypto.randomUUID()
  sessionStorage.setItem(key, requestId)
  try {
    const res: any = await runWechatAutomationPlanOnce(plan.planId, { planVersion: plan.version, requestId })
    if (!res.success) throw new Error(res.message || '运行请求未完成')
    sessionStorage.removeItem(key); ElMessage.success('已开始生成，可在内容与记录中查看进度'); await load()
  } catch (e: any) { if (e?.response?.status >= 400 && e?.response?.status < 500) sessionStorage.removeItem(key); ElMessage.error(e?.response?.data?.message || e?.message || '网络错误，重试会沿用同一请求编号') }
  finally { submittingId.value = '' }
}
const checkingFeed = ref(false), feedStatus = ref('')
const feeds = ref<Array<{ feedId: string; name: string; description: string; kind: string }>>([])
const loading = ref(false), saving = ref(false), error = ref(''), busyId = ref('')
const formVisible = ref(false)
const resumeLoadingId = ref('')
const resumeRequestIds = new Map<string, string>()
const draftEditorVisible = ref(false), draftLoadingId = ref(''), draftSaving = ref(false), draftEditorError = ref('')
const draftEditor = ref<any>(null), draftEdit = reactive({ title: '', body: '', summary: '' })
const draftRequestIds = new Map<string, string>()
const defaults = () => ({ planId: undefined as string | undefined, accountId: '', workflowId: '', approvedFeedId: '', timeZone: 'Asia/Shanghai', startDate: new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Shanghai' }), endDate: new Date(Date.now() + 29 * 86400000).toLocaleDateString('en-CA', { timeZone: 'Asia/Shanghai' }), dailyPublishTime: '09:00', minimumQualityScore: 80, deliveryMode: 'draft_only', acknowledgeAutomaticPublishing: false })
const form = reactive(defaults())
function chooseContentDirection(selection: { workflowId?: string; feedId: string }) { form.workflowId = selection.workflowId || ''; form.approvedFeedId = selection.feedId }
watch(() => form.approvedFeedId, () => { feedStatus.value = '' })
const label = (status: string) => ({ active: '启用中', paused: '已暂停', running: '运行中', generated: '文章已生成', waiting: '等待发表', no_publication: '本次不发布', canceled: '已取消', pending: '等待处理', evidence_ready: '来源已留存', generating: '生成中', checking: '等待审核', ready: '等待投递时间', cover_resolving: '选择或生成封面', cover_ready: '封面已固定', submitting: '提交中', reviewing: '微信处理中', reconciling: '结果待核对，不重发', draft_delivered: '草稿已投递 · 待人工发表', failed: '失败', rejected: '审核拒绝', expired: '已过期，不补发', published: '已发布', passed: '通过' }[status] || status)
const coverLabel = (source: string) => ({ material: '已匹配素材', generated: 'AI 生成图片', default: '默认素材' }[source] || source)
const accountName = (id: string) => props.accounts.find(a => a.accountId === id)?.accountName || '公众号'
const feedName = (id: string) => feeds.value.find(feed => feed.feedId === id)?.name || id
const isArticleUrl = articleUrl
const safeSourceUrl = (value: string) => { try { return new URL(value).protocol === 'https:' } catch { return false } }
const runReason = (run: any) => ({ WECHAT_WEB_LOGIN_REQUIRED: '官方发表接口权限不足，文章已生成；需先完成网页登录身份核验及页面适配。修改计划不会恢复此草稿，已在微信手动发表的文章不要重复发表。', WECHAT_RUN_PLAN_CHANGED: '计划已修改，旧任务自动发表授权已撤销，内容保留。可按新计划重新生成；如已手动发表，请核对微信正式文章。', WECHAT_MANUAL_AUTHORIZATION_EXPIRED: '本次自动发表授权已到期，内容保留，不会补发。已手动发表的文章请以微信记录为准。', BROWSER_LOGIN_IN_PROGRESS: '正在扫码登录，文章已保留，等待登录窗口关闭。' }[run.reason as string] || workspaceFailure(run.reason) || formatAutomationFailure(run.reason))
const runLabel = (run: any) => run.status === 'draft_delivered' ? run.manualPublicationConfirmed ? '已人工确认发表' : '草稿已投递 · 待人工发表' : run.reason === 'WECHAT_WEB_LOGIN_REQUIRED' && run.deliveryMode !== 'draft_only' ? '草稿已创建 · 等待网页登录' : run.status === 'published' ? isArticleUrl(run.publishedUrl) ? '正式发表成功' : '结果待核对' : label(run.status)
const canRequestResume = (run: any) => access.can('wechat.execute') && access.can('wechat.publish') && run.triggerKind === 'manual' && run.deliveryMode === 'draft_only' && ['failed', 'rejected'].includes(run.status) && !!run.workflowRunId && !!run.planVersion
const canOfferDraftEdit = (run: any) => run.status === 'draft_delivered' && !run.manualPublicationConfirmed && run.deliveryMode === 'draft_only' && !!run.runId && access.can('wechat.write') && access.can('wechat.publish')
async function openDraftEditor(run: any) {
  if (draftLoadingId.value) return
  draftLoadingId.value = run.runId; draftEditorError.value = ''
  try {
    const res: any = await getWechatDraftEditor(run.runId)
    if (!res.success || !res.data) throw new Error(res.message || '编辑内容暂不可用')
    draftEditor.value = res.data
    Object.assign(draftEdit, { title: res.data.title || '', body: res.data.body || '', summary: res.data.summary || '' })
    draftEditorVisible.value = true
    if (!res.data.canEdit) draftEditorError.value = res.data.reason || '该文章当前不能修改；请创建新内容。'
  } catch (cause: any) { ElMessage.error(cause?.response?.data?.message || cause?.message || '读取文章编辑内容失败') }
  finally { draftLoadingId.value = '' }
}
async function saveDraftRevision() {
  const source = draftEditor.value
  if (!source?.canEdit || !draftEdit.title.trim() || !draftEdit.body.trim() || draftSaving.value) return
  try {
    await ElMessageBox.confirm('将使用当前内容版本重新审核。审核失败不会投递新草稿；审核通过后会生成新草稿，旧文章和旧草稿保留。此操作会产生审校费用。', '确认修改并重新审核', { type: 'warning', confirmButtonText: '确认并提交审核', cancelButtonText: '继续编辑' })
  } catch { return }
  draftSaving.value = true
  const title = draftEdit.title.trim()
  const requestKey = `wechat-revise:${encodeURIComponent(JSON.stringify([source.runId, source.contentHash, title, draftEdit.body, draftEdit.summary]))}`
  const requestId = draftRequestIds.get(requestKey) || sessionStorage.getItem(requestKey) || crypto.randomUUID()
  draftRequestIds.set(requestKey, requestId); sessionStorage.setItem(requestKey, requestId)
  try {
    const res: any = await reviseWechatDraft(source.runId, { planVersion: source.planVersion, requestId, sourceContentHash: source.contentHash, title, body: draftEdit.body, summary: draftEdit.summary, acknowledgeReviewAndDraftDelivery: true })
    if (!res.success) {
      if (res.status >= 400 && res.status < 500) { draftRequestIds.delete(requestKey); sessionStorage.removeItem(requestKey) }
      draftEditorError.value = res.message || '提交新版本失败，请检查运行状态'
      return
    }
    draftRequestIds.delete(requestKey); sessionStorage.removeItem(requestKey); draftEditorVisible.value = false; ElMessage.success('已提交新版本审核，原草稿保留')
    await load()
  } catch (cause: any) {
    const status = Number(cause?.response?.status)
    if (status >= 400 && status < 500) { draftRequestIds.delete(requestKey); sessionStorage.removeItem(requestKey) }
    draftEditorError.value = cause?.response?.data?.message || '网络错误；重试会沿用当前请求编号'
  } finally { draftSaving.value = false }
}
async function resumeRun(run: any) {
  if (resumeLoadingId.value || !canRequestResume(run)) return
  resumeLoadingId.value = run.runId
  const key = `wechat-resume:${run.runId}:${run.planVersion}`
  let requestId = resumeRequestIds.get(run.runId) || sessionStorage.getItem(key)
  try {
    const optionsRes: any = await getWechatAutomationResumeOptions(run.runId)
    const options = optionsRes.data
    if (!optionsRes.success || !options?.canResume) {
      ElMessage.warning(options?.reason || optionsRes.message || '该运行当前不能安全续跑')
      resumeRequestIds.delete(run.runId); sessionStorage.removeItem(key)
      return
    }
    const expiryNotice = options.requiresAuthorization
      ? '继续将复用已完成步骤，并授权本次运行最多60分钟且不跨今日；可能重新调用已明确失败的阶段，仍受现有预算限制。'
      : '继续将复用已完成步骤，并从明确失败的阶段继续。'
    try {
      await ElMessageBox.confirm(`${options.reason || '该运行符合安全续跑条件。'}\n\n${expiryNotice}`, '确认从失败步骤继续', { type: 'warning', confirmButtonText: '确认继续', cancelButtonText: '取消' })
    } catch { return }
    requestId ||= crypto.randomUUID()
    resumeRequestIds.set(run.runId, requestId); sessionStorage.setItem(key, requestId)
    const res: any = await resumeWechatAutomationRun(run.runId, { planVersion: run.planVersion, requestId, acknowledgeResume: true })
    if (!res.success) {
      if (res.status === 409) { resumeRequestIds.delete(run.runId); sessionStorage.removeItem(key) }
      ElMessage.error(res.message || '续跑未能启动')
      await load()
      return
    }
    resumeRequestIds.delete(run.runId); sessionStorage.removeItem(key)
    ElMessage.success('已从失败步骤继续，已完成的步骤会复用')
    await load()
  } catch (cause: any) {
    const status = Number(cause?.response?.status)
    const message = cause?.response?.data?.message || cause?.response?.data?.error?.message
    if (status >= 400 && status < 500) { resumeRequestIds.delete(run.runId); sessionStorage.removeItem(key) }
    ElMessage.error(message || '网络错误；重试会沿用当前请求编号')
  } finally { resumeLoadingId.value = '' }
}
async function load() {
  loading.value = true; error.value = ''
  try { const res: any = await getWechatAutomation(); if (!res.success) throw new Error(); if (!disposed) state.value = res.data }
  catch { error.value = '草稿投递计划服务暂不可用，请稍后刷新；当前页面不代表计划已启用。'; state.value = null }
  finally { loading.value = false }
}
async function loadFeeds() {
  try {
    const res: any = await getWechatNewsSources()
    feeds.value = res.success && Array.isArray(res.data) ? res.data : []
  } catch { feeds.value = [] }
}
async function checkFeed() {
  checkingFeed.value = true; feedStatus.value = ''
  try {
    const res: any = await checkWechatNewsSource(form.approvedFeedId)
    if (!res.success) throw new Error(res.message || '新闻源暂不可用')
    const count = JSON.parse(res.data.inputJson).sources?.length || 0
    const unavailable = (res.data.availability || []).filter((x: any) => x.status !== 'available')
    feedStatus.value = `已获取 ${count} 条有效来源` + (unavailable.length ? `；以下源未提供有效条目：${unavailable.map((x: any) => x.feedId + ' ' + x.code).join('、')}` : '')
  } catch (cause: any) { feedStatus.value = cause?.message || '来源检测失败' }
  finally { checkingFeed.value = false }
}
function reset() { Object.assign(form, defaults()) }
function openCreate() { reset(); form.accountId = props.accounts[0]?.accountId || ''; form.workflowId = props.workflows[0]?.workflowId || ''; form.approvedFeedId = feeds.value.find(feed => feed.feedId === 'ai-china')?.feedId || feeds.value[0]?.feedId || ''; feedStatus.value = ''; formVisible.value = true }
function edit(plan: any) { Object.assign(form, plan.settings, { planId: plan.planId, deliveryMode: 'draft_only', acknowledgeAutomaticPublishing: false }); feedStatus.value = ''; formVisible.value = true }
async function save() {
  if (saving.value) return
  if (!form.accountId || !form.workflowId || !feeds.value.some(feed => feed.feedId === form.approvedFeedId) || !form.startDate || !form.endDate || !form.acknowledgeAutomaticPublishing) return ElMessage.warning('请完整填写计划、选择可用新闻源并确认草稿投递范围')
  saving.value = true
  try { const res: any = await saveWechatAutomationPlan({ ...form }); if (res.success) { ElMessage.success('已保存为暂停计划'); reset(); formVisible.value = false; await load() } }
  finally { saving.value = false }
}
async function toggle(plan: any) {
  busyId.value = plan.planId
  try { const res: any = await setWechatAutomationEnabled(plan.planId, plan.status !== 'active'); if (res.success) await load() }
  finally { busyId.value = '' }
}
onMounted(() => { load(); loadFeeds(); timer = setInterval(() => { if (!loading.value && state.value?.runs.some((run: any) => wechatBusyStatuses.has(run.status))) load() }, 10000) })
onBeforeUnmount(() => { disposed = true; if (timer) clearInterval(timer) })
defineExpose({ openCreate, load })
</script>
<style scoped>
.panel-heading,.plan-row { display:flex; gap:12px; align-items:center; flex-wrap:wrap; }
.panel-heading { justify-content:space-between; }.plan-row { border-top:1px solid #e5e7eb; padding:12px 0; }
.plan-fields { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; }
.workflow-choice { display:flex; gap:8px; width:100%; flex-wrap:wrap; }
</style>
