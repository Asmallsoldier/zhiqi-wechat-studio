<template>
  <main class="wx-workspace">
    <header class="wx-hero"><div><span class="wx-kicker">WECHAT STUDIO / 公众号工作台</span><h1>{{ pageHeading }}</h1><p>{{ pageDescription }}</p></div><div class="wx-hero-actions"><t-button variant="outline" :loading="loading" @click="load">刷新工作台</t-button><t-button v-if="access.can('wechat.write') && section !== 'accounts'" @click="newPlan"><template #icon><AddIcon /></template>创建内容计划</t-button></div></header>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <nav class="wx-top-tabs" aria-label="公众号模块导航"><button v-for="item in sections" :key="item.key" :class="{ selected: section === item.key }" @click="go(item.key)"><component :is="item.icon" size="18" />{{ item.label }}</button></nav>
    <template v-if="section === 'overview'">
      <div class="wx-stats"><article><span>已接入公众号</span><strong>{{ accounts.length }}</strong><small>{{ accounts.filter(a => a.configured).length }} 个已配置凭据</small></article><article><span>待人工发表</span><strong>{{ count('draft') }}</strong><small>已送达微信草稿箱</small></article><article><span>正在处理</span><strong>{{ count('progress') }}</strong><small>采集、写作、审核与投递</small></article><article :class="{ attention: count('attention') > 0 }"><span>需要关注</span><strong>{{ count('attention') }}</strong><small>查看原因并继续处理</small></article></div>
      <div class="wx-intro"><div><span class="wx-intro-label">从选题到发表，每一步都看得见</span><h2>让好内容，持续到达读者。</h2><p>选择内容方向，准备好公众号和封面。系统完成采集、写作和审核，你在微信后台确认最终发表。</p><div class="wx-actions"><t-button variant="outline" @click="go(accounts.length ? 'plans' : 'accounts')">{{ accounts.length ? '管理我的运营计划' : '接入第一个公众号' }} ↗</t-button><span>{{ state?.plans.filter((p: any) => p.status === 'active').length || 0 }} 个计划运行中</span></div></div><ol><li><span>01</span><div><strong>连接账号</strong><small>配置凭据与默认封面</small></div></li><li><span>02</span><div><strong>创作与审核</strong><small>真实来源、有依据的文章</small></div></li><li><span>03</span><div><strong>投递与发表</strong><small>草稿送达后人工确认发表</small></div></li></ol></div>
    </template>
    <WechatAccountsWorkspace v-if="section === 'accounts'" ref="accountsWorkspace" :accounts="accounts" @updated="load" />
    <template v-else>
      <WechatAutomationPanel ref="automation" :accounts="accounts" :workflows="workflows" :view="section === 'plans' ? 'plans' : 'articles'" @updated="state = $event" />
      <details v-if="section === 'plans' && accounts.length" class="wx-editorial"><summary>内容定位与写作偏好<span>设置读者、关注方向和封面风格</span></summary><WechatEditorialProfilePanel :accounts="accounts" /></details>
    </template>
    <footer class="wx-workspace-footer"><span><LockOnIcon size="14" />账号与内容按用户隔离</span><span>草稿送达与正式发表分别记录</span></footer>
  </main>
</template>
<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button as TButton } from 'tdesign-vue-next'
import { AddIcon, AppIcon, CalendarIcon, ChatIcon, FileIcon, LockOnIcon } from 'tdesign-icons-vue-next'
import { useAuthStore } from '@/stores/auth'
import { getWechatAccounts, getWechatWorkflows } from '@/api/wechatWorkspace'
import { getWechatAutomation } from '@/api/wechatAutomation'
import WechatAutomationPanel from '@/components/wechat/WechatAutomationPanel.vue'
import WechatAccountsWorkspace from '@/components/wechat/WechatAccountsWorkspace.vue'
import WechatEditorialProfilePanel from '@/components/wechat/WechatEditorialProfilePanel.vue'
import { errorMessage, runGroup } from '@/components/wechat/workspacePresentation'
import 'tdesign-vue-next/es/style/index.css'
import '@/components/wechat/workspace.css'
const access = useAuthStore(), route = useRoute(), router = useRouter()
const accounts = ref<any[]>([]), workflows = ref<any[]>([]), state = ref<any>(null), loading = ref(false), error = ref('')
const automation = ref<InstanceType<typeof WechatAutomationPanel>>(), accountsWorkspace = ref<InstanceType<typeof WechatAccountsWorkspace>>()
const sections = [{ key: 'overview', label: '工作台', icon: AppIcon }, { key: 'articles', label: '内容与记录', icon: FileIcon }, { key: 'plans', label: '运营计划', icon: CalendarIcon }, { key: 'accounts', label: '公众号账号', icon: ChatIcon }]
const section = computed(() => { const key = route.path.startsWith('/studio/wechat/') ? route.path.split('/').pop() : String(route.query.section || 'overview'); return sections.some(x => x.key === key) ? key : 'overview' })
const pageHeading = computed(() => ({ overview: '公众号，也可以从容运营。', articles: '每一篇内容，都有清晰的进度。', plans: '用好计划，保持内容的节奏。', accounts: '连接公众号，开始你的内容运营。' }[section.value || 'overview']))
const pageDescription = computed(() => ({ overview: '从真实资讯到优质文章，在一个工作台里完成日常公众号运营。', articles: '预览文章、查看审核与投递记录，并登记正式发表结果。', plans: '为公众号设置内容方向、发布时间和审核标准。', accounts: '管理自己的公众号凭据、连接状态与封面素材。' }[section.value || 'overview']))
const count = (group: string) => (state.value?.runs || []).filter((run: any) => runGroup(run) === group).length
async function go(key: string) { if (route.path.startsWith('/studio')) await router.push(key === 'overview' ? '/studio/wechat' : `/studio/wechat/${key}`); else await router.replace({ query: { ...route.query, section: key } }) }
async function newPlan() { if (!accounts.value.length) { await go('accounts'); await nextTick(); accountsWorkspace.value?.openCreate(); return }; await go('plans'); await nextTick(); automation.value?.openCreate() }
async function load() {
  if (loading.value) return
  loading.value = true; error.value = ''
  try { const [a, w, s]: any[] = await Promise.all([getWechatAccounts(), getWechatWorkflows(), getWechatAutomation()]); for (const response of [a, w, s]) if (!response.success) throw new Error(response.message || '读取失败'); accounts.value = a.data || []; workflows.value = w.data || []; state.value = s.data }
  catch (e) { error.value = errorMessage(e, '工作台数据暂时不可用，请刷新重试') } finally { loading.value = false }
}
onMounted(load)
</script>
