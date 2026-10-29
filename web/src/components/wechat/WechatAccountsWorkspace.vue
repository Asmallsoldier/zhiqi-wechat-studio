<template>
  <section class="wx-accounts">
    <div class="wx-section-head"><div><h2>我的公众号</h2><p>在这里接入账号、检查连接，并准备文章封面。</p></div><t-button v-if="auth.can('wechat.authorize')" @click="openCreate">添加公众号</t-button></div>
    <div v-if="!accounts.length" class="wx-empty"><ChatIcon size="36" /><h3>从连接第一个公众号开始</h3><p>准备公众号后台的 AppID 和 AppSecret，即可接入文章草稿投递。</p><t-button v-if="auth.can('wechat.authorize')" @click="openCreate">添加公众号</t-button></div>
    <div v-else class="wx-account-grid">
      <article v-for="account in accounts" :key="account.accountId" class="wx-account-card">
        <div class="wx-card-top"><span class="wx-account-avatar"><ChatIcon size="26" /></span><span class="wx-pill" :class="account.configured ? 'success' : 'warning'">{{ account.configured ? '凭据已配置' : '待接入' }}</span></div>
        <h3>{{ account.accountName }}</h3><p>{{ account.platformAccountId || '微信公众号' }}</p>
        <div class="wx-account-footer"><span>仅当前用户与管理员可管理</span><t-button variant="outline" size="small" @click="openSettings(account)">{{ auth.can('wechat.authorize') ? '管理账号' : '查看账号' }}</t-button></div>
      </article>
    </div>
    <div class="wx-onboarding"><span>01 <strong>接入账号</strong> 保存应用凭据</span><span>02 <strong>准备封面</strong> 同步并选择默认素材</span><span>03 <strong>开始创作</strong> 配置选题与运营计划</span></div>
    <el-dialog class="wx-overlay" v-model="createVisible" title="添加公众号" width="480px" :close-on-click-modal="false">
      <el-form label-position="top" @submit.prevent="create"><el-form-item label="公众号名称"><el-input v-model="newAccount.accountName" maxlength="128" placeholder="例如：你的行业观察" /></el-form-item><el-form-item label="公众号原始 ID（选填）"><el-input v-model="newAccount.platformAccountId" maxlength="128" placeholder="gh_ 开头的原始 ID" /></el-form-item></el-form>
      <p class="wx-muted">账号创建后，在配置面板填写 AppID 和 AppSecret。该公众号归属于当前登录用户。</p>
      <template #footer><t-button variant="text" @click="createVisible = false">取消</t-button><t-button :loading="creating" :disabled="!newAccount.accountName.trim()" @click="create">创建并配置</t-button></template>
    </el-dialog>
    <el-drawer class="wx-overlay" v-model="settingsVisible" :title="selected?.accountName || '公众号设置'" size="650px" :close-on-click-modal="false" @closed="credential.appSecret = ''">
      <el-alert v-if="settingsError" :title="settingsError" type="error" :closable="false" />
      <div v-if="settingsLoading" class="wx-empty">正在加载账号配置…</div>
      <template v-else-if="selected">
        <section class="wx-setting-section"><h3>账号信息</h3><el-form label-position="top"><el-form-item label="公众号名称"><el-input v-model="accountEdit.accountName" maxlength="128" :disabled="!canConfigure" /></el-form-item><el-form-item label="公众号原始 ID"><el-input v-model="accountEdit.platformAccountId" maxlength="128" :disabled="!canConfigure" /></el-form-item></el-form><t-button v-if="canConfigure" variant="outline" :loading="savingName" @click="saveName">保存账号信息</t-button></section>
        <section class="wx-setting-section"><div class="wx-section-head"><h3>应用凭据</h3><span class="wx-pill" :class="credentialStatus?.clientConfigured ? 'success' : 'warning'">{{ credentialStatus?.clientConfigured ? '已加密保存' : '尚未配置' }}</span></div><p class="wx-muted">在微信公众平台的开发接口管理中获取。已保存的密钥不会回显，留空可保留原值。</p>
          <el-form v-if="canConfigure" label-position="top" autocomplete="off"><el-form-item label="AppID"><el-input v-model="credential.appId" autocomplete="off" :placeholder="credentialStatus?.clientConfigured ? '留空保留已保存的 AppID' : 'wx 开头的 AppID'" /></el-form-item><el-form-item label="AppSecret"><el-input v-model="credential.appSecret" type="password" show-password autocomplete="new-password" :placeholder="credentialStatus?.clientConfigured ? '留空保留已保存的密钥' : '请输入 AppSecret'" /></el-form-item></el-form>
          <div class="wx-actions"><t-button v-if="canConfigure" :loading="savingCredential" @click="saveCredential">保存凭据</t-button><t-button v-if="canConfigure" variant="outline" :disabled="!credentialStatus?.clientConfigured" :loading="probing" @click="probe">检测连接</t-button><t-button v-if="canConfigure && credentialStatus?.clientConfigured" theme="danger" variant="text" @click="revoke">撤销授权</t-button></div>
          <el-alert v-if="probeResult" :type="probeResult.draftAccessible ? 'success' : 'warning'" :title="probeResult.draftAccessible ? '连接正常，可访问公众号草稿箱' : probeResult.errorMessage || '暂时无法访问草稿箱'" :description="probeResult.guidance" :closable="false" style="margin-top:16px" />
          <p class="wx-muted">连接检测只读取草稿权限。若提示 IP 白名单，请在公众号后台添加服务端出口 IP。</p>
        </section>
        <section class="wx-setting-section"><div class="wx-section-head"><div><h3>封面素材</h3><p>{{ materials?.syncedAt ? `上次同步 ${beijingTime(materials.syncedAt)}` : '从公众号素材库同步图片，选择一张默认封面。' }}</p></div><t-button v-if="canConfigure" variant="outline" :loading="syncing" :disabled="!credentialStatus?.clientConfigured" @click="sync">同步素材</t-button></div>
          <el-alert v-if="materialError" :title="materialError" type="warning" :closable="false" />
          <el-alert v-if="materials?.defaultMissing" title="原默认封面已不可用，请重新选择。" type="warning" :closable="false" />
          <div class="wx-material-search"><el-input v-model="search" clearable placeholder="搜索素材名称" @keyup.enter="loadMaterials(1)" @clear="loadMaterials(1)" /><t-button variant="outline" @click="loadMaterials(1)">搜索</t-button></div>
          <p v-if="!materialLoading && !materials?.items?.length" class="wx-muted">暂无素材。可先在微信公众平台上传封面图片，再点击同步。</p>
          <div class="wx-material-grid"><button v-for="item in materials?.items || []" :key="item.mediaId" class="wx-material" :class="{ selected: item.mediaId === materials?.defaultMediaId }" :disabled="!canConfigure || !!settingDefault" :aria-label="`设为默认封面：${item.name}`" @click="setDefault(item)"><img v-if="safeImage(item.previewUrl)" :src="item.previewUrl" :alt="item.name" loading="lazy" referrerpolicy="no-referrer" /><span v-else class="wx-image-placeholder"><ImageIcon size="24" /></span><strong>{{ item.name || '未命名素材' }}</strong><small>{{ item.mediaId === materials?.defaultMediaId ? '✓ 默认封面' : '选择为默认' }}</small></button></div>
          <el-pagination v-if="materials?.total > 12" small layout="prev, pager, next" :current-page="page" :page-size="12" :total="materials.total" @current-change="loadMaterials" />
        </section>
      </template>
    </el-drawer>
  </section>
