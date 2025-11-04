import { defineConfig } from 'vite'
import electron from 'vite-plugin-electron/simple'

console.log('[desktop] using vite-plugin-electron/simple')

export default defineConfig({
  appType: 'custom',
  publicDir: false,
  server: { port: 5175 },
  plugins: [
    electron({
      main: {
        entry: 'src/main/index.ts',
        onstart({ startup }) {
          startup()
        },
        vite: {
          build: {
            outDir: 'dist-electron/main',
            minify: false,
            sourcemap: true,
            target: 'node20',
          },
        },
      },

      preload: {
        input: { index: 'src/preload/index.ts' },
        vite: {
          build: {
            outDir: 'dist-electron/preload',
            minify: false,
            sourcemap: true,
            target: 'node20',
          },
        },
      },
    }),
  ],
})