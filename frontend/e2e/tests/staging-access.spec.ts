import { expect, test, request as playwrightRequest } from '@playwright/test'

test('app loads and closed registration stays closed', async ({ page }) => {
  const response = await page.goto('/')
  expect(response?.status()).toBe(200)
  await expect(page.locator('#root')).toBeAttached()

  const probeEmail = process.env.E2E_ADMIN_EMAIL
  test.skip(!probeEmail, 'Set E2E_ADMIN_EMAIL to an existing staging admin to avoid creating a test account if registration is open')
  const status = await page.evaluate(async (email) => {
    const response = await fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, name: 'E2E User', password: 'NotARealPassword123!' }),
    });
    return response.status;
  }, probeEmail);
  expect(status).toBe(403);
})

test('staging basic-auth gate rejects an unauthenticated browser', async ({ baseURL }) => {
  test.skip(process.env.E2E_EXPECT_BASIC_AUTH !== '1', 'Gate check is for the protected staging deployment')
  const anonymous = await playwrightRequest.newContext({ baseURL })
  try {
    const response = await anonymous.get('/')
    expect(response.status()).toBe(401)
  } finally {
    await anonymous.dispose()
  }
})

test('chat API streams through the local fake provider', async ({ baseURL }) => {
  test.skip(process.env.E2E_ALLOW_STUB_STREAM !== '1', 'Streaming requires the isolated fake-provider stack')
  const adminEmail = process.env.E2E_ADMIN_EMAIL
  const adminPassword = process.env.E2E_ADMIN_PASSWORD
  test.skip(!adminEmail || !adminPassword, 'Set E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD for authenticated API checks')

  const basicPassword = process.env.E2E_BASIC_PASSWORD
  const api = await playwrightRequest.newContext({
    baseURL,
    httpCredentials: basicPassword
      ? { username: process.env.E2E_BASIC_USER ?? 'staging', password: basicPassword }
      : undefined,
  })
  try {
    const login = await api.post('/api/auth/admin-login', { data: { email: adminEmail, password: adminPassword } })
    expect(login.status()).toBe(200)
    const { access_token: token } = await login.json()
    const headers = { Authorization: `Bearer ${token}` }
    const chat = await api.post('/api/chats', { headers, data: { title: 'Playwright staging smoke' } })
    expect(chat.ok()).toBeTruthy()
    const { id } = await chat.json()
    const answer = await api.post(`/api/chats/${id}/messages/stream`, {
      headers,
      data: { content: 'Explain convergent invoicing in SAP BRIM.', mode: 'sprint' },
      timeout: 45_000,
    })
    expect(answer.status()).toBe(200)
    const body = await answer.text()
    expect(body).toContain('"type": "token"')
    expect(body).toContain('"type": "done"')
    expect(body).toContain('Stub answer about SAP BRIM')
  } finally {
    await api.dispose()
  }
})
