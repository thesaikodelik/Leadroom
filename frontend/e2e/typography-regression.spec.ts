import { expect, test } from '@playwright/test'
import { mockWorkspaceData } from './run-fixture'

const routes = ['/runs', '/new', '/repository', '/outreach', '/settings', '/local-data']

// The Survey Field Book type system: Public Sans for text, Barlow Condensed caps for
// labels, Roboto Mono for numbers, on one size scale (frontend/src/styles/tokens.css).
test('primary screens use the shared typography system', async ({ page }) => {
  await mockWorkspaceData(page)

  for (const route of routes) {
    await page.goto(route)
    await page.waitForLoadState('networkidle')

    const violations = await page.locator('body').evaluate((body) => {
      const families = ['Public Sans Variable', 'Barlow Condensed', 'Roboto Mono Variable']
      const sizes = new Set(['11px', '12px', '12.5px', '14px', '15.5px', '17px', '18px', '22px', '24px', '26px', '30px', '32px'])
      const weights = new Set(['400', '500', '600', '700'])
      const ownText = (element: Element) => [...element.childNodes].some((node) => node.nodeType === Node.TEXT_NODE && node.textContent?.trim())

      return [...body.querySelectorAll('*')].flatMap((element) => {
        if (!ownText(element) || element.closest('.sr-only')) return []
        const style = getComputedStyle(element)
        const family = style.fontFamily.split(',')[0].replaceAll('"', '').trim()
        const tracking = style.letterSpacing === 'normal' ? 0 : Number.parseFloat(style.letterSpacing)
        // Only condensed caps are tracked open; headings may tighten slightly.
        const trackingIsValid = family === 'Barlow Condensed' ? tracking > 0 : tracking <= 0 && tracking >= -0.04 * Number.parseFloat(style.fontSize)
        if (families.includes(family) && sizes.has(style.fontSize) && weights.has(style.fontWeight) && trackingIsValid) return []
        return [{ tag: element.tagName, className: element.getAttribute('class') ?? '', text: element.textContent?.trim().slice(0, 40) ?? '', family, size: style.fontSize, weight: style.fontWeight, spacing: style.letterSpacing }]
      })
    })

    expect(violations, `Typography violations on ${route}`).toEqual([])
  }
})
