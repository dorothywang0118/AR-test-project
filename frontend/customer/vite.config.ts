import { defineConfig } from 'vite';
import basicSsl from '@vitejs/plugin-basic-ssl';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  // Relative base so the same build works on GitHub Pages sub-paths and any static host.
  base: './',
  // basic-ssl gives `npm run dev` a self-signed HTTPS cert (phones need HTTPS for the camera).
  plugins: [basicSsl()],
  resolve: {
    alias: { '@shared': fileURLToPath(new URL('../../shared', import.meta.url)) },
  },
  server: { host: true, fs: { allow: ['../..'] } },
  build: { chunkSizeWarningLimit: 4000 }, // MindAR bundles TensorFlow.js (~2.5 MB)
});
