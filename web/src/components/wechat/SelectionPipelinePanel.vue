<template>
  <section class="selection-panel" aria-labelledby="selection-title">
    <header><div><span class="eyebrow">RESEARCH → WECHAT</span><h2 id="selection-title">选品到公众号</h2><p>自动比较商品、生成文章和配图，再按你选择的方式交付到公众号。</p></div><button type="button" class="secondary" :disabled="busy" @click="refresh">刷新进度</button></header>
    <p v-if="error" role="alert" class="callout error">{{ error }}</p>
    <p v-if="notice" role="status" class="callout">{{ notice }}</p>
    <form @submit.prevent="start">
      <fieldset :disabled="busy || !!pending">
        <div class="form-grid">
          <label>目标公众号<select v-model="form.account_id" required><option value="" disabled>请选择公众号</option><option v-for="account in accounts" :key="account.accountId" :value="account.accountId">{{ account.accountName }}</option></select></label>
          <label>商品来源<select v-model="form.source" aria-label="商品来源"><option value="samples">当前筛选的 {{ listings.length }} 个商品样本</option><option v-if="selectedArticleId" value="article">已选研究文章</option><option value="query">按关键词采集新商品</option></select></label>
          <label v-if="form.source==='query'">选品关键词<input v-model="form.query" minlength="2" maxlength="80" required placeholder="例如：iPhone 15 256GB"></label>
          <label>文章选题<input v-model="form.title" minlength="2" maxlength="64" required></label>
          <label>交付方式<select v-model="form.delivery_mode" aria-label="交付方式"><option value="draft_only">投递微信草稿箱</option><option value="publish">自动正式发表</option></select></label>
          <label v-if="form.source!=='article'">写作方式<select v-model="form.use_ai"><option :value="true" :disabled="!aiConfigured">AI 原创组织语言</option><option :value="false">确定性证据分析稿</option></select></label>
        </div>
        <label v-if="form.delivery_mode==='publish'" class="check"><input v-model="form.acknowledge" type="checkbox">授权本次选品通过自动校验后，向所选公众号提交正式发表并查询最终链接。</label>
      </fieldset>
      <p v-if="form.source==='query' && !sourceConfigured" class="callout">当前未配置商品数据接口。{{ sourceNote || '公开页面需要登录或没有商品结构时，采集会停止；可先导入有原链接和观察时间的真实商品资料。' }}</p>
      <p v-if="form.source==='article'" class="hint">沿用已选文章，不重新调用模型。重新校验正文与来源时效，准备封面及两张正文图后投递。</p>
      <p v-else class="hint">同配置至少 5 个近期样本、3 个卖家，有价格优势且无已识别风险才继续。样本不足会结束选题；接口权限不足会显示阻断原因。</p>
      <p v-if="pending" class="callout">上次创建结果尚未确认。重试会使用原请求编号和原配置，避免重复任务。</p>
      <div class="actions"><button :disabled="busy || !canExecute || (!pending && !valid)">{{ pending?'查询并重试原请求':'开始选品与投递' }}</button><button type="button" class="secondary" :disabled="busy || !form.account_id" @click="checkAccount">检查发表能力</button></div>
    </form>
    <div v-if="!runs.length" class="empty">还没有选品任务。可以使用已导入的真实商品，也可以接入数据接口按关键词采集。</div>
    <article v-for="run in runs" :key="run.id" class="run-card" :data-status="run.status">
      <div class="run-top"><div><span class="badge">{{ run.delivery_mode==='publish'?'正式发表':'草稿交付' }} · {{ statusLabel[run.status] || run.status }}</span><h3>{{ run.title }}</h3><small>{{ accountName(run.account_id) }} · {{ date(run.created_at) }} · {{ run.sample_count }} 个样本</small></div><a v-if="safeLink(run.receipt?.publishedUrl) && run.status==='published'" :href="run.receipt.publishedUrl" target="_blank" rel="noopener noreferrer" class="article-link">查看正式文章 ↗</a></div>
      <ol class="stage-track" aria-label="任务阶段"><li v-for="(stage,index) in steps" :key="stage.id" :class="{current:run.stage===stage.id,done:stageIndex(run.stage)>index || run.stage==='complete'}">{{ stage.label }}</li></ol>
      <p v-if="run.message" :class="['run-message',{blocked:run.status==='blocked'}]">{{ run.message }} <code v-if="run.error_code">{{ run.error_code }}</code></p>
      <p v-if="run.receipt?.draftMediaId" class="hint">草稿编号：<span class="remote-id">{{ run.receipt.draftMediaId }}</span></p>
      <p v-if="run.review?.passed" class="hint">已通过{{ (run.review.checks || []).join('、') }}等自动校验；配图为原创资料图解。</p>
      <div class="actions"><button v-if="run.article_id" type="button" class="secondary" @click="$emit('open-articles')">查看文章与依据</button><button v-if="run.status==='blocked'" type="button" :disabled="busy || !canExecute" @click="operate(run.id,'resume')">继续原任务</button><button v-if="!terminal.has(run.status) && !run.has_submit_intent" type="button" class="text-button" :disabled="busy || !canExecute" @click="operate(run.id,'cancel')">取消任务</button><span v-if="run.has_submit_intent && !terminal.has(run.status)" class="hint">已记录提交意图，后续只查询原请求。</span></div>
    </article>
  </section>
</template>
<script setup lang="ts">
import {computed,onMounted,onBeforeUnmount,reactive,ref} from 'vue'
import request from '@/utils/request'
import {useAuthStore} from '@/stores/auth'
const props=defineProps<{listings:{id:string}[];aiConfigured:boolean;sourceConfigured?:boolean;sourceNote?:string;selectedArticleId?:string}>()
defineEmits<{(event:'open-articles'):void}>()
const auth=useAuthStore(),canExecute=computed(()=>auth.can('wechat.write') && auth.can('wechat.execute'))
const accounts=ref<any[]>([]),runs=ref<any[]>([]),busy=ref(false),error=ref(''),notice=ref('')
const key=()=>`wechat-selection-pending:${auth.userId}`
const pending=ref<any>(null)
try{pending.value=JSON.parse(sessionStorage.getItem(key()) || 'null')}catch{sessionStorage.removeItem(key())}
const form=reactive({account_id:'',source:props.selectedArticleId?'article':'samples',query:'',title:'二手数码，哪些值得进一步核验？',delivery_mode:'draft_only',use_ai:props.aiConfigured,acknowledge:false})
const valid=computed(()=>!!form.account_id && (form.source==='article'?!!props.selectedArticleId:form.source==='query'?form.query.trim().length>=2:props.listings.length>0 && props.listings.length<=200) && (form.delivery_mode!=='publish'||form.acknowledge))
const terminal=new Set(['published','draft_delivered','no_selection','rejected','canceled'])
const steps=[{id:'preflight',label:'账号检查'},{id:'collect',label:'采集'},{id:'analyze',label:'选品'},{id:'write',label:'写作'},{id:'validate',label:'校验'},{id:'illustrate',label:'配图'},{id:'deliver',label:'提交'},{id:'reconcile',label:'确认结果'}]
const stageIndex=(stage:string)=>stage==='complete'?steps.length:steps.findIndex(x=>x.id===stage)
const statusLabel:Record<string,string>={queued:'等待执行',running:'执行中',blocked:'需要处理',publishing:'微信处理中',reconciling:'查询结果中',published:'已正式发表',draft_delivered:'草稿已送达',no_selection:'无合格选品',rejected:'发表失败',canceled:'已取消'}
const date=(v:string)=>new Date(v).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'})
const accountName=(id:string)=>accounts.value.find(a=>a.accountId===id)?.accountName||'公众号'
function safeLink(value:unknown){try{const u=new URL(String(value));return u.protocol==='https:'&&u.hostname==='mp.weixin.qq.com'&&!u.username&&!u.password&&(!u.port||u.port==='443')&&(u.pathname.startsWith('/s/')||u.pathname==='/s')}catch{return false}}
function uuid(){const b=crypto.getRandomValues(new Uint8Array(16));b[6]=(b[6]&15)|64;b[8]=(b[8]&63)|128;const h=Array.from(b,x=>x.toString(16).padStart(2,'0')).join('');return `${h.slice(0,8)}-${h.slice(8,12)}-${h.slice(12,16)}-${h.slice(16,20)}-${h.slice(20)}`}
function message(e:any){return e.response?.data?.message || e.response?.data?.detail?.[0]?.msg || e.message || '操作失败'}
async function refresh(){try{const r:any=await request.get('/research/selection-runs');runs.value=r.data||[]}catch(e){error.value=message(e)}}
async function start(){if(busy.value)return;busy.value=true;error.value='';notice.value='';try{
 if(!pending.value){pending.value={request_id:uuid(),account_id:form.account_id,title:form.title,article_id:form.source==='article'?props.selectedArticleId:null,query:form.source==='query'?form.query.trim():'',listing_ids:form.source==='samples'?props.listings.map(i=>i.id):[],delivery_mode:form.delivery_mode,use_ai:form.use_ai,acknowledge_automatic_publishing:form.delivery_mode==='publish'&&form.acknowledge};sessionStorage.setItem(key(),JSON.stringify(pending.value))}
 const r:any=await request.post('/research/selection-runs',pending.value)
 if(!r.success)throw Error(r.message||'创建失败')
 pending.value=null;sessionStorage.removeItem(key());notice.value='任务已保存，当前页面可查看每一步进度。';await refresh()
 }catch(e:any){if(e.response?.status>=400&&e.response?.status<500){pending.value=null;sessionStorage.removeItem(key())}error.value=message(e)}finally{busy.value=false}}
