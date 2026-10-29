import {defineConfig} from '@playwright/test'
export default defineConfig({testDir:'./e2e',use:{baseURL:process.env.STUDIO_E2E_ORIGIN||'http://127.0.0.1:3103'},reporter:'list'})
