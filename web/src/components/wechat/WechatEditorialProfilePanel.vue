<template>
  <el-card shadow="never" class="profile-card">
    <template #header><div class="head"><div><strong>账号运营定位</strong><p>设置只对之后的新运行生效；已运行内容保留原始版本。</p></div><el-button :loading="loading" @click="loadHealth">刷新来源健康状态</el-button></div></template>
    <div v-if="accounts.length" class="accounts">
      <article v-for="account in accounts" :key="account.accountId" class="account-row">
        <strong>{{ account.accountName }}</strong>
        <div class="readiness" v-if="coverReadiness[account.accountId]">
          <el-tag :type="coverReadiness[account.accountId].unavailable ? 'info' : coverReadiness[account.accountId].canPrepareCover ? 'success' : 'warning'">{{ coverReadiness[account.accountId].unavailable ? '状态暂不可用' : coverReadiness[account.accountId].canPrepareCover ? '封面可准备' : '封面待配置' }}</el-tag>
          <template v-if="!coverReadiness[account.accountId].unavailable">
            <span>可用素材 {{ coverReadiness[account.accountId].materialCount }} · {{ coverReadiness[account.accountId].defaultValid ? '有效默认素材可继续' : '未发现有效默认素材' }}</span>
            <small v-if="!coverReadiness[account.accountId].generationConfigured || !coverReadiness[account.accountId].priceConfigured">AI补图未完整配置时仅使用可用素材或默认封面；AI图片生成尚未验收。</small>
          </template>
          <small v-if="coverReadiness[account.accountId].reason">{{ coverReadiness[account.accountId].reason }}</small>
        </div>
        <el-button link :loading="coverLoadingId === account.accountId" @click="loadCoverReadiness(account.accountId)">检查封面就绪</el-button>
        <el-button v-if="access.can('wechat.read')" link type="primary" @click="open(account)">{{ access.can('wechat.write') ? '编辑定位与栏目' : '查看定位与栏目' }}</el-button>
      </article>
    </div>
    <el-empty v-else description="暂无公众号账号" :image-size="72" />
    <div class="sources-head"><strong>资讯来源健康</strong><el-button link :loading="loadingHealth" @click="loadHealth">刷新</el-button></div>
    <el-alert v-if="healthError" :title="healthError" type="error" :closable="false" />
    <el-empty v-if="!loadingHealth && !healthError && !health.length" description="暂无资讯来源健康记录" :image-size="60" />
    <article v-for="group in health" :key="group.feedId" class="health-group">
      <div class="feed-row">
        <strong>{{ sourceName(group.feedId) }}</strong><el-tag :type="healthType(group.status)">{{ healthLabel(group.status) }}</el-tag>
        <el-button v-if="access.can('wechat.execute')" link :loading="checkingId === group.feedId" @click="checkHealth(group.feedId)">立即检测</el-button>
      </div>
      <small>有效来源 {{ availableCount(group) }}</small>
      <div v-for="feed in group.feeds || []" :key="feed.feedId" class="health-member">
        <span>{{ feed.name || sourceName(feed.feedId) }}</span><el-tag size="small" :type="healthType(feed.status)">{{ feed.code === 'NEWS_FEED_NO_FRESH_EVIDENCE' ? '暂无新资讯' : healthLabel(feed.status) }}</el-tag><span v-if="feed.code" :title="feed.code">{{ healthReason(feed.code) }}</span><span v-if="feed.reason">{{ feed.reason }}</span>
      </div>
    </article>
    <el-drawer class="wx-overlay" v-model="visible" title="账号运营定位" size="520px" :close-on-click-modal="false">
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <el-form v-if="profile" label-position="top" class="profile-form">
        <el-form-item label="题材预设（仅填写空白项，保存后生效）"><el-select :disabled="!access.can('wechat.write')" placeholder="可选；也可直接自定义下方栏目" @change="applyDirection"><el-option v-for="direction in directions" :key="direction.code" :label="direction.name" :value="direction.code" /></el-select></el-form-item>
        <el-form-item label="账号定位"><el-input v-model="profile.positioning" :disabled="!access.can('wechat.write')" type="textarea" :rows="3" maxlength="500" show-word-limit /></el-form-item>
        <el-form-item label="目标读者"><el-input v-model="profile.audience" :disabled="!access.can('wechat.write')" type="textarea" :rows="2" maxlength="200" show-word-limit /></el-form-item>
        <el-form-item label="栏目（每行一项）"><el-input v-model="columnsText" :disabled="!access.can('wechat.write')" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="关注关键词（每行一项）"><el-input v-model="keywordsText" :disabled="!access.can('wechat.write')" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="避免主题（每行一项）"><el-input v-model="avoidText" :disabled="!access.can('wechat.write')" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="封面风格"><el-input v-model="profile.coverStyle" :disabled="!access.can('wechat.write')" maxlength="300" show-word-limit /></el-form-item>
      </el-form>
      <template #footer><el-button @click="visible = false">取消</el-button><el-button v-if="access.can('wechat.write')" type="primary" :loading="saving" @click="save">保存设置</el-button></template>
    </el-drawer>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getWechatContentDirections, getWechatEditorialProfile, saveWechatEditorialProfile, getWechatNewsSources, getWechatNewsSourceHealth, checkWechatNewsSourceHealth, getWechatAccountCoverReadiness } from '@/api/wechatAutomation'
