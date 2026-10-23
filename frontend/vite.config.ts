import path from 'path';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// @shared/widgets resolves to the sibling shared checkout
// (symlink/copy it next to this repo, or adjust the path).
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@shared/widgets': path.resolve(__dirname, '../../shared-canonical-services/shared/widgets/react'),
    },
  },
  server: {
    port: 24581,
    fs: {
      allow: [path.resolve(__dirname), path.resolve(__dirname, '../../shared-canonical-services')],
    },
    proxy: {
      '/api': {
        target: process.env.VITE_PROXY_TARGET || 'http://localhost:8163',
        changeOrigin: true,
      },
    },
  },
  build: { outDir: 'dist', sourcemap: false },
});
