import type { Page } from '@playwright/test'

// Synthetic demonstration data: plausible London dental clinics, not real businesses.
export const demoRunId = 'run-dental-london'

const lead = (name: string, domain: string, area: string, email: string, emailMethod: string, phone: string, phoneMethod: string, score: number, lat: number, lng: number, extra: Record<string, unknown> = {}) => ({
  business_name: name, website: `https://${domain}`, domain, city_or_area: area, address: `${area}, London`,
  business_type: 'Dental clinic', services: ['General dentistry', 'Hygiene', 'Implants'],
  generic_email: email, emails: email ? [email] : [], phone, phones: phone ? [phone] : [],
  contact_page: `https://${domain}/contact`, booking_page: '', instagram_or_social: '', has_online_booking: false,
  website_quality_note: '', lead_score: score, lead_reason: 'Email and phone published on the clinic’s own site.',
  enrichment_errors: [], latitude: lat ? String(lat) : '', longitude: lng ? String(lng) : '',
  field_evidence: {
    ...(email ? { generic_email: { value: email, source_url: `https://${domain}/contact`, method: emailMethod } } : {}),
    ...(phone ? { phone: { value: phone, source_url: `https://${domain}/`, method: phoneMethod } } : {}),
  },
  ...extra,
})

export const demoLeads = [
  lead('Bright Smile Dental', 'brightsmile.co.uk', 'Islington', 'hello@brightsmile.co.uk', 'html-link', '020 7946 0123', 'json-ld', 9, 51.5362, -0.1033),
  lead('Harley Row Dental Studio', 'harleyrowdental.co.uk', 'Marylebone', 'info@harleyrowdental.co.uk', 'html-link', '020 7946 0458', 'html', 9, 51.5205, -0.1477),
  lead('Camden Family Dentists', 'camdenfamilydentists.co.uk', 'Camden', 'reception@camdenfamilydentists.co.uk', 'html', '020 7946 0871', 'html-link', 8, 51.5390, -0.1426),
  lead('Greenwich Smile Studio', 'greenwichsmile.co.uk', 'Greenwich', 'bookings@greenwichsmile.co.uk', 'osm-local', '020 7946 0599', 'osm-local', 8, 51.4826, -0.0077),
  lead('Clapham Common Dental', 'claphamcommondental.co.uk', 'Clapham', '', '', '020 7946 0312', 'html', 6, 51.4618, -0.1384),
  lead('Northcote Dental Care', 'northcotedental.co.uk', 'Battersea', 'hello@northcotedental.co.uk', 'llm', '020 7946 0244', 'llm', 5, 0, 0),
]

const candidate = (title: string, domain: string, status: string, sources: string[], snippet: string) => ({
  title, url: `https://${domain}`, homepage: `https://${domain}`, domain, snippet, status, source: sources[0] === 'local' ? 'osm_local' : 'web', sources,
  crawl_mode: 'deep', crawl_pages_checked: status === 'completed' ? 9 : status === 'processing' ? 4 : 0, crawl_page_limit: 20, crawl_contacts_found: 2,
})

export const demoRun = {
  run: {
    id: demoRunId, run_name: 'independent_dental_clinics_20261126_104200_000', status: 'running',
    niche: 'independent dental clinics', location: 'London UK', crawl_mode: 'deep', search_provider: 'hybrid',
    counts: { completed: 33, no_contact: 6, failed: 2, processing: 2, queued: 17, cancelled: 88 },
    created_at: '2026-11-26T10:42:00Z', updated_at: '2026-11-26T11:00:00Z',
    discovery: { mode: 'new_only', new_candidates: 148, local_results: 61, web_results: 104, merged_results: 17, previously_seen_filtered: 12, pages_searched: 9 },
  },
  candidates: [
    candidate('Bright Smile Dental – Islington dentist', 'brightsmile.co.uk', 'completed', ['local', 'web'], 'Family and cosmetic dentistry on Upper Street, Islington.'),
    candidate('Harley Row Dental Studio', 'harleyrowdental.co.uk', 'completed', ['web'], 'Private dental studio in Marylebone. Implants, hygiene and whitening.'),
    candidate('Camden Family Dentists', 'camdenfamilydentists.co.uk', 'processing', ['local'], 'NHS and private dentistry for families in Camden Town.'),
    candidate('Find a dentist near you | Dental directory', 'dentaldirectory.example', 'cancelled', ['web'], 'Compare 2,000 dentists across London.'),
    candidate('Greenwich Smile Studio', 'greenwichsmile.co.uk', 'queued', ['local', 'web'], 'Modern dental studio by Greenwich Park.'),
  ],
  leads: demoLeads,
}

export const demoRuns = [
  demoRun.run,
  { id: 'run-accountants', run_name: 'accountants', status: 'completed', niche: 'accountants', location: 'Manchester UK', crawl_mode: 'quick', search_provider: 'auto', counts: { completed: 41, no_contact: 9, failed: 1, cancelled: 23 }, created_at: '2026-11-24T09:10:00Z', updated_at: '2026-11-24T09:58:00Z' },
  { id: 'run-venues', run_name: 'wedding_venues', status: 'ready', niche: 'wedding venues', location: 'Kent UK', crawl_mode: 'deep', search_provider: 'osm_local', counts: { queued: 52, cancelled: 4 }, created_at: '2026-11-25T16:20:00Z', updated_at: '2026-11-25T16:21:00Z' },
]

export async function mockDemoWorkspace(page: Page, options: { budget?: { sent: number; reserved: number; limit: number } } = {}) {
  await page.route('**/api/v1/updates', (route) => route.fulfill({ json: { current_version: '0.1.8', phase: 'idle', version: null, page: '', notes: '', progress: 0, error: '', postponed: false, installed: true, enabled: true } }))
  await page.route('**/api/v1/health', (route) => route.fulfill({ json: { status: 'ok', database: 'ok', version: '0.1.8' } }))
  await page.route('**/api/v1/outreach/budget', (route) => route.fulfill({ json: options.budget ?? { sent: 7, reserved: 0, limit: 25 } }))
  await page.route('**/api/v1/outreach/drafts', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/settings/email-accounts', (route) => route.fulfill({ json: { accounts: [], default_account_id: '' } }))
  await page.route('**/api/v1/settings', (route) => route.fulfill({ json: {
    workspace_name: 'Leadroom', workspace_subtitle: 'Signal desk', logo_data_url: '', theme: 'fieldbook', email_configured: false, email_accounts: [], default_email_account_id: '',
    default_model: 'ollama/llama3.2:3b', model_provider: 'ollama', model_name: 'llama3.2:3b', model_endpoint: 'http://localhost:11434',
    api_key_configured: false, smtp_password_configured: false, blocked_domains: [], limits: { max_results_per_query: 100, max_sites: 500 }, search_providers: ['hybrid', 'osm_local', 'auto'],
  } }))
  await page.route('**/api/v1/runs', (route) => route.fulfill({ json: demoRuns }))
  await page.route(`**/api/v1/runs/${demoRunId}`, (route) => route.fulfill({ json: demoRun }))
}
