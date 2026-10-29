<template><template v-if="standalone"><StandaloneAccounts v-if="route.path.endsWith('/accounts')"/><section v-else class="standalone-home"><span class="eyebrow">ZHIQI WECHAT STUDIO</span><h1>你的独立公众号工作空间</h1><p>从资料和商品证据开始，生成原创组织的文章、资料配图，再投递到自己的公众号。</p><div class="entry-grid"><router-link to="/studio/research"><strong>资料与文章</strong><span>来源雷达、AI写作、选品分析与投递流程</span></router-link><router-link to="/studio/wechat/accounts"><strong>公众号账号</strong><span>配置自己的AppID、加密凭据及发表授权</span></router-link></div><h2>最近投递</h2><p v-if="!runs.length">还没有投递任务。先连接公众号，再从研究文章或选品页面开始。</p><article v-for="r in runs" :key="r.id"><strong>{{ r.title }}</strong><p>{{ states[r.status]||r.status }} · {{ r.message }}</p><a v-if="r.status==='published'&&link(r.receipt?.publishedUrl)" :href="r.receipt.publishedUrl" target="_blank" rel="noopener noreferrer">查看正式文章 ↗</a></article><p class="note">独立版提供单次文章和选品作业。发布开关、账号授权与最终微信回执共同决定发表结果。</p></section></template><WechatOperations v-else /></template>
<script setup lang="ts">
import {onMounted,ref} from 'vue'
import {useRoute} from 'vue-router'
import {standalone} from '@/product'
import request from '@/utils/request'
import StandaloneAccounts from '@/components/wechat/StandaloneAccounts.vue'
import WechatOperations from './WechatOperations.vue'
const route=useRoute(),runs=ref<any[]>([])
const states:Record<string,string>={published:'已正式发表',draft_delivered:'草稿已交付',blocked:'需要处理',queued:'等待执行',running:'执行中',reconciling:'查询回执',publishing:'微信处理中',rejected:'发表失败',no_selection:'没有合格选品',canceled:'已取消'}
function link(v:unknown){try{const u=new URL(String(v));return u.protocol==='https:'&&u.hostname==='mp.weixin.qq.com'&&!u.username&&!u.password}catch{return false}}
onMounted(async()=>{if(standalone.value){const r:any=await request.get('/research/selection-runs');runs.value=r.data||[]}})
</script><style scoped>.standalone-home{max-width:1100px;margin:auto;color:#34452c}.eyebrow{font-size:11px;letter-spacing:2px;color:#7c8a70}.standalone-home h1{font-size:34px;margin:20px 0}.standalone-home p{line-height:1.9;color:#718064}.entry-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:20px;margin:30px 0}.entry-grid a{display:grid;gap:15px;padding:30px;background:white;border:1px solid #dfe5d8;border-radius:14px;color:#49664a;text-decoration:none}.entry-grid span,.note{font-size:13px}.standalone-home article{background:white;padding:22px;border:1px solid #dfe5d8;border-radius:12px;margin-bottom:16px}.standalone-home a{color:#49664a}</style>
