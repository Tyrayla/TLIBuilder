import { defineConfig, configDefaults } from 'vitest/config'
export default defineConfig({
  test: {
    environment: 'node',
    // e2e/ is Playwright's, not vitest's — its specs throw if collected here.
    exclude: [...configDefaults.exclude, 'e2e/**'],
  },
})