async function operate(id:string,action:string){if(busy.value)return;busy.value=true;error.value='';try{await request.post(`/research/selection-runs/${id}/${action}`);await refresh()}catch(e){error.value=message(e)}finally{busy.value=false}}
async function checkAccount(){busy.value=true;error.value='';notice.value='';try{await request.get(`/research/publication-capabilities/${form.account_id}`,{params:{mode:form.delivery_mode}});notice.value='当前账号支持所选交付方式，正式提交前会再次检查。'}catch(e){error.value=message(e)}finally{busy.value=false}}
let timer:ReturnType<typeof setInterval>|undefined
onMounted(async()=>{try{const r:any=await request.get('/wechat-workspace/accounts');accounts.value=r.data||[];if(accounts.value.length===1)form.account_id=accounts.value[0].accountId}catch(e){error.value=message(e)}await refresh();timer=setInterval(()=>{if(!busy.value&&runs.value.some(r=>!terminal.has(r.status)&&r.status!=='blocked'))void refresh()},5000)})
onBeforeUnmount(()=>{if(timer)clearInterval(timer)})
</script>
<style scoped>
.selection-panel{background:#fff;border:1px solid #dfe5d8;border-radius:14px;padding:28px;color:#29372c}.selection-panel header,.run-top{display:flex;justify-content:space-between;gap:20px;align-items:flex-start}.eyebrow{font-size:11px;letter-spacing:2px;color:#7c8a70}h2{font-size:22px;margin:10px 0}h3{font-size:18px;line-height:1.65;margin:12px 0}p{color:#75816c;line-height:1.8}button,select,input{font:inherit}button{padding:10px 15px;border:1px solid #49664a;border-radius:8px;background:#49664a;color:#fff;cursor:pointer}button:disabled{opacity:.5;cursor:not-allowed}.secondary{background:#fff;color:#49664a}.text-button{border:0;background:none;color:#7a805f}fieldset{border:0;padding:18px 0 0;margin:0}.form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}label{display:grid;gap:8px;font-size:13px;color:#617254}select,input{width:100%;box-sizing:border-box;min-width:0;padding:11px;border:1px solid #d9e1d2;border-radius:7px;background:#fff;color:#35452f}.check{display:flex;gap:10px;align-items:flex-start;margin-top:20px;line-height:1.8}.check input{width:16px;flex-shrink:0;margin-top:4px}.hint,small{font-size:12px;line-height:1.8;color:#819072}.actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.callout{padding:14px;border-radius:8px;background:#edf5e7;overflow-wrap:anywhere}.error,.blocked{background:#fff1e1;color:#8b6430}.empty{padding:32px 0;color:#819072}.run-card{border-top:1px solid #e3e8da;padding-top:25px;margin-top:30px}.badge{display:inline-block;background:#f0f4e9;color:#647a54;padding:4px 8px;font-size:12px;border-radius:5px}.stage-track{padding:0;display:flex;flex-wrap:wrap;gap:8px;list-style:none;margin:22px 0}.stage-track li{font-size:12px;padding:7px 9px;border:1px solid #e4e9dd;border-radius:6px;color:#99a18e}.stage-track li.current{background:#e8efdf;border-color:#839a71;color:#3f6339}.stage-track li.done{color:#4d7141;border-color:#cbd8c0}.run-message{padding:12px;background:#f5f7ef;border-radius:7px;overflow-wrap:anywhere}code{display:block;font-size:11px;overflow-wrap:anywhere}.remote-id{overflow-wrap:anywhere}.article-link{white-space:nowrap;color:#416c37;text-decoration:none;padding-top:10px}@media(max-width:760px){.selection-panel{padding:18px}.selection-panel header,.run-top{flex-direction:column}.form-grid{grid-template-columns:1fr}}
</style>
