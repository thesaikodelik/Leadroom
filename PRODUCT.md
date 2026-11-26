# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

A React 19 + Vite single-page app served by a local FastAPI server and shown inside a pywebview (Edge WebView2) window on Windows 10/11. There is no browser chrome; the window can be resized from narrow to wide.

## Users

In order of priority (confirmed by the owner):

1. **Sales teams at a company**, people who build and work lead lists as a regular part of the job and care about volume, order and repeatability.
2. **Freelancers and small agencies** (for example web designers or marketers) who find local businesses to sell their services to and write to them themselves.
3. **Business owners** who occasionally look for customers for their own business and have no sales or technical background.

The interface must serve the regular, repeated work of the first group without losing the third, who needs every step explained.

## Product Purpose

Leadroom turns a business niche and a location (for example *independent dental clinics in London*) into a reviewed list of real businesses with their public emails and phone numbers. It searches the web and an optional private OpenStreetMap index, reads each business's own website, lets an optional local AI model fill gaps, keeps every lead in one deduplicated repository, and supports carefully controlled, human-approved outreach.

Success: the user ends a session with leads they trust (each contact detail traceable to the page it came from) and a clear next step for each.

The heart of the product, confirmed by the owner, is **finding and reviewing leads**: creating a run, watching candidates come in, and judging the leads that result. The repository and outreach follow from it.

## Positioning

Local-first: the workspace, leads, keys and the default AI model stay on the user's PC; there is no Leadroom account or server. Every contact detail carries evidence (the source page and method), and scoring trusts only observable evidence, never a number the model invents. Outreach is reviewed and approved message by message and sent from the user's own mailbox.

## Operating Context

- **Runs:** a niche + location, discovery source (web, local map index, or both), crawl depth (quick / deep / exhaustive), batch size, whether to reuse or recheck earlier results, adaptive fetching, and whether to read sites with AI. A run discovers candidates, the user selects which to enrich, and enrichment produces leads with field-level evidence and a score.
- **Repository:** all leads across runs, deduplicated, searchable, organised into collections, exportable as CSV/JSON, with a detail drawer per lead.
- **Outreach review:** a campaign brief, AI- or template-drafted messages per lead, each approved by hand, sent through a connected SMTP mailbox, at most 25 a day, with suppression/opt-out handling and a send preflight.
- **Local data:** the optional Full Local OpenStreetMap index (WSL2 + PostgreSQL/PostGIS), its status, data date and daily sync while the app is open.
- **Settings:** workspace name/subtitle/logo, theme, storage locations, model runtime (Ollama models: list, download, select, fit test; or an OpenAI-compatible API), email accounts, discovery filters (blocked domains), local index, About + update check.
- **Updates:** the app checks GitHub hourly, offers new versions in the sidebar, downloads and verifies them, and restarts into the new version.
- Long-running work (discovery, enrichment, model downloads, map sync) runs in the background while the user keeps working; progress and cancellation must stay visible.

## Capabilities and Constraints

- Interface language: **English only** (confirmed). Tuned for UK businesses (phone formats, map index).
- Windows desktop window via WebView2; no native menus; keyboard and mouse; must work from narrow (≈390 px) to wide windows.
- Works fully offline except for searching and crawling websites, update checks and map sync.
- AI is optional: with Ollama missing or the AI step turned off, leads still get rule-based contact details. On computers without a graphics card the AI step is slow (about a minute per site).
- Outreach is capped at 25 messages a day and every message needs explicit approval.
- Existing capability: users can pick a workspace theme and set a workspace name, subtitle and logo. Whether a redesign keeps a multi-theme selector is an open design decision, not a product commitment.
- Requested 2026-11-26: a map view of a run's leads beside the table. Only leads with coordinates (from the Local map index) can be plotted; every lead, plotted or not, stays in the list. The map must need no API key, account or download: OpenFreeMap vector tiles (keyless) rendered by a bundled map library. Showing the map fetches tiles for the viewed area from that service, which the privacy notes must say.
- Pending owner request: remove the sidebar "Private workspace / Data stays on this machine" block and show the app version in small type at the bottom of the sidebar instead.

## Brand Commitments

- Name: **Leadroom**. Logo: the "L" mark made of two slanted rounded parallelograms (`assets/leadroom-mark-white.svg` holds the shape). The **shape is binding**; its **colours are not**: the owner asked (2026-11-26) that the mark be recoloured to the new design's palette everywhere it appears, including the app icon (`assets/leadroom-icon.*`), the Setup icon and wizard images (`assets/leadroom-setup.ico`, `installer/images/`, drawn by `scripts/make_installer_images.py`), the favicon and both READMEs. The current blue-to-cyan gradient is the old colouring. The owner has said there is no design system to preserve and nothing else is binding.
- Published anonymously; no person, studio or company is credited anywhere in the product.

## Evidence on Hand

- README screenshots in `docs/screenshots/` (generated from Playwright fixtures in `frontend/e2e/`).
- No testimonials, customer names, usage numbers or benchmarks exist; do not invent any.

## Product Principles

1. **Evidence before confidence.** Show where each detail came from and how sure Leadroom is; never present a guess as a fact.
2. **The run is the unit of work.** Creating a run, following its progress and reviewing what it found is the primary path and gets the most room.
3. **Background work stays visible and stoppable.** Anything slow shows progress and can be cancelled without losing earlier results.
4. **A person approves every outreach message.** The interface makes careful sending easy and careless sending hard.
5. **Plain language for non-experts.** Every option says what it does and what it costs (time, disk, data leaving the PC).

## Accessibility & Inclusion

No product-specific standard was set. Existing tests cover keyboard focus trapping, reduced motion and narrow layouts; keep them passing.
