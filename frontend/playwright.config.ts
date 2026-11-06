import { defineConfig, devices } from '@playwright/test'

const baseURL = process.env.E2E_BASE_URL ?? 'https://staging.example.com'
const username = process.env.E2E_BASIC_USER ?? 'staging'
const password = process.env.E2E_BASIC_PASSWORD

export default defineConfig({
  testDir: './e2e/tests',
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: 'list',
  use: {
    ...devices['Desktop Chrome'],
    baseURL,
    ignoreHTTPSErrors: true,
    httpCredentials: password ? { username, password } : undefined,
    launchOptions: {
      args: process.env.E2E_MAP_HOST_TO_LOCAL === '1'
        ? [`--host-resolver-rules=MAP ${new URL(baseURL).hostname} 127.0.0.1`]
        : [],
    },
    trace: 'retain-on-failure',
  },
})
