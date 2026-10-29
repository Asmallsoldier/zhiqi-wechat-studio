import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import {loadProduct} from '@/product'
const router = createRouter({ history:createWebHistory(), routes:[
 {path:'/',redirect:'/studio/wechat'},
 {path:'/login',component:()=>import('@/views/admin/Login.vue'),meta:{public:true}},
 {path:'/studio',component:()=>import('@/layouts/StudioLayout.vue'),meta:{requiresAuth:true},children:[
  {path:'',redirect:'/studio/wechat'},
  {path:'profile',component:()=>import('@/views/admin/Profile.vue'),meta:{title:'个人设置'}},
  ...['','/articles','/plans','/accounts'].map((suffix)=>({path:'wechat'+suffix,component:()=>import('@/views/admin/WechatEntry.vue'),meta:{title:'公众号工作台',dedicatedHeading:true,permission:'wechat.read'}})),
  {path:'research',component:()=>import('@/views/research/ResearchWorkbench.vue'),meta:{title:'数码选购研究',dedicatedHeading:true,permission:'wechat.read'}},
 ]},
 {path:'/:pathMatch(.*)*',redirect:'/studio/wechat'},
]})
router.beforeEach(async to=>{
 await loadProduct()
 if(to.meta.public)return true
 const auth=useAuthStore()
 if(!auth.accessToken)return {path:'/login',query:{redirect:to.fullPath}}
 if(!auth.profileLoaded){try{await auth.loadProfile()}catch{auth.clearAuth();return '/login'}}
 if(auth.mustChangePassword && to.path!='/studio/profile')return '/studio/profile'
 if(to.meta.permission && !auth.can(String(to.meta.permission)))return '/studio/profile'
 return true
})
router.afterEach(to=>document.title=`${to.meta.title||'公众号工作台'} · 智启图文`)
export default router
