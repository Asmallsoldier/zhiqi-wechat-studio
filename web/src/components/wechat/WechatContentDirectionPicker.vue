<template>
  <div class="direction-picker">
    <el-alert v-if="error" :title="error" type="warning" :closable="false" />
    <el-form-item label="题材方向（可在账号定位中自定义栏目、读者与关键词）">
      <el-select v-model="selected" placeholder="选择方向查看模板与批准来源" clearable @change="chooseDirection">
        <el-option v-for="direction in directions" :key="direction.code" :label="direction.name" :value="direction.code" />
      </el-select>
    </el-form-item>
    <template v-if="active">
      <p>{{ active.positioning }}</p><small>{{ active.sourceGuidance }}</small>
      <el-alert v-if="!active.approvedFeedIds.length" title="此方向尚无批准来源。请管理员添加真实 RSS/Atom 订阅并设置方向，检测通过后再选择。" type="warning" :closable="false" />
      <el-form-item v-else label="本方向已批准来源">
        <el-select v-model="selectedFeed" placeholder="选择资讯来源" @change="chooseFeed">
          <el-option v-for="feedId in active.approvedFeedIds" :key="feedId" :value="feedId" :label="feeds.find(feed => feed.feedId === feedId)?.name || feedId" />
        </el-select>
      </el-form-item>
      <p v-if="!workflowFor(active.workflowCode)">模板尚未加载；请刷新工作流列表或由管理员初始化公众号模板。</p>
      <p v-if="selectedFeed && feeds.find(f => f.feedId === selectedFeed)?.sourceNames?.length" class="wx-source-members">实际采集：{{ feeds.find(f => f.feedId === selectedFeed)?.sourceNames?.join('、') }}。会显示失败来源，只使用成功采集且未过期的资料。</p>
      <details v-if="active.sourceSuggestions?.length"><summary>更多来源配置</summary>
        <p v-for="source in active.sourceSuggestions || []" :key="source.url"><a :href="source.url" target="_blank" rel="noopener noreferrer">{{ source.name }}</a>（待管理员批准）<br />{{ source.note }}<br />Url={{ source.url }}<br />AllowedArticleHosts={{ source.allowedArticleHosts.join(', ') }}</p><p>管理员在 WechatNews:Feeds 下添加来源标识，设置 Enabled=true、Url 为公开 HTTPS RSS/Atom 地址、AllowedArticleHosts 为原文域名列表、Direction={{ active.code }}。该目录只显示已启用且地址有效的来源；健康检测和72小时证据校验仍须通过。普通网页不能直接填写为订阅地址。</p><p>来源不足时停止写作；不生成假资料。保存计划后仍为暂停状态，交付草稿由负责人审核并人工发表。</p></details>
    </template>
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getWechatContentDirections } from '@/api/wechatAutomation'
const props = defineProps<{ workflows: any[]; feeds: Array<{ feedId: string; name: string; sourceNames?: string[]; sourceCount?: number }> }>()
const emit = defineEmits<{ choose: [selection: { workflowId?: string; feedId: string }] }>()
const directions = ref<any[]>([]), selected = ref(''), selectedFeed = ref(''), error = ref('')
const active = computed(() => directions.value.find(direction => direction.code === selected.value))
const workflowFor = (code: string) => props.workflows.find(workflow => workflow.workflowCode === code && workflow.workflowType === 'wechat_operations')
function chooseDirection() {
  selectedFeed.value = ''
  if (active.value) emit('choose', { workflowId: workflowFor(active.value.workflowCode)?.workflowId, feedId: '' })
}
function chooseFeed() { if (active.value?.approvedFeedIds.includes(selectedFeed.value)) emit('choose', { workflowId: workflowFor(active.value.workflowCode)?.workflowId, feedId: selectedFeed.value }) }
onMounted(async () => {
  try { const response: any = await getWechatContentDirections(); if (!response.success) throw new Error(response.message); directions.value = response.data || [] }
  catch { error.value = '题材目录暂不可用；仍可手动选择已有工作流与批准来源。' }
})
</script>
<style scoped>
.direction-picker { padding: 12px; border: 1px solid #ebeef5; border-radius: 8px; }.direction-picker p { margin: 8px 0; }.direction-picker small { color: #687782; }details { margin-top: 12px; font-size: 13px; }
</style>
