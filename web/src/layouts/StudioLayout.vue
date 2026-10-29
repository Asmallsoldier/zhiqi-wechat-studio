<template>
  <div class="creator-shell">
    <aside class="creator-sidebar" :class="{ open: menuOpen }">
      <router-link class="creator-brand" :to="wechatOnly ? '/studio/wechat' : '/studio'" @click="menuOpen = false"><span class="brand-symbol">智</span><span>{{ productTitle }}<small>{{ isWechatProduct ? 'WECHAT STUDIO' : 'CREATOR STUDIO' }}</small></span></router-link>
      <p class="nav-caption">{{ wechatOnly ? '你的公众号空间' : '你的创作空间' }}</p>
      <nav aria-label="创作者导航"><router-link v-for="item in navigation" :key="item.path" :to="item.path" :class="{ selected: active(item.path) }" @click="menuOpen = false"><component :is="item.icon" size="20" /><span>{{ item.label }}</span></router-link></nav>
      <div class="sidebar-footer"><div class="workspace-note"><span class="live-dot" />{{ wechatOnly ? '公众号运营工作台' : '连接真实创作流程' }}<small>{{ wechatOnly ? '从选题、草稿到正式发表' : '从灵感、制作到作品交付' }}</small></div><router-link to="/studio/profile" @click="menuOpen = false"><UserCircleIcon size="20" />个人设置</router-link><router-link v-if="!isWechatProduct && canEnterAdmin(auth)" :to="{ path: '/admin/dashboard', query: { adminWorkspace: '1' } }"><SettingIcon size="20" />管理工作台 ↗</router-link></div>
    </aside>
    <button v-if="menuOpen" class="menu-backdrop" aria-label="关闭导航" @click="menuOpen = false" />
    <div class="creator-main">
      <header class="creator-topbar"><div class="topbar-left"><t-button class="mobile-menu" variant="text" aria-label="打开导航" @click="menuOpen = !menuOpen"><MenuIcon size="22" /></t-button><span>工作空间</span><span class="breadcrumb-divider">/</span><strong>{{ route.meta.title }}</strong></div><div class="topbar-right"><router-link v-if="!isWechatProduct && auth.can('douyin.read')" to="/studio/delivery" class="delivery-shortcut"><CheckCircleIcon size="18" />交付中心</router-link><t-avatar size="34px" style="background:#eee9df;color:#59523e">{{ name.slice(0, 1) }}</t-avatar><span class="user-name">{{ name }}</span><t-button variant="text" size="small" @click="logout">退出</t-button></div></header>
      <main class="creator-content"><div v-if="!isOverview && !route.meta.dedicatedHeading" class="workspace-page-heading"><router-link :to="wechatOnly ? '/studio/wechat' : '/studio/projects'">{{ wechatOnly ? '← 公众号工作台' : '← 我的创作' }}</router-link><h1>{{ route.meta.title }}</h1><p>{{ descriptions[String(route.meta.title)] || '在这里管理内容、查看实际进度，并继续完成你的作品。' }}</p></div><div :class="{ 'creator-business': !isOverview }"><router-view :key="route.path.startsWith('/studio/wechat') ? 'wechat-workspace' : route.path" /></div></main>
      <footer class="creator-footer">{{ productTitle }} · 让灵感成为作品<span>CREATED WITH INTENTION</span></footer>
    </div>
  </div>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import { isWechatProduct, productTitle, standalone } from '@/product'
import { useRoute, useRouter } from 'vue-router'
import { Avatar as TAvatar, Button as TButton } from 'tdesign-vue-next'
import { HomeIcon, FolderIcon, ImageIcon, VideoIcon, CalendarIcon, UserCircleIcon, SettingIcon, MenuIcon, CheckCircleIcon, ChatIcon, BookOpenIcon } from 'tdesign-icons-vue-next'
import { useAuthStore } from '@/stores/auth'
import { logout as revokeSession } from '@/api'
import { canEnterAdmin, isWechatWorkspaceOnly } from '@/router/workspace'
import 'tdesign-vue-next/es/style/index.css'
import '@/views/studio/studio.css'
const route = useRoute(), router = useRouter(), auth = useAuthStore()
const menuOpen = ref(false)
const name = computed(() => auth.displayName || auth.username || '创作者')
const isOverview = computed(() => route.path === '/studio' || route.path === '/studio/projects')
const wechatOnly = computed(() => isWechatProduct || isWechatWorkspaceOnly(auth))
const navigation = computed(() => standalone.value ? [
 {path:'/studio/wechat',label:'工作台与投递',icon:HomeIcon},
 {path:'/studio/research',label:'资料与选品研究',icon:BookOpenIcon},
 {path:'/studio/wechat/accounts',label:'公众号账号',icon:ChatIcon},
] : wechatOnly.value ? [
  { path: '/studio/wechat', label: '公众号工作台', icon: HomeIcon },
  { path: '/studio/research', label: '数码选购研究', icon: BookOpenIcon },
  { path: '/studio/wechat/articles', label: '内容与记录', icon: FolderIcon },
  { path: '/studio/wechat/plans', label: '运营计划', icon: CalendarIcon },
  { path: '/studio/wechat/accounts', label: '公众号账号', icon: ChatIcon },
] : [
  { path: '/studio', label: '工作台', icon: HomeIcon },
  { path: '/studio/projects', label: '我的创作', icon: FolderIcon },
  { path: '/studio/pets', label: '萌宠剧场', icon: VideoIcon, permission: 'pet.read' },
  { path: '/studio/history', label: '史影智编', icon: VideoIcon, permission: 'history.read' },
  { path: '/studio/novels', label: '小说创作', icon: BookOpenIcon, permission: 'novels.read' },
  { path: '/studio/wechat', label: '公众号运营', icon: ChatIcon, permission: 'wechat.read' },
  { path: '/studio/assets', label: '素材与作品', icon: ImageIcon, permission: 'assets.read' },
  { path: '/studio/delivery', label: '成片交付', icon: CheckCircleIcon, permission: 'douyin.read' },
  { path: '/studio/promotion', label: '抖音推广', icon: VideoIcon, permission: 'douyin.read' },
  { path: '/studio/calendar', label: '内容日历', icon: CalendarIcon, permission: ['wechat.read', 'novels.read'] },
].filter(item => !item.permission || (Array.isArray(item.permission) ? item.permission : [item.permission]).some(p => auth.can(p))))
function active(path: string) { return path === '/studio' || path === '/studio/wechat' ? route.path === path : route.path.startsWith(path) }
async function logout() { await revokeSession().catch(() => {}); auth.clearAuth(); await router.replace('/login') }
const descriptions: Record<string, string> = { '萌宠剧场': '固定角色与世界观，编写每一集故事，逐镜审看你的萌宠短片。', '史影智编': '从史料到分镜，让有依据的历史故事走向荧幕。', '小说创作': '整理灵感、管理章节，让长篇故事持续生长。', '成片交付': '查看制作进度，审看成片，并将已确认的作品送入交付流程。', '公众号运营': '规划选题、编辑内容，管理公众号的持续创作。', '素材与作品': '你的文字、图片、声音与视频，都在这里。' }
</script>
