<template>
  <el-drawer class="wx-overlay" v-model="visible" title="文章与投递详情" size="800px" :close-on-click-modal="false">
    <div v-if="loading" class="wx-empty">正在加载文章和投递记录…</div>
    <el-alert v-else-if="error" :title="error" type="error" :closable="false" />
    <template v-else-if="detail && run">
      <div class="wx-detail-heading"><span class="wx-pill" :class="runGroup(run)">{{ run.manualPublicationConfirmed ? '已人工确认发表' : statusLabel(run.status) }}</span><h2>{{ detail.title || runTitle(run) }}</h2><p>{{ beijingTime(detail.createTime) }} · 质量评分 {{ run.qualityScore ?? '待评估' }}</p></div>
      <t-tabs v-model="tab"><t-tab-panel value="article" label="文章预览"><div v-if="detail.body" class="wx-reading"><template v-if="detail.articleBlocks?.length"><template v-for="(block, index) in detail.articleBlocks" :key="index"><figure v-if="block.kind === 'image' && safeArticleImage(block.url)" class="wx-article-figure"><img :src="block.url" :alt="block.text" loading="lazy" referrerpolicy="no-referrer" /><figcaption>{{ block.text }}</figcaption></figure><h3 v-else-if="block.kind === 'heading'">{{ block.text }}</h3><p v-else>{{ block.text }}</p></template></template><template v-else>{{ detail.body }}</template></div><div v-else class="wx-empty">文章尚未生成，先在处理记录中查看当前进度。</div></t-tab-panel><t-tab-panel value="logs" label="处理记录"><ol class="wx-timeline"><li v-for="(stage, index) in detail.stages" :key="index" :class="stage.status"><span class="wx-timeline-dot" /><div class="wx-timeline-head"><strong>{{ stage.stepName }}</strong><span>{{ statusLabel(stage.status) }}</span></div><p>{{ beijingTime(stage.finishedAt || stage.startedAt) }}<span v-if="stage.totalCost"> · ¥{{ Number(stage.totalCost).toFixed(4) }}</span></p><p v-if="stage.error" class="wx-error-text">{{ stage.error }}</p></li><li v-for="(log, index) in detail.logs" :key="`log-${index}`"><span class="wx-timeline-dot" /><div class="wx-timeline-head"><strong>{{ statusLabel(log.toStatus) }}</strong><span>{{ beijingTime(log.createTime) }}</span></div><p>{{ log.detail }}</p><small v-if="log.errorCode">{{ log.errorCode }}</small></li></ol><div v-if="!detail.stages.length && !detail.logs.length" class="wx-empty">任务等待开始，暂无处理记录。</div></t-tab-panel><t-tab-panel value="receipt" label="投递结果"><div v-if="detail.delivery" class="wx-receipt"><h3>{{ run.manualPublicationConfirmed ? '已登记人工发表结果' : run.status === 'draft_delivered' ? '文章已送达公众号草稿箱' : statusLabel(detail.delivery.status) }}</h3><p v-if="run.status === 'draft_delivered' && !run.manualPublicationConfirmed">在微信公众平台检查并发表文章，然后将正式链接登记到这里，完成本次内容记录。</p><dl><dt>草稿 Media ID</dt><dd>{{ detail.delivery.remotePostId || '尚未取得' }}</dd><dt>投递编号</dt><dd>{{ detail.delivery.deliveryId }}</dd><dt>最后更新</dt><dd>{{ beijingTime(detail.updateTime) }}</dd></dl><a v-if="articleUrl(detail.delivery.remoteUrl)" :href="detail.delivery.remoteUrl" target="_blank" rel="noopener noreferrer" class="wx-text-link">查看正式文章 ↗</a><a v-else href="https://mp.weixin.qq.com/" target="_blank" rel="noopener noreferrer" class="wx-text-link">打开微信公众平台 ↗</a><div v-if="run.status === 'draft_delivered' && !run.manualPublicationConfirmed && auth.can('wechat.publish')" class="wx-confirm"><label for="wechat-article-url">正式文章链接</label><el-input id="wechat-article-url" v-model="publishedUrl" placeholder="https://mp.weixin.qq.com/s/..." /><t-button :loading="confirming" :disabled="!articleUrl(publishedUrl)" @click="confirm">登记人工发表结果</t-button><small>登记表示你已在公众号后台发表，不会再次发送文章。</small></div></div><div v-else class="wx-empty">尚未提交到微信。文章审核通过并完成封面准备后，才会进入投递。</div></t-tab-panel></t-tabs>
    </template>
  </el-drawer>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Tabs as TTabs, TabPanel as TTabPanel, Button as TButton } from 'tdesign-vue-next'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { getWechatRunDetail, confirmWechatPublication } from '@/api/wechatWorkspace'
import { articleUrl, beijingTime, errorMessage, runGroup, runTitle, statusLabel } from './workspacePresentation'
const props = defineProps<{ modelValue: boolean; run: any; initialTab?: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; updated: [] }>()
const visible = computed({ get: () => props.modelValue, set: value => emit('update:modelValue', value) })
const auth = useAuthStore(), loading = ref(false), error = ref(''), detail = ref<any>(null), tab = ref('article'), publishedUrl = ref(''), confirming = ref(false)
const safeArticleImage = (value: string) => { try { const url = new URL(value); return url.protocol === 'https:' && !url.username && !url.password && url.port === '' && ['mmbiz.qpic.cn', 'mmbiz.qlogo.cn'].includes(url.hostname) } catch { return false } }
let generation = 0
watch(() => [props.modelValue, props.run?.runId], async () => {
  const current = ++generation
  if (!props.modelValue || !props.run?.runId) return
  tab.value = props.initialTab || 'article'; detail.value = null; error.value = ''; loading.value = true; publishedUrl.value = ''
  try { const result: any = await getWechatRunDetail(props.run.runId); if (!result.success) throw new Error(result.message); if (current === generation) detail.value = result.data }
  catch (e) { if (current === generation) error.value = errorMessage(e, '文章记录暂时无法读取') } finally { if (current === generation) loading.value = false }
})
async function confirm() {
  if (confirming.value || !articleUrl(publishedUrl.value)) return
  confirming.value = true
  try { const response: any = await confirmWechatPublication(props.run.runId, publishedUrl.value.trim()); if (!response.success) throw new Error(response.message); ElMessage.success('人工发表结果已登记'); emit('updated'); visible.value = false }
  catch (e) { ElMessage.error(errorMessage(e, '登记失败，请检查链接及投递状态')) } finally { confirming.value = false }
}
</script>
