import { createApp } from 'vue'
import { createPinia } from 'pinia'
import piniaPluginPersistedstate from 'pinia-plugin-persistedstate'
import App from './App.vue'
import router from './router'
import { setupBrowserObservability } from './utils/observability'
// Element Plus component auto-imports do not consistently include overlay styles
// across production chunks. Keep toast and confirmation overlays explicitly styled.
import 'element-plus/theme-chalk/el-message.css'
import 'element-plus/theme-chalk/el-message-box.css'

const app = createApp(App)

const pinia = createPinia()
pinia.use(piniaPluginPersistedstate)
app.use(pinia)
app.use(router)
setupBrowserObservability(router)

app.mount('#app')
