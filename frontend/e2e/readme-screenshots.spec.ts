import { mkdirSync } from 'node:fs'
import path from 'node:path'

import { expect, test } from '@playwright/test'

const outputDir = path.resolve(process.cwd(), '../docs/screenshots')

const runs = [
  { id: 'readme-run', run_name: 'london_dental_clinics_20260721_104500', niche: 'dental clinics', location: 'London UK', crawl_mode: 'deep', search_provider: 'hybrid', status: 'completed', counts: { completed: 4, no_contact: 1, cancelled: 2 }, created_at: '2026-07-21T10:45:00Z', updated_at: '2026-07-21T11:03:00Z' },
  { id: 'readme-hvac', run_name: 'hvac_contractors_20260720_153000', niche: 'HVAC contractors', location: 'Manchester UK', crawl_mode: 'quick', search_provider: 'auto', status: 'ready', counts: { completed: 10, queued: 10, cancelled: 4 }, created_at: '2026-07-20T15:30:00Z', updated_at: '2026-07-20T15:51:00Z' },
  { id: 'readme-studio', run_name: 'creative_studios_20260719_091500', niche: 'creative studios', location: 'Bristol UK', crawl_mode: 'deep', search_provider: 'hybrid', status: 'stopped', counts: { completed: 19, failed: 2, queued: 7, cancelled: 3 }, created_at: '2026-07-19T09:15:00Z', updated_at: '2026-07-19T09:48:00Z' },
]

const leads = [
  { business_name: 'Northstar Dental Studio', domain: 'northstar-dental.example', latitude: '51.5205', longitude: '-0.1477', website: 'https://northstar-dental.example', city_or_area: 'London', business_type: 'Dental clinic', services: ['Implants', 'General dentistry'], generic_email: 'hello@northstar-dental.example', emails: ['hello@northstar-dental.example', 'appointments@northstar-dental.example'], phone: '020 7946 0123', phones: ['020 7946 0123'], contact_page: 'https://northstar-dental.example/contact', booking_page: '', instagram_or_social: '', has_online_booking: true, website_quality_note: 'Clear services and public contact details.', lead_score: 9, lead_reason: 'Verified public business contacts.', field_evidence: { generic_email: { source_url: 'https://northstar-dental.example/contact', method: 'html-link' }, phone: { source_url: 'https://northstar-dental.example/', method: 'json-ld' } }, enrichment_errors: [], niches: ['Dental clinics'], locations: ['London UK'], sources: ['local', 'web'], source_run_ids: ['readme-run'], created_at: '2026-07-21T10:50:00Z', updated_at: '2026-07-21T10:57:00Z' },
  { business_name: 'Alder & Finch Dental', domain: 'alder-finch.example', latitude: '51.5390', longitude: '-0.1426', website: 'https://alder-finch.example', city_or_area: 'Camden', business_type: 'Dental clinic', services: ['Cosmetic dentistry'], generic_email: 'care@alder-finch.example', emails: ['care@alder-finch.example'], phone: '020 7946 0188', phones: ['020 7946 0188', '0800 555 0188'], contact_page: 'https://alder-finch.example/contact', booking_page: '', instagram_or_social: '', has_online_booking: false, website_quality_note: 'Contact page verified.', lead_score: 8, lead_reason: 'Verified email and phone.', field_evidence: { generic_email: { source_url: 'https://alder-finch.example/contact', method: 'html' }, phone: { source_url: 'https://alder-finch.example/', method: 'html-link' } }, enrichment_errors: [], niches: ['Dental clinics'], locations: ['London UK'], sources: ['web'], source_run_ids: ['readme-run'], created_at: '2026-07-21T10:51:00Z', updated_at: '2026-07-21T10:58:00Z' },
  { business_name: 'Cedar House Orthodontics', domain: 'cedar-ortho.example', latitude: '51.5362', longitude: '-0.1033', website: 'https://cedar-ortho.example', city_or_area: 'Islington', business_type: 'Orthodontist', services: ['Orthodontics'], generic_email: 'team@cedar-ortho.example', emails: ['team@cedar-ortho.example'], phone: '020 7946 0152', phones: ['020 7946 0152'], contact_page: 'https://cedar-ortho.example/contact', booking_page: '', instagram_or_social: '', has_online_booking: true, website_quality_note: 'Structured business data confirmed.', lead_score: 9, lead_reason: 'Multiple matching evidence sources.', field_evidence: { generic_email: { source_url: 'https://cedar-ortho.example/contact', method: 'osm-local' }, phone: { source_url: 'https://cedar-ortho.example/', method: 'osm-local' } }, enrichment_errors: [], niches: ['Dental clinics'], locations: ['London UK'], sources: ['local'], source_run_ids: ['readme-run'], created_at: '2026-07-21T10:52:00Z', updated_at: '2026-07-21T10:59:00Z' },
  { business_name: 'River Lane Dental Care', domain: 'river-lane.example', latitude: '51.5450', longitude: '-0.0553', website: 'https://river-lane.example', city_or_area: 'Hackney', business_type: 'Dental clinic', services: ['Family dentistry'], generic_email: 'contact@river-lane.example', emails: ['contact@river-lane.example'], phone: '020 7946 0171', phones: ['020 7946 0171'], contact_page: 'https://river-lane.example/contact', booking_page: '', instagram_or_social: '', has_online_booking: false, website_quality_note: 'Public contact details found.', lead_score: 8, lead_reason: 'Verified public contact details.', field_evidence: { generic_email: { source_url: 'https://river-lane.example/contact', method: 'llm' }, phone: { source_url: 'https://river-lane.example/', method: 'html' } }, enrichment_errors: [], niches: ['Dental clinics'], locations: ['London UK'], sources: ['web'], source_run_ids: ['readme-run'], created_at: '2026-07-21T10:53:00Z', updated_at: '2026-07-21T11:00:00Z' },
]

