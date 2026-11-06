/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv, type Plugin } from 'vite'

/**
 * Strict Content-Security-Policy for the production build (AUDIT_REPORT F-26). Not applied to the dev
 * server, whose hot-reload client needs inline scripts. No inline scripts are allowed; images only from
 * this origin (markdown images in answers are not rendered at all, F-10). The hosting server should also
 * send this policy plus `frame-ancestors 'none'` as a header (meta tags cannot set frame-ancestors).
 *
 * The API is same-origin ("/api", see src/services/apiBase.ts) unless VITE_API_BASE_URL names another
 * origin, which is then the only extra origin allowed in connect-src.
 */
const contentSecurityPolicy = (apiBaseUrl?: string): Plugin => {
  const apiOrigin = apiBaseUrl && /^https?:\/\//.test(apiBaseUrl) ? new URL(apiBaseUrl).origin : ''
  const policy = [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data: blob:",
    `connect-src 'self'${apiOrigin ? ` ${apiOrigin}` : ''}`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
  ].join('; ')
  return {
    name: 'content-security-policy',
    apply: 'build',
    transformIndexHtml: () => [
      { tag: 'meta', attrs: { 'http-equiv': 'Content-Security-Policy', content: policy }, injectTo: 'head-prepend' },
    ],
  }
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  plugins: [react(), contentSecurityPolicy(loadEnv(mode, process.cwd(), 'VITE_').VITE_API_BASE_URL)],
  // The app calls the same-origin path /api; in development (and `npm run preview`) Vite forwards it to
  // the backend. Override the target with VITE_DEV_API_PROXY_TARGET when the backend is elsewhere.
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: loadEnv(mode, process.cwd(), 'VITE_').VITE_DEV_API_PROXY_TARGET || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  // Tests run with the build defaults, whatever a developer put in frontend/.env.local (for example
  // VITE_REGISTRATION_ENABLED=true to see the Sign up button).
  test: { env: { VITE_REGISTRATION_ENABLED: 'false' } },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (id.includes('node_modules')) {
            if (id.includes('react-markdown') || id.includes('remark-gfm') || id.includes('micromark') || id.includes('mdast') || id.includes('unified')) {
              return 'vendor-markdown';
            }
            if (id.includes('framer-motion')) {
              return 'vendor-motion';
            }
            if (id.includes('lucide-react')) {
              return 'vendor-icons';
            }
            if (id.includes('react-router-dom') || id.includes('react-dom') || id.includes('/react/')) {
              return 'vendor-react';
            }
          }
        },
      },
    },
  },
}))
