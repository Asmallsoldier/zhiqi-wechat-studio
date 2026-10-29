/// <reference types="vitest" />
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import { resolve } from 'path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd())
  const apiBase = env.VITE_API_BASE ?? 'http://localhost:5000/api/v1'
  const backendOrigin = apiBase.replace('/api/v1', '')

  return {
    plugins: [
      vue(),
      Components({
        resolvers: [ElementPlusResolver({ importStyle: mode === 'test' ? false : 'css' })],
        dts: false,
      }),
    ],
    build: {
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (!id.includes('node_modules')) return undefined
            if (id.includes('echarts') || id.includes('zrender') || id.includes('vue-echarts')) return 'charts'
            if (id.includes('element-plus') || id.includes('@element-plus')) return 'element-plus'
            if (id.includes('@microsoft/signalr')) return 'signalr'
            if (id.includes('vue') || id.includes('pinia')) return 'vue-runtime'
            if (id.includes('axios')) return 'http-client'
            return 'vendor'
          },
        },
      },
    },
    resolve: {
      alias: {
        '@': resolve(import.meta.dirname, 'src'),
      },
    },
    server: {
      port: 3000,
      proxy: {
        '/api': {
          target: backendOrigin || 'http://localhost:5000',
          changeOrigin: true,
        },
        '/hubs': {
          target: backendOrigin || 'http://localhost:5000',
          changeOrigin: true,
          ws: true,
        },
      },
    },
    test: {
      globals: true,
      environment: 'jsdom',
      include: ['src/**/*.test.ts'],
      setupFiles: ['src/test/setup.ts'],
      coverage: {
        provider: 'v8',
        reporter: ['text', 'html', 'lcov'],
        include: ['src/**/*.{ts,vue}'],
        exclude: [
          'src/test/**',
          'src/main.ts',
          'src/env.d.ts',
          '**/*.d.ts',
        ],
        thresholds: {
          lines: 7,
          functions: 2,
          statements: 6,
          branches: 1,
        },
      },
    },
  }
})