import { useAuthStore } from '@/stores/auth'

defineProps<{ accounts: any[] }>()
const access = useAuthStore()
const visible = ref(false), loading = ref(false), saving = ref(false), loadingHealth = ref(false), checkingId = ref(''), error = ref(''), healthError = ref('')
const profile = ref<any>(null), activeAccountId = ref(''), columnsText = ref(''), keywordsText = ref(''), avoidText = ref(''), health = ref<any[]>([]), sourceCatalog = ref<any[]>([])
const coverReadiness = ref<Record<string, any>>({}), coverLoadingId = ref('')
const coverRequestVersions: Record<string, number> = {}
let healthRequestVersion = 0
let profileRequestVersion = 0
const directions = ref<any[]>([])
function applyDirection(code: string) {
  const direction = directions.value.find(item => item.code === code)
  if (!direction || !profile.value) return
  if (!profile.value.positioning?.trim()) profile.value.positioning = direction.positioning
  if (!profile.value.audience?.trim()) profile.value.audience = direction.audience
  if (!columnsText.value.trim()) columnsText.value = direction.columns.join('\n')
  if (!keywordsText.value.trim()) keywordsText.value = direction.focusKeywords.join('\n')
  if (!avoidText.value.trim()) avoidText.value = direction.avoidTopics.join('\n')
}
const lines = (value: string) => value.split('\n').map(item => item.trim()).filter(Boolean)
function open(account: any) { activeAccountId.value = account.accountId; visible.value = true; profile.value = null; health.value = []; void loadProfile(account.accountId); void loadHealth(); void loadCoverReadiness(account.accountId) }
async function loadProfile(accountId: string) {
  const version = ++profileRequestVersion
  loading.value = true; error.value = ''; profile.value = null
  try {
    const res: any = await getWechatEditorialProfile(accountId)
    if (!res.success) throw new Error(res.message || '读取账号定位失败')
    if (activeAccountId.value !== accountId || version !== profileRequestVersion) return
    profile.value = res.data; columnsText.value = (res.data.columns || []).join('\n'); keywordsText.value = (res.data.focusKeywords || []).join('\n'); avoidText.value = (res.data.avoidTopics || []).join('\n')
  } catch (cause: any) { if (activeAccountId.value === accountId && version === profileRequestVersion) { error.value = cause?.message || '账号定位暂不可用'; profile.value = null } }
  finally { if (version === profileRequestVersion) loading.value = false }
}
async function save() {
  if (!profile.value || saving.value) return
  saving.value = true
  const accountId = profile.value.accountId || activeAccountId.value
  try {
    const res: any = await saveWechatEditorialProfile(accountId, { version: profile.value.version, positioning: profile.value.positioning, audience: profile.value.audience, columns: lines(columnsText.value), focusKeywords: lines(keywordsText.value), avoidTopics: lines(avoidText.value), coverStyle: profile.value.coverStyle })
    if (!res.success) { if (activeAccountId.value === accountId) { if (res.status === 409) error.value = '设置已被其他人更新，请关闭后重新打开最新版本。'; else error.value = res.message || '保存失败' } return }
    if (activeAccountId.value === accountId) { profile.value = res.data; visible.value = false; ElMessage.success('账号运营定位已保存；只影响之后的新运行') }
  } catch (cause: any) { if (activeAccountId.value === accountId) error.value = Number(cause?.response?.status) === 409 ? '设置已被其他人更新，请关闭后重新打开最新版本。' : cause?.response?.data?.message || '保存失败' }
  finally { saving.value = false }
}
const healthLabel = (status: string) => ({ available: '可用', degraded: '部分可用', unavailable: '不可用', unchecked: '未检测' }[status] || '状态待核验')
const healthReason = (code: string) => ({ NEWS_FEED_NO_FRESH_EVIDENCE: '没有72小时内符合条件的资讯；其他可用来源仍可继续', NEWS_FEED_TIMEOUT: '来源响应超时，可稍后重试', NEWS_FEED_FETCH_FAILED: '来源暂时无法连接', NEWS_FEED_HTTP_ERROR: '来源服务器返回错误', NEWS_FEED_INVALID: '来源内容格式无法解析' }[code] || code)
const healthType = (status: string) => ({ available: 'success', degraded: 'warning', unavailable: 'danger', unchecked: 'info' }[status] || 'info') as any
function sourceName(feedId: string) { return sourceCatalog.value.find(feed => feed.feedId === feedId)?.name || ({ 'ai-china': '国内 AI 资讯合集', 'ai-official': '国际 AI 官方资讯合集' } as Record<string, string>)[feedId] || feedId }
function availableCount(group: any) { return group.validSourceCount ?? (group.feeds || []).filter((feed: any) => feed.status === 'available').length }
async function loadHealth() {
  const version = ++healthRequestVersion; checkingId.value = ''; loadingHealth.value = true; healthError.value = ''
  try {
    const [healthRes, sourceRes]: any[] = await Promise.all([getWechatNewsSourceHealth(), getWechatNewsSources().catch(() => null)])
    if (version !== healthRequestVersion) return
    if (!healthRes.success) throw new Error(healthRes.message || '读取资讯源健康状态失败')
    sourceCatalog.value = Array.isArray(sourceRes?.data) ? sourceRes.data : sourceRes?.data?.list || []
    health.value = Array.isArray(healthRes.data) ? healthRes.data : Array.isArray(healthRes.data?.list) ? healthRes.data.list : healthRes.data?.feedId ? [healthRes.data] : []
  } catch (cause: any) { if (version === healthRequestVersion) { health.value = []; healthError.value = cause?.response?.data?.message || cause?.message || '资讯源健康状态暂不可用' } }
  finally { if (version === healthRequestVersion) loadingHealth.value = false }
}
async function checkHealth(feedId: string) {
  const version = ++healthRequestVersion; checkingId.value = feedId; healthError.value = ''
  try {
    const res: any = await checkWechatNewsSourceHealth(feedId)
    if (version !== healthRequestVersion) return
    if (!res.success) throw new Error(res.message || '检测资讯来源失败')
    const checkedGroup = res.data
    if (!checkedGroup?.feedId) throw new Error('检测结果缺少合集标识')
    const groupId = checkedGroup?.feedId || feedId
    const exists = health.value.some(group => group.feedId === groupId)
    health.value = exists ? health.value.map(group => group.feedId === groupId ? checkedGroup : group) : [...health.value, checkedGroup]
  } catch (cause: any) { if (version === healthRequestVersion) healthError.value = cause?.response?.data?.message || cause?.message || '检测资讯来源失败' }
  finally { if (version === healthRequestVersion) checkingId.value = '' }
}
async function loadCoverReadiness(accountId: string) {
  const version = coverRequestVersions[accountId] = (coverRequestVersions[accountId] || 0) + 1
  coverLoadingId.value = accountId; coverReadiness.value = { ...coverReadiness.value, [accountId]: null }
  try { const res: any = await getWechatAccountCoverReadiness(accountId); if (coverRequestVersions[accountId] === version && res.success) coverReadiness.value = { ...coverReadiness.value, [accountId]: res.data } }
  catch { if (coverRequestVersions[accountId] === version) coverReadiness.value = { ...coverReadiness.value, [accountId]: { accountId, unavailable: true, reason: '封面就绪状态暂不可用，请重试' } } }
  finally { if (coverRequestVersions[accountId] === version && coverLoadingId.value === accountId) coverLoadingId.value = '' }
}
onMounted(loadHealth)
onMounted(async () => { try { const response: any = await getWechatContentDirections(); if (response.success) directions.value = response.data || [] } catch { directions.value = [] } })
</script>

<style scoped>
.profile-card { display:grid; gap:14px; }.head,.account-row,.feed-row,.sources-head { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; }.head p { margin:4px 0 0; color:#687782; font-size:13px; }.accounts { display:grid; gap:6px; }.account-row,.feed-row { border-top:1px solid #ebeef5; padding:10px 0; }.profile-form { display:grid; }
</style>