const candidates = leads.map((lead, index) => ({
  title: lead.business_name,
  url: lead.website,
  homepage: lead.website,
  domain: lead.domain,
  snippet: `${lead.business_type} | ${lead.city_or_area} | London`,
  status: 'completed',
  source: index === 0 ? 'both' : lead.sources[0],
  sources: lead.sources,
  crawl_mode: 'deep',
  crawl_pages_checked: 8 + index,
  crawl_page_limit: 20,
  crawl_contacts_found: lead.emails.length + lead.phones.length,
}))

const settings = {
  workspace_name: 'Leadroom', workspace_subtitle: 'Signal desk', logo_data_url: '', theme: 'fieldbook',
  model_provider: 'ollama', model_name: 'llama3.2:3b', default_model: 'ollama/llama3.2:3b', model_endpoint: 'http://localhost:11434', ollama_base_url: 'http://localhost:11434', api_key_configured: false,
  blocked_domains: ['wikipedia.org', 'github.com', 'yelp.com'], smtp_host: '', smtp_port: 587, smtp_security: 'starttls', smtp_username: '', smtp_password_configured: false, smtp_from_email: '', smtp_from_name: '', smtp_reply_to: '',
  email_accounts: [{ id: 'demo-sender', label: 'Demo sales', host: 'smtp.example.test', port: 587, security: 'starttls', username: 'sales@leadroom.example', password_configured: true, from_email: 'sales@leadroom.example', from_name: 'Leadroom Demo', reply_to: 'privacy@leadroom.example', is_default: true }],
  default_email_account_id: 'demo-sender', email_configured: true,
}

