import {test,expect} from '@playwright/test'
test('research shows honest source limits and handles collection failure without inventing listings',async({page})=>{
 await page.addInitScript(()=>sessionStorage.setItem('zhiqi-auth',JSON.stringify({accessToken:'fixture',refreshToken:'',userId:'operator',role:'wechat_operator',username:'operator'})))
 await page.route('**/api/v1/**',async route=>{
  const path=new URL(route.request().url()).pathname
  if(path.endsWith('/research/xianyu/search'))return route.fulfill({status:409,json:{success:false,code:'XIANYU_LOGIN_OR_STRUCTURED_DATA_REQUIRED',message:'公开搜索页没有可用商品数据；请配置授权数据接口，或导入商品资料。'}})
  const data=path.endsWith('/auth/me')?{userId:'operator',username:'operator',status:'active',role:'wechat_operator',permissions:['wechat.read','wechat.write','wechat.execute']}:path.endsWith('/capabilities')?{ai_configured:false,xianyu_mode:'public_page',xianyu_note:'公开页缺少商品信息时停止，不生成虚构数据。'}:path.endsWith('/sources')?[{id:'source',name:'测试来源',status:'unavailable',detail:'SOURCE_NON_PUBLIC_ADDRESS',url:'https://example.org/feed',category:'数码',count:0}]:[]
  return route.fulfill({json:{success:true,data}})
 })
 await page.goto('/studio/research')
 await expect(page.getByRole('heading',{name:'把数码低价，变成有依据的好选题。'})).toBeVisible()
 await page.getByLabel('闲鱼搜索关键词').fill('iPhone 15 256GB')
 await page.getByRole('button',{name:'采集商品',exact:true}).click()
 await expect(page.getByRole('alert')).toContainText('没有可用商品数据')
 await expect(page.locator('.listing-card')).toHaveCount(0)
 await page.getByRole('button',{name:'来源雷达',exact:true}).click()
 await expect(page.locator('.source-card')).toContainText('暂不可用')
 await page.setViewportSize({width:390,height:844})
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
})
