import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'

// The SPA's CSP: whoever hosts dist/ serves this page, so the policy travels inside it.
// Build only: the dev server needs Vite's inline HMR scripts. frame-ancestors cannot go in a <meta>;
// the host must send it as a header.
function contentSecurityPolicy() {
  let apiOrigin = '';
  return {
    name: 'genomia-csp',
    apply: 'build',
    configResolved(config) {
      try {
        apiOrigin = new URL(config.env.VITE_API_BASE_URL).origin;
      } catch {
        // Relative '/api' (the default): the API is same-origin and 'self' covers it.
      }
    },
    transformIndexHtml() {
      const policy = {
        'default-src': ["'self'"],
        'script-src': ["'self'", 'https://accounts.google.com/gsi/client'],
        // React and GSAP set styles from JS (allowed); 'unsafe-inline' covers the <style> tags Google Sign-In injects.
        'style-src': ["'self'", "'unsafe-inline'", 'https://fonts.googleapis.com', 'https://accounts.google.com/gsi/style'],
        'font-src': ["'self'", 'https://fonts.gstatic.com'],
        'img-src': ["'self'", 'data:', 'blob:', 'https://flagcdn.com'],
        'connect-src': ["'self'", apiOrigin, 'https://cdn.jsdelivr.net', 'https://accounts.google.com/gsi/'],
        'frame-src': ['https://accounts.google.com/gsi/'],
        'object-src': ["'none'"],
        'base-uri': ["'self'"],
        'form-action': ["'self'"],
      };
      const content = Object.entries(policy)
        .map(([directive, sources]) => [directive, ...sources.filter(Boolean)].join(' '))
        .join('; ');
      return [{ tag: 'meta', attrs: { 'http-equiv': 'Content-Security-Policy', content }, injectTo: 'head-prepend' }];
    },
  };
}

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    contentSecurityPolicy(),
  ],
  css: {
    // Keep the frontend on Tailwind v4 instead of inheriting the root app's v3 PostCSS config.
    postcss: {
      plugins: [],
    },
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  base: '/',
  publicDir: 'public',
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    copyPublicDir: true,
    cssCodeSplit: false,
    rollupOptions: {
      output: {
        assetFileNames: 'assets/[name]-[hash][extname]'
      }
    }
  },
  server: {
    fs: {
      allow: ['..', '.']
    },
    // Proxy de dev: same-origin hacia el backend para que la cookie HttpOnly funcione.
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
  },
  })
