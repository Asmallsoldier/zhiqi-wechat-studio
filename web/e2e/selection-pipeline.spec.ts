import {test,expect} from '@playwright/test'
const accountId='00000000-0000-4000-8000-000000000001'
async function setup(page:any,options:{uncertain?:boolean;blocked?:boolean}={}){
 await page.addInitScript(()=>sessionStorage.setItem('zhiqi-auth',JSON.stringify({accessToken:'fixture',refreshToken:'',userId:'operator',role:'wechat_operator',username:'operator'})))
 const posts:any[]=[],runs:any[]=[]
 await page.route('**/api/v1/**',async(route:any)=>{
  const req=route.request(),path=new URL(req.url()).pathname
  if(path.endsWith('/selection-runs')&&req.method()==='POST'){
   const body=req.postDataJSON();posts.push(body)
   if(options.uncertain&&posts.length===1)return route.abort('failed')
   runs.splice(0,runs.length,{id:'run-fixture',account_id:accountId,title:body.title,delivery_mode:body.delivery_mode,status:'publishing',stage:'reconcile',sample_count:6,has_submit_intent:true,created_at:'2026-10-23T03:30:00Z',message:'微信发布处理中，等待最终回执。',receipt:{publishId:'test-publish-id'}})
   return route.fulfill({json:{success:true,data:runs[0]}})
  }
  if(path.endsWith('/accounts'))return route.fulfill({json:{success:true,data:[{accountId,accountName:'测试公众号'}]}})
  if(path.includes('/publication-capabilities/'))return route.fulfill({status:409,json:{success:false,code:'PUBLICATION_CONTRACT_UNAVAILABLE',message:'共享服务尚未接入当前研究发表契约。'}})
  const data=path.endsWith('/auth/me')?{userId:'operator',username:'operator',status:'active',role:'wechat_operator',permissions:['wechat.read','wechat.write','wechat.execute']}:
   path.endsWith('/capabilities')?{ai_configured:true,xianyu_mode:'public_page'}:
   path.endsWith('/selection-runs')?runs:
   path.endsWith('/listings')?Array.from({length:6},(_,i)=>({id:`00000000-0000-4000-8000-${String(i+10).padStart(12,'0')}`,title:'测试手机',model:'型号A',variant:'256GB',price:1000,shipping:0,condition:'good',battery_health:90,url:'https://www.goofish.com/item?id=test',observed_at:'2026-10-23T03:00:00Z'})):[]
  return route.fulfill({json:{success:true,data}})
 })
 await page.goto('/studio/research')
 await page.getByRole('button',{name:'选品到公众号',exact:true}).click()
 return {posts,runs}
}
test('formal publication requires authority and remains processing until final receipt',async({page})=>{
 const {posts}=await setup(page)
 await page.getByLabel('交付方式',{exact:true}).selectOption('publish')
 await expect(page.getByRole('button',{name:'开始选品与投递',exact:true})).toBeDisabled()
 await page.getByRole('checkbox').check()
 await page.getByRole('button',{name:'开始选品与投递',exact:true}).click()
 await expect(page.locator('.run-card')).toContainText('微信处理中')
 await expect(page.getByRole('link',{name:'查看正式文章 ↗'})).toHaveCount(0)
 await expect(page.getByRole('button',{name:'取消任务',exact:true})).toHaveCount(0)
 expect(posts[0].acknowledge_automatic_publishing).toBe(true)
 expect(posts[0].listing_ids).toHaveLength(6)
 await page.setViewportSize({width:390,height:844})
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
})
test('unknown create result reuses the identical request even after reload',async({page})=>{
 const {posts}=await setup(page,{uncertain:true})
 await page.getByRole('button',{name:'开始选品与投递',exact:true}).click()
 await expect(page.getByRole('button',{name:'查询并重试原请求',exact:true})).toBeVisible()
 await page.reload();await page.getByRole('button',{name:'选品到公众号',exact:true}).click()
 await page.getByRole('button',{name:'查询并重试原请求',exact:true}).click()
 await expect(page.locator('.run-card')).toBeVisible()
 expect(posts[1]).toEqual(posts[0])
})
test('missing shared capability is shown as an actionable blocker',async({page})=>{
 await setup(page)
 await page.getByRole('button',{name:'检查发表能力',exact:true}).click()
 await expect(page.locator('.selection-panel [role="alert"]')).toContainText('共享服务尚未接入')
})
test('unconfigured collection is explained before starting a paid writing task',async({page})=>{
 await setup(page)
 await page.getByLabel('商品来源',{exact:true}).selectOption('query')
 await expect(page.locator('.selection-panel .callout')).toContainText('当前未配置商品数据接口')
 await expect(page.getByRole('button',{name:'开始选品与投递',exact:true})).toBeDisabled()
})
