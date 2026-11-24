# Dependency Licence Audit

This document records the source-publication audit updated on 23 July 2026. It is not legal advice and does not replace the licence text shipped by each dependency.

## Scope

- Direct Python dependencies declared in `pyproject.toml`
- Their installed runtime dependency graph in the project virtual environment
- Non-development frontend packages in `frontend/package-lock.json`
- Optional OpenStreetMap data, ScrapeGraphAI, and Scrapling attribution described in `THIRD_PARTY_NOTICES.md`

## Result

- 121 installed Python runtime packages were inspected using package metadata, including `License-Expression`, `License`, and licence classifiers.
- 15 frontend runtime packages were inspected from the lockfile; all declared a licence and no strong-copyleft licence was reported.
- ScrapeGraphAI's installed wheel does not expose complete licence metadata. Its upstream repository declares the MIT licence and is attributed in `THIRD_PARTY_NOTICES.md`.
- Scrapling declares the BSD 3-Clause licence and is attributed in `THIRD_PARTY_NOTICES.md`; its fetcher extras add curl-cffi, BrowserForge, Patchright, and supporting runtime packages.
- `html2text==2025.4.15`, pulled transitively by ScrapeGraphAI, declares `GPL-3.0-or-later`.

## Release Decision

Updated on 24 November 2026: binary releases are published under the GPL route.

- The source repository is published under Leadroom's MIT licence with third-party notices.
- The Windows installer and portable build bundle `html2text` (GPL-3.0-or-later), so those binaries as a whole are distributed under GPL-3.0-or-later terms. MIT and the other bundled licences (including psycopg's LGPL-3.0) are compatible with that.
- Every binary release ships the GPL text (`licenses/GPL-3.0.txt`), `THIRD_PARTY_NOTICES.md`, and a generated `THIRD_PARTY_LICENSES.txt` with the licence text of each bundled Python and frontend package.
- Each GitHub Release is tagged, and the release notes link to the source at that tag as the complete corresponding source.
- Known gap: `langchain-community`, `minify_html`, `primp`, `proxy_tools`, and `tokenizers` ship no licence file in their wheels. `THIRD_PARTY_LICENSES.txt` records their declared licence and source; add the upstream texts when they become available.

## Re-run Before Every Binary Release

1. Build from a clean environment using the locked dependency versions.
2. Inspect both Python and frontend runtime dependency trees.
3. Resolve packages with missing or ambiguous metadata against their official source distributions.
4. Include all required licence texts and notices in the release artifact.
5. Re-check bundled browser, WebView, Ollama, model, and map-data licences because those components may not appear in language package metadata.

The authoritative dependency declarations are `pyproject.toml`, `requirements.txt`, and `frontend/package-lock.json`.
