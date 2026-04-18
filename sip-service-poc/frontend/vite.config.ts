import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  base: '/',  // Базовый путь для ресурсов
  server: {
    port: 3003,
  },
  build: {
    assetsDir: 'assets',
    outDir: 'dist',
  }
})