</template>
<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { Button as TButton } from 'tdesign-vue-next'
import { ChatIcon, ImageIcon } from 'tdesign-icons-vue-next'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { createWechatAccount, updateWechatAccount, getWechatCredential, saveWechatCredential, probeWechatAccount, revokeWechatCredential, getWorkspaceMaterials, syncWorkspaceMaterials, setWorkspaceDefaultMaterial } from '@/api/wechatWorkspace'
import { errorMessage, beijingTime } from './workspacePresentation'
defineProps<{ accounts: any[] }>()
const emit = defineEmits<{ updated: [] }>()
const auth = useAuthStore(), canConfigure = computed(() => auth.can('wechat.authorize'))
const createVisible = ref(false), creating = ref(false), settingsVisible = ref(false), selected = ref<any>(null)
const newAccount = reactive({ requestId: '', accountName: '', platformAccountId: '' }), accountEdit = reactive({ accountName: '', platformAccountId: '' })
const credential = reactive({ appId: '', appSecret: '' }), credentialStatus = ref<any>(null), probeResult = ref<any>(null)
const settingsLoading = ref(false), settingsError = ref(''), savingName = ref(false), savingCredential = ref(false), probing = ref(false)
const materials = ref<any>(null), materialError = ref(''), materialLoading = ref(false), syncing = ref(false), settingDefault = ref(''), search = ref(''), page = ref(1)
let epoch = 0
const safeImage = (url: string) => { try { return new URL(url).protocol === 'https:' } catch { return false } }
const requireData = (response: any) => { if (!response.success) throw new Error(response.message || '请求未完成'); return response.data }
function openCreate() { Object.assign(newAccount, { requestId: crypto.randomUUID(), accountName: '', platformAccountId: '' }); createVisible.value = true }
async function create() {
  if (creating.value || !newAccount.accountName.trim()) return
  creating.value = true
  try { const data = requireData(await createWechatAccount({ ...newAccount, accountName: newAccount.accountName.trim() })); createVisible.value = false; emit('updated'); await openSettings({ ...newAccount, accountId: data.accountId }) }
  catch (e) { ElMessage.error(errorMessage(e, '添加公众号失败')) } finally { creating.value = false }
}
async function openSettings(account: any) {
  const current = ++epoch
  selected.value = account; settingsVisible.value = true; settingsLoading.value = true; settingsError.value = ''; credentialStatus.value = null; probeResult.value = null; materials.value = null; search.value = ''; materialError.value = ''
  Object.assign(credential, { appId: '', appSecret: '' }); Object.assign(accountEdit, { accountName: account.accountName, platformAccountId: account.platformAccountId || '' })
  try { const status = requireData(await getWechatCredential(account.accountId)); if (current !== epoch) return; credentialStatus.value = status; if (status?.clientConfigured) await loadMaterials(1) }
  catch (e) { if (current === epoch) settingsError.value = errorMessage(e, '账号配置加载失败') } finally { if (current === epoch) settingsLoading.value = false }
}
async function saveName() { savingName.value = true; try { requireData(await updateWechatAccount(selected.value.accountId, accountEdit)); selected.value = { ...selected.value, ...accountEdit }; emit('updated'); ElMessage.success('账号信息已保存') } catch (e) { ElMessage.error(errorMessage(e, '保存失败')) } finally { savingName.value = false } }
async function saveCredential() {
  if (savingCredential.value) return
  savingCredential.value = true
  try { credentialStatus.value = requireData(await saveWechatCredential(selected.value.accountId, credential)); credential.appSecret = ''; credential.appId = ''; probeResult.value = null; emit('updated'); ElMessage.success('凭据已加密保存'); await loadMaterials(1) }
  catch (e) { ElMessage.error(errorMessage(e, '凭据保存失败')) } finally { savingCredential.value = false }
}
async function probe() { probing.value = true; probeResult.value = null; try { probeResult.value = requireData(await probeWechatAccount(selected.value.accountId)) } catch (e) { ElMessage.error(errorMessage(e, '连接检测失败')) } finally { probing.value = false } }
async function revoke() { try { await ElMessageBox.confirm('撤销后该公众号需要重新配置凭据，原文章和投递记录保留。', '撤销公众号授权', { type: 'warning' }) } catch { return }; try { credentialStatus.value = requireData(await revokeWechatCredential(selected.value.accountId)); emit('updated'); probeResult.value = null; ElMessage.success('授权已撤销') } catch (e) { ElMessage.error(errorMessage(e, '撤销失败')) } }
async function loadMaterials(value = 1) { const current = epoch; materialLoading.value = true; materialError.value = ''; try { const data = requireData(await getWorkspaceMaterials(selected.value.accountId, value, search.value)); if (current === epoch) { materials.value = data; page.value = value } } catch (e) { if (current === epoch) materialError.value = errorMessage(e, '素材读取失败') } finally { if (current === epoch) materialLoading.value = false } }
async function sync() { if (syncing.value) return; syncing.value = true; materialError.value = ''; try { materials.value = requireData(await syncWorkspaceMaterials(selected.value.accountId)); page.value = 1; search.value = ''; ElMessage.success('公众号素材已同步') } catch (e) { materialError.value = errorMessage(e, '素材同步失败') } finally { syncing.value = false } }
async function setDefault(item: any) { if (settingDefault.value) return; settingDefault.value = item.mediaId; try { requireData(await setWorkspaceDefaultMaterial(selected.value.accountId, item.mediaId)); await loadMaterials(page.value); ElMessage.success('默认封面已设置') } catch (e) { ElMessage.error(errorMessage(e, '默认封面保存失败')) } finally { settingDefault.value = '' } }
defineExpose({ openCreate })
</script>
