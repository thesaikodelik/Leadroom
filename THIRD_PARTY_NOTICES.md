# Third-Party Notices

Leadroom includes or integrates with third-party open-source software and data. This file is a concise attribution guide, not a replacement for the license text distributed with each dependency.

## ScrapeGraphAI

The first Leadroom prototype was built around `SmartScraperGraph`, and the current enrichment pipeline continues to depend on the open-source [ScrapeGraphAI project](https://github.com/ScrapeGraphAI/Scrapegraph-ai).

- Upstream repository: <https://github.com/ScrapeGraphAI/Scrapegraph-ai>
- Upstream license: MIT
- Role in Leadroom: LLM-assisted structured extraction from public business websites

Leadroom is an independent community project. It is not an official ScrapeGraphAI product and is not endorsed by ScrapeGraphAI's maintainers.

## Scrapling

Leadroom optionally uses [Scrapling](https://github.com/D4Vinci/Scrapling) as an adaptive HTTP fetcher when a public website rejects or challenges the standard client.

- Upstream repository: <https://github.com/D4Vinci/Scrapling>
- Upstream license: BSD 3-Clause
- Role in Leadroom: TLS-aware fallback fetching for public business pages

## html2text

ScrapeGraphAI depends on [html2text](https://github.com/Alir3z4/html2text), which is bundled into the Windows builds.

- Upstream repository: <https://github.com/Alir3z4/html2text>
- Upstream license: GPL-3.0-or-later ([licenses/GPL-3.0.txt](licenses/GPL-3.0.txt))
- Role in Leadroom: HTML-to-text conversion inside ScrapeGraphAI

Because the Windows installer and portable build include html2text, those binaries as a whole are distributed under the terms of the GNU General Public License, version 3 or later. Leadroom's own source code remains available under the MIT License, which is compatible with the GPL. The complete corresponding source for each binary release is this repository at the release's tag, together with the published sources of the dependencies listed in `THIRD_PARTY_LICENSES.txt`.

## OpenStreetMap and Geofabrik

The optional local discovery engine can download OpenStreetMap extracts provided by Geofabrik.

- OpenStreetMap copyright: <https://www.openstreetmap.org/copyright>
- Open Database License (ODbL): <https://opendatacommons.org/licenses/odbl/>
- Geofabrik download server and usage policy: <https://download.geofabrik.de/>

OpenStreetMap data is Copyright OpenStreetMap contributors and is available under the ODbL. Generated products must preserve the attribution and comply with the applicable database license.

## Other Dependencies

Python and frontend dependencies are declared in `pyproject.toml`, `requirements.txt`, and `frontend/package-lock.json`. The current audit is recorded in `docs/DEPENDENCY_LICENSES.md`. Release builds generate `THIRD_PARTY_LICENSES.txt` (with `scripts/collect_licenses.py`), which reproduces the licence text of every bundled package and ships next to the application.
