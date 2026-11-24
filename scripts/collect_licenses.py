"""Collect the licence texts of every third-party package bundled into Leadroom.exe.

Writes one plain-text file that the installer and the portable archive ship next to
the application, so binary releases carry the notices that MIT, BSD, Apache and GPL
licences require. Run it with the build virtual environment's Python:

    .venv\\Scripts\\python.exe scripts\\collect_licenses.py build\\THIRD_PARTY_LICENSES.txt
"""

from __future__ import annotations

import json
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Build and test tooling that is installed in the virtual environment but is not
# bundled into the application.
DEV_ONLY = {
    "pyinstaller",
    "pyinstaller-hooks-contrib",
    "altgraph",
    "pefile",
    "pywin32-ctypes",
    "pytest",
    "pytest-asyncio",
    "pytest-cov",
    "pytest-timeout",
    "coverage",
    "iniconfig",
    "pluggy",
    "ruff",
    "mypy",
    "mypy-extensions",
    "pip",
    "setuptools",
    "wheel",
}

LICENCE_NAMES = ("LICENSE", "LICENCE", "COPYING", "NOTICE", "AUTHORS")
RULE = "=" * 78


def _licence_files(dist: metadata.Distribution) -> list[Path]:
    found: list[Path] = []
    for entry in dist.files or []:
        name = Path(str(entry)).name.upper()
        if name.startswith(LICENCE_NAMES) and ".dist-info" in str(entry):
            path = Path(str(dist.locate_file(entry)))
            if path.is_file():
                found.append(path)
    return sorted(found)


def _licence_label(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    expression = meta.get("License-Expression")
    if expression:
        return expression
    classifiers = [
        c.split("::")[-1].strip()
        for c in meta.get_all("Classifier") or []
        if c.startswith("License ::")
    ]
    if classifiers:
        return ", ".join(classifiers)
    licence = (meta.get("License") or "").strip()
    if licence and "\n" not in licence and len(licence) < 80:
        return licence
    return "see licence text below"


def python_section() -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for dist in sorted(metadata.distributions(), key=lambda d: (d.metadata["Name"] or "").lower()):
        name = dist.metadata["Name"] or ""
        key = name.lower().replace("_", "-")
        if not name or key in DEV_ONLY or key in seen:
            continue
        seen.add(key)
        lines += [RULE, f"{name} {dist.version}", f"Licence: {_licence_label(dist)}"]
        homepage = dist.metadata.get("Home-page") or next(
            (u.split(",", 1)[1].strip() for u in dist.metadata.get_all("Project-URL") or []),
            "",
        )
        if homepage:
            lines.append(f"Source: {homepage}")
        lines.append(RULE)
        files = _licence_files(dist)
        if not files:
            lines += ["(No licence file is shipped in this package's metadata.)", ""]
        for path in files:
            lines += [f"--- {path.name} ---", path.read_text(encoding="utf-8", errors="replace").strip(), ""]
    return lines


def frontend_section() -> list[str]:
    lock = json.loads((ROOT / "frontend" / "package-lock.json").read_text(encoding="utf-8"))
    lines: list[str] = []
    for key, info in sorted(lock.get("packages", {}).items()):
        if not key.startswith("node_modules/") or info.get("dev") or info.get("devOptional"):
            continue
        name = key.rsplit("node_modules/", 1)[1]
        folder = ROOT / "frontend" / key
        lines += [RULE, f"{name} {info.get('version', '')} (frontend)", f"Licence: {info.get('license', 'unknown')}", RULE]
        texts = [p for p in sorted(folder.glob("*")) if p.is_file() and p.name.upper().startswith(LICENCE_NAMES)]
        if not texts:
            lines += ["(No licence file is shipped in this package.)", ""]
        for path in texts:
            lines += [path.read_text(encoding="utf-8", errors="replace").strip(), ""]
    return lines


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: collect_licenses.py OUTPUT", file=sys.stderr)
        return 2
    header = [
        "Leadroom: third-party licences",
        "",
        "Leadroom's own source code is released under the MIT License (LICENSE).",
        "The Windows installer and portable build bundle the third-party packages below.",
        "Each remains under its own licence, reproduced here as shipped by the package.",
        "",
        "html2text is licensed under GPL-3.0-or-later, so the bundled Leadroom.exe as a",
        "whole is distributed under the terms of the GNU General Public License,",
        "version 3 or later (see GPL-3.0.txt). The complete corresponding source code is",
        "the Leadroom repository at the matching release tag, plus the listed packages'",
        "published sources: https://github.com/thesaikodelik/Leadroom",
        "",
    ]
    body = python_section() + frontend_section()
    output = Path(sys.argv[1])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(header + body) + "\n", encoding="utf-8")
    count = sum(1 for line in body if line.startswith("Licence: "))
    print(f"Wrote licences for {count} packages to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