test('capture privacy-safe README screenshots', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'README assets use the desktop viewport')
  mkdirSync(outputDir, { recursive: true })
  await page.clock.setFixedTime(new Date('2026-07-21T10:45:00Z'))

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const pathname = url.pathname

    if (pathname === '/api/v1/health') return route.fulfill({ json: { status: 'ok', database: 'ok', version: '0.1.8' } })
    if (pathname === '/api/v1/outreach/budget') return route.fulfill({ json: { sent: 4, reserved: 0, limit: 25 } })
    if (pathname === '/api/v1/updates') return route.fulfill({ json: { current_version: '0.1.8', phase: 'idle', version: null, page: '', notes: '', progress: 0, error: '', postponed: false, installed: true, enabled: true } })
    if (pathname === '/api/v1/settings') return route.fulfill({ json: settings })
    if (pathname === '/api/v1/settings/email-accounts') return route.fulfill({ json: { accounts: settings.email_accounts, default_account_id: 'demo-sender' } })
    if (pathname === '/api/v1/settings/storage') return route.fulfill({ json: { data_root: 'D:\\LeadroomData', downloads_root: 'D:\\LeadroomModels', active_data_root: 'D:\\LeadroomData', database_path: 'D:\\LeadroomData\\lead_scraper.db', database_exists: true, database_bytes: 18400000, workspace_bytes: 76000000, cache_dir: 'D:\\LeadroomModels\\cache', browser_dir: 'D:\\LeadroomModels\\playwright', ollama_dir: 'D:\\LeadroomModels\\ollama', data_disk: { free_bytes: 380000000000, total_bytes: 1000000000000 }, downloads_disk: { free_bytes: 720000000000, total_bytes: 2000000000000 }, restart_required: false, ollama_restart_required: false } })
    if (pathname === '/api/v1/settings/ollama/models') return route.fulfill({ json: { status: 'ok', endpoint: 'http://localhost:11434', selected_model: 'llama3.2:3b', models: [{ name: 'llama3.2:3b', size: 2000000000, details: { parameter_size: '3.2B', quantization_level: 'Q4_K_M' } }, { name: 'qwen2.5:7b', size: 4700000000, details: { parameter_size: '7.6B', quantization_level: 'Q4_K_M' } }] } })
    if (pathname === '/api/v1/settings/ollama/catalog') return route.fulfill({ json: { status: 'ok', selected_model: 'llama3.2:3b', installed: ['llama3.2:3b', 'qwen2.5:7b'], models: [] } })
    if (pathname === '/api/v1/local-data/status') return route.fulfill({ json: { ready: true, database: 'online', message: 'Local discovery is ready.', businesses: 1240000, with_website: 612000, with_phone: 804000, with_email: 186000, dataset: 'OpenStreetMap Great Britain', update_status: 'idle', update_schedule: 'Daily at 03:30' } })
    if (pathname === '/api/v1/discovery/history') return route.fulfill({ json: { previous_runs: 3, seen_domains: 46, completed_leads: 31 } })
    if (pathname === '/api/v1/runs/readme-run') return route.fulfill({ json: { run: { ...runs[0], discovery: { mode: 'new_only', next_search_page: 4, web_candidates: 11, local_candidates: 7 } }, candidates, leads } })
    if (pathname === '/api/v1/runs') return route.fulfill({ json: runs })
    if (pathname === '/api/v1/repository') return route.fulfill({ json: { count: leads.length, leads } })
    if (pathname === '/api/v1/compliance/suppressions') return route.fulfill({ json: [{ id: 'suppression-demo', type: 'email', value_hint: 'o***@example.test', reason: 'Demo opt-out', created_at: '2026-07-20T12:00:00Z' }] })
    if (pathname === '/api/v1/outreach/drafts') return route.fulfill({ json: [
      { id: 'draft-1', run_id: 'readme-run', lead_domain: 'northstar-dental.example', recipient_email: 'hello@northstar-dental.example', subscriber_type: 'corporate', consent_confirmed: false, lawful_basis_note: 'Public corporate mailbox reviewed for this demonstration.', subject: 'A practical idea for Northstar Dental Studio', body: 'Hello Northstar Dental Studio team,\n\nI noticed your public implant service information and prepared a concise introduction relevant to your practice.\n\nYou can opt out at any time using the contact details below.', status: 'approved', approved_by: 'Demo reviewer', created_at: '2026-07-21T11:10:00Z', delivery_status: '', delivery_error: '', provider_message_id: '', sent_at: '' },
      { id: 'draft-2', run_id: 'readme-run', lead_domain: 'alder-finch.example', recipient_email: 'care@alder-finch.example', subscriber_type: 'corporate', consent_confirmed: false, lawful_basis_note: 'Public corporate mailbox reviewed for this demonstration.', subject: 'Introduction for Alder & Finch Dental', body: 'A short evidence-based draft ready for human review.', status: 'draft', approved_by: '', created_at: '2026-07-21T11:11:00Z', delivery_status: '', delivery_error: '', provider_message_id: '', sent_at: '' },
    ] })
    return route.fulfill({ json: {} })
  })

  const capture = async (route: string, name: string, heading: string) => {
    await page.goto(route)
    await page.reload()
    await expect(page.getByRole('heading', { name: heading, exact: true }).first()).toBeVisible()
    await page.evaluate(() => document.fonts.ready)
    await page.evaluate(() => window.scrollTo(0, 0))
    await page.waitForTimeout(700)
    await page.screenshot({ path: path.join(outputDir, `${name}.png`), fullPage: false })
  }

  await capture('/runs', 'runs', 'Runs')
  await capture('/new', 'new-run', 'Find your next market')
  await capture('/runs/readme-run', 'run-workspace', 'Dental clinics')
  // The same run on the map: tiles come from OpenFreeMap, the leads are synthetic.
  await page.getByRole('row', { name: /Northstar Dental Studio/ }).getByRole('cell').first().click()
  await page.waitForTimeout(600)
  await page.screenshot({ path: path.join(outputDir, 'run-workspace.png'), fullPage: false })
  await page.locator('.view-switch button', { hasText: 'Map' }).click()
  await page.waitForTimeout(6000)
  await page.locator('.leads-map').scrollIntoViewIfNeeded()
  await page.screenshot({ path: path.join(outputDir, 'run-map.png'), fullPage: false })
  await capture('/repository', 'repository', 'Repository')
  await capture('/outreach', 'outreach', 'Outreach review')
  await capture('/settings', 'settings', 'Settings')
})
