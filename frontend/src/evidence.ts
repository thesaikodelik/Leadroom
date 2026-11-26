// Evidence helpers shared by the Field Book marks, the tables and the map.

import type { FieldEvidence, Lead } from './types'

export type EvidenceLevel = 0 | 1 | 2 | 3

// How a contact detail was found, strongest first.
const STRUCTURED = new Set(['json-ld', 'html-link', 'osm-local'])
const PAGE_TEXT = new Set(['html', 'site-name', 'discovered-link'])

export const EVIDENCE_TEXT: Record<EvidenceLevel, string> = {
  3: 'Published by the business as a link, structured data or a map record',
  2: 'Found in the text of the business’s own pages',
  1: 'Read by AI and not matched on the page',
  0: 'Not found',
}

export function evidenceLevel(value: string | undefined, item?: FieldEvidence): EvidenceLevel {
  if (!value) return 0
  const method = item?.method ?? ''
  if (STRUCTURED.has(method)) return 3
  if (PAGE_TEXT.has(method)) return 2
  if (method === 'llm') return 1
  return 0
}

export function leadEvidence(lead: Lead, field: 'email' | 'phone') {
  const value = field === 'email' ? (lead.emails?.[0] || lead.generic_email) : (lead.phones?.[0] || lead.phone)
  const evidence = field === 'email'
    ? lead.field_evidence?.generic_email ?? lead.field_evidence?.emails
    : lead.field_evidence?.phone ?? lead.field_evidence?.phones
  return { value, evidence, level: evidenceLevel(value, evidence) }
}

export function methodLabel(method?: string) {
  switch (method) {
    case 'json-ld': return 'Structured data'
    case 'html-link': return 'Link on page'
    case 'osm-local': return 'Map record'
    case 'html': return 'Page text'
    case 'site-name': return 'Home page title'
    case 'discovered-link': return 'Linked page'
    case 'llm': return 'Read by AI'
    case 'manual': return 'Edited by you'
    default: return method ? method.replace(/[-_]/g, ' ') : 'Source'
  }
}

/** A lead's map position, when the local map index supplied one. */
export function mapPosition(lead: Lead): { lng: number; lat: number } | null {
  const lat = Number.parseFloat(lead.latitude ?? '')
  const lng = Number.parseFloat(lead.longitude ?? '')
  if (!Number.isFinite(lat) || !Number.isFinite(lng) || (lat === 0 && lng === 0)) return null
  if (Math.abs(lat) > 90 || Math.abs(lng) > 180) return null
  return { lat, lng }
}
