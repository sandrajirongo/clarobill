import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      // Mirror tsconfig.json's "paths" so vitest can resolve the workspace
      // package without requiring a build step. Next.js + tsc honor tsconfig
      // paths natively; vitest does not.
      '@clarobill/shared': path.resolve(__dirname, '../../packages/shared/src/index.ts'),
    },
  },
});
