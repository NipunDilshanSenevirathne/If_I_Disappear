import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The built app is served by the FastAPI backend from backend/static, on one origin.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../backend/static',
    emptyOutDir: true,
    sourcemap: false,
    chunkSizeWarningLimit: 900,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8080',
      '/webhooks': 'http://127.0.0.1:8080',
    },
  },
});
