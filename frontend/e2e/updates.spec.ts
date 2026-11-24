import { expect, test } from '@playwright/test'

import { mockShell, mockWorkspaceData } from './run-fixture'

const base = {
  current_version: '0.1.3', version: '0.1.4', page: 'https://github.com/thesaikodelik/Leadroom/releases/tag/v0.1.4',
  notes: '', progress: 0, error: '', postponed: false, installed: true, enabled: true,
}

test('an available update is downloaded and installed from the sidebar', async ({ page }) => {
  await mockShell(page)
  await mockWorkspaceData(page)
  let state = { ...base, phase: 'available' }
  const calls: string[] = []
  await page.route('**/api/v1/updates', (route) => route.fulfill({ json: state }))
  await page.route('**/api/v1/updates/download', (route) => {
    calls.push('download')
    state = { ...state, phase: 'downloading', progress: 0.42 }
    return route.fulfill({ json: state })
  })
  await page.route('**/api/v1/updates/install', (route) => {
    calls.push('install')
    return route.fulfill({ json: state })
  })

  await page.goto('/runs')
  const card = page.locator('.update-card')
  await expect(card).toContainText('Update available')
  await expect(card).toContainText('Leadroom 0.1.4 is ready to download.')
  await card.getByRole('button', { name: 'Update' }).click()
  await expect(card).toContainText('Downloading 0.1.4')
  await expect(card.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '42')

  state = { ...state, phase: 'ready', progress: 1 }
  await expect(card).toContainText('Update ready', { timeout: 5000 })
  await card.getByRole('button', { name: 'Restart now' }).click()
  await expect(card).toContainText('Restarting Leadroom')
  expect(calls).toEqual(['download', 'install'])
})

test('a postponed update stays out of the way and nothing shows when up to date', async ({ page }) => {
  await mockShell(page)
  await mockWorkspaceData(page)
  let state = { ...base, phase: 'available' }
  await page.route('**/api/v1/updates', (route) => route.fulfill({ json: state }))
  await page.route('**/api/v1/updates/postpone', (route) => {
    state = { ...state, postponed: true }
    return route.fulfill({ json: state })
  })

  await page.goto('/runs')
  await page.locator('.update-card').getByRole('button', { name: 'Later' }).click()
  await expect(page.locator('.update-card')).toHaveCount(0)
})

test('a failed update explains itself and settings can check again', async ({ page }) => {
  await mockShell(page)
  await mockWorkspaceData(page)
  await page.route('**/api/v1/updates', (route) => route.fulfill({ json: {
    ...base, phase: 'failed', error: 'The update to Leadroom 0.1.4 did not finish.',
  } }))
  await page.route('**/api/v1/updates/check', (route) => route.fulfill({ json: { ...base, phase: 'idle', version: null, result: 'up_to_date' } }))

  await page.goto('/runs')
  await expect(page.locator('.update-card')).toContainText("Update didn't finish")
  await expect(page.locator('.update-card')).toContainText('did not finish')

  await page.goto('/settings')
  const about = page.locator('.about-settings')
  await expect(about).toContainText('Version 0.1.3')
  await about.getByRole('button', { name: 'Check for updates' }).click()
  await expect(about).toContainText('Leadroom is up to date.')
})
