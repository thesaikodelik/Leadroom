"""Keeps the installed app up to date from the project's GitHub releases.

The app looks for a newer release now and then, downloads its installer when the user asks,
checks the project's signature on it, and runs it quietly when the user restarts. The
installer replaces the files and opens the new version (``/RELAUNCH=1``).

Every step is written to ``logs/update.log`` and the installer writes
``logs/update-installer.log`` beside it, so a failure on someone else's computer can be
traced. Before quitting for the installer the app records ``update-pending.json``; the next
copy to open either is the new version or learns that the installer did not finish.

A file ``update-feed.txt`` in the Leadroom folder (``%LOCALAPPDATA%\\Leadroom``) holding an
address points any build at a test feed. What it offers is still installed only when signed
with the key built into the app, and only when it is newer.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

REPOSITORY = "thesaikodelik/Leadroom"
FEED_URL = f"https://api.github.com/repos/{REPOSITORY}/releases?per_page=10"
RELEASES_PAGE = f"https://github.com/{REPOSITORY}/releases"
INSTALLER_NAME = "Leadroom-Setup.exe"
TAG_PREFIX = "v"
# The public half of the release signing key (scripts/sign_update.py public).
PUBLIC_KEY = "cxgbE1WK+tudfNAI7NzPXI6wiIoL9sHedvfIRbxRDvY="
SIGNATURE_DOMAIN = b"leadroom-update-v1\n"
DEV_VERSION = "0.0.0+dev"
CHECK_EVERY = timedelta(hours=1)

log = logging.getLogger("leadroom.updater")


def current_version() -> str:
    """The version this build was made as; a source checkout reports a development version."""
    try:
        from app._build_info import VERSION  # type: ignore[import-not-found]
    except ImportError:
        return DEV_VERSION
    return str(VERSION)


def trusted_public_key() -> str:
    """The key updates must be signed with. A test build may carry its own, set at build time."""
    try:
        from app._build_info import UPDATE_PUBLIC_KEY  # type: ignore[import-not-found]
    except ImportError:
        return PUBLIC_KEY
    return str(UPDATE_PUBLIC_KEY or PUBLIC_KEY)


def _parts(version: str) -> list[int]:
    core = version.lstrip("vV").split("+", 1)[0]
    parts: list[int] = []
    for piece in core.replace("-", ".").split("."):
        digits = "".join(character for character in piece if character.isdigit())
        parts.append(int(digits) if digits else 0)
    return parts


def is_newer(version: str, other: str) -> bool:
    """Compares number by number, so 0.1.10 is newer than 0.1.9."""
    a, b = _parts(version), _parts(other)
    width = max(len(a), len(b))
    return a + [0] * (width - len(a)) > b + [0] * (width - len(b))


def signed_message(path: Path) -> bytes:
    """What the release key signs: a fixed label and the SHA-256 digest of the installer."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return SIGNATURE_DOMAIN + digest.digest()


def verify_signature(path: Path, signature_text: str, public_key: str | None = None) -> bool:
    try:
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key or trusted_public_key()))
        key.verify(base64.b64decode(signature_text.strip(), validate=True), signed_message(path))
    except (InvalidSignature, ValueError, TypeError):
        return False
    return True


@dataclass(frozen=True)
class Release:
    version: str
    page: str
    installer_url: str
    signature_url: str
    notes: str = ""
    size: int = 0


def newest_release(feed: Any, current: str) -> Release | None:
    """The newest finished release in a GitHub ``releases`` answer that is newer than ``current``.

    A release without the installer and its signature is passed over, as if not out yet.
    """
    best: Release | None = None
    for entry in feed if isinstance(feed, list) else []:
        if not isinstance(entry, dict) or entry.get("draft") or entry.get("prerelease"):
            continue
        tag = str(entry.get("tag_name") or "")
        if not tag.startswith(TAG_PREFIX):
            continue
        assets = {
            str(asset.get("name")): asset
            for asset in entry.get("assets") or []
            if isinstance(asset, dict) and asset.get("browser_download_url")
        }
        installer = assets.get(INSTALLER_NAME)
        signature = assets.get(INSTALLER_NAME + ".sig")
        if not installer or not signature:
            continue
        release = Release(
            version=tag[len(TAG_PREFIX):],
            page=str(entry.get("html_url") or RELEASES_PAGE),
            installer_url=str(installer["browser_download_url"]),
            signature_url=str(signature["browser_download_url"]),
            notes=str(entry.get("body") or "")[:4000],
            size=int(installer.get("size") or 0),
        )
        if is_newer(release.version, current) and (best is None or is_newer(release.version, best.version)):
            best = release
    return best


class Updater:
    IDLE, AVAILABLE, DOWNLOADING, READY, FAILED = "idle", "available", "downloading", "ready", "failed"

    def __init__(
        self,
        home: Path,
        *,
        version: str | None = None,
        executable: Path | None = None,
        frozen: bool | None = None,
        client_factory: Callable[[], httpx.Client] | None = None,
    ) -> None:
        self.home = home
        self.version = version or current_version()
        self.executable = executable or Path(sys.executable)
        self.frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
        self._client_factory = client_factory or (
            lambda: httpx.Client(
                headers={"User-Agent": "Leadroom-updater", "Accept": "application/vnd.github+json"},
                follow_redirects=True,
                timeout=httpx.Timeout(20, read=60),
            )
        )
        self._lock = threading.RLock()
        self._last_look: datetime | None = None
        self._auto: threading.Thread | None = None
        self._stop = threading.Event()
        self.phase = self.IDLE
        self.release: Release | None = None
        self.progress = 0.0
        self.error = ""
        self.postponed = False
        self._staged: Path | None = None
        self._discard_old_downloads()
        self._check_pending()

    # Files ------------------------------------------------------------------------------
    @property
    def pending_file(self) -> Path:
        return self.home / "update-pending.json"

    @property
    def feed_file(self) -> Path:
        return self.home / "update-feed.txt"

    @property
    def installer_log(self) -> Path:
        return self.home / "logs" / "update-installer.log"

    @property
    def download_folder(self) -> Path:
        return Path(tempfile.gettempdir()) / "leadroom-update"

    @property
    def log_file(self) -> Path:
        return self.home / "logs" / "update.log"

    def _log(self, message: str) -> None:
        """One line in update.log, opened and closed each time; past 200 KB it starts again."""
        log.info("%s", message)
        try:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            if self.log_file.exists() and self.log_file.stat().st_size > 200_000:
                self.log_file.unlink()
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with self.log_file.open("a", encoding="utf-8") as handle:
                handle.write(f"{stamp} [{self.version}] {message}\n")
        except OSError:
            pass

    def _discard_old_downloads(self) -> None:
        # The installer of the update that brought this version, or of one given up on.
        folder = self.download_folder
        if folder.is_dir():
            for item in folder.iterdir():
                with contextlib.suppress(OSError):
                    item.unlink()

    def _check_pending(self) -> None:
        try:
            pending = json.loads(self.pending_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        with contextlib.suppress(OSError):
            self.pending_file.unlink()
        version = str(pending.get("version") or "")
        if not version or not is_newer(version, self.version):
            self._log(f"opened as {self.version}: the update to {version} arrived")
            return
        self._log(f"opened as {self.version}, not {version}: the installer did not finish")
        self.release = Release(version, str(pending.get("page") or RELEASES_PAGE), "", "")
        self.error = (
            f"The update to Leadroom {version} did not finish. "
            f"Details: {self.installer_log}"
        )
        self.phase = self.FAILED

    # State ------------------------------------------------------------------------------
    @property
    def installed(self) -> bool:
        """A copy Setup put in place, and so one an update can replace."""
        return self.frozen and any(self.executable.parent.glob("unins*.exe"))

    @property
    def test_feed(self) -> str | None:
        try:
            text = self.feed_file.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return text if text.startswith(("http://", "https://")) else None

    @property
    def enabled(self) -> bool:
        """A development build looks for updates only when pointed at a test feed."""
        return self.version != DEV_VERSION or self.test_feed is not None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            release = self.release
            return {
                "current_version": self.version,
                "phase": self.phase,
                "version": release.version if release else None,
                "page": release.page if release else RELEASES_PAGE,
                "notes": release.notes if release else "",
                "progress": round(self.progress, 3),
                "error": self.error,
                "postponed": self.postponed,
                "installed": self.installed,
                "enabled": self.enabled,
            }

    # Looking ----------------------------------------------------------------------------
    def check(self, asked: bool = False) -> str | None:
        """Looks for a newer release: by itself at most once an hour, at once when asked.

        Returns "found", "up_to_date" or "no_answer", or None when it did not look.
        """
        with self._lock:
            if not self.enabled:
                return None
            if asked and self.phase == self.AVAILABLE and self.postponed:
                self.postponed = False
                return "found"
            if self.phase not in {self.IDLE, self.FAILED} or (
                self.phase == self.FAILED and not asked
            ):
                return None
            now = datetime.now(UTC)
            if not asked and self._last_look and now - self._last_look < CHECK_EVERY:
                return None
            self._last_look = now
        feed_url = self.test_feed or FEED_URL
        if feed_url != FEED_URL:
            self._log(f"looking at the test feed {feed_url}")
        try:
            with self._client_factory() as client:
                response = client.get(feed_url)
            if response.status_code != 200:
                # A private repository answers 404 to anonymous requests; that is not an error.
                self._log(f"the release list answered {response.status_code}")
                return "no_answer"
            release = newest_release(response.json(), self.version)
        except (httpx.HTTPError, ValueError) as exc:
            self._log(f"could not look for updates: {type(exc).__name__}: {exc}")
            return "no_answer"
        if release is None:
            with self._lock:
                if asked and self.phase == self.FAILED:
                    # Asked again after a failure, and nothing newer is out: nothing to report.
                    self.phase, self.error, self.release = self.IDLE, "", None
            return "up_to_date"
        with self._lock:
            self.release = release
            self.phase = self.AVAILABLE
            self.error = ""
            if asked:
                self.postponed = False
        self._log(f"found {release.version}: {release.installer_url}")
        return "found"

    def start_automatic(self, first_delay: float = 20) -> None:
        if self._auto and self._auto.is_alive():
            return

        def loop() -> None:
            delay = first_delay
            while not self._stop.wait(delay):
                delay = CHECK_EVERY.total_seconds()
                try:
                    self.check()
                except Exception:  # noqa: BLE001 - looking for updates must never stop the app
                    continue

        self._auto = threading.Thread(target=loop, name="update-check", daemon=True)
        self._auto.start()

    def stop_automatic(self) -> None:
        self._stop.set()

    def postpone(self) -> None:
        with self._lock:
            self.postponed = True

    # Downloading ------------------------------------------------------------------------
    def download(self) -> dict[str, Any]:
        with self._lock:
            if self.phase != self.AVAILABLE or self.release is None:
                return self.snapshot()
            if not self.installed:
                # A copy run from a build folder or the portable zip cannot be replaced by Setup.
                self._log(f"not installed by Setup ({self.executable.parent}); sent to the release page")
                self.open_page()
                return self.snapshot()
            release = self.release
            self.phase = self.DOWNLOADING
            self.progress = 0.0
            self.error = ""
        self._log(f"downloading {release.version}")
        threading.Thread(target=self._fetch, args=(release,), name="update-download", daemon=True).start()
        return self.snapshot()

    def _fetch(self, release: Release) -> None:
        folder = self.download_folder
        target = folder / f"Leadroom-Setup-{release.version}.exe"
        step = "download of the installer"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            with self._client_factory() as client:
                with client.stream("GET", release.installer_url) as response:
                    response.raise_for_status()
                    total = int(response.headers.get("content-length") or release.size or 0)
                    done = 0
                    with target.open("wb") as handle:
                        for chunk in response.iter_bytes(1 << 17):
                            handle.write(chunk)
                            done += len(chunk)
                            if total:
                                with self._lock:
                                    self.progress = min(done / total, 1.0)
                step = "download of the signature"
                signature = client.get(release.signature_url)
                signature.raise_for_status()
            step = "signature check"
            if not verify_signature(target, signature.text):
                raise ValueError("the installer is not signed with the Leadroom release key")
            with self._lock:
                self._staged = target
                self.progress = 1.0
                self.phase = self.READY
            self._log(f"downloaded and signature checked: {target}")
        except Exception as exc:  # noqa: BLE001 - every failure is reported to the user
            with contextlib.suppress(OSError):
                target.unlink(missing_ok=True)
            self._log(f"failed: {step}: {type(exc).__name__}: {exc}")
            with self._lock:
                self.phase = self.FAILED
                self.error = f"The update could not be downloaded ({step}). Try again later."

    # Installing -------------------------------------------------------------------------
    def installer_arguments(self) -> list[str]:
        return [
            "/SILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            "/CLOSEAPPLICATIONS",
            # Open the new version when the files are in place.
            "/RELAUNCH=1",
            # An update changes Leadroom only: it never installs or downloads anything else.
            "/INSTALL_OLLAMA=0",
            "/DOWNLOAD_MODEL=0",
            "/SETUP_LOCAL_DATA=0",
            f"/LOG={self.installer_log}",
        ]

    @staticmethod
    def installer_environment() -> dict[str, str]:
        """The environment for Setup and the app it reopens: none of this process's own state."""
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("LEADROOM_LAUNCH_TOKEN", "LEAD_SCRAPER_FRONTEND_DIR", "_PYI", "_MEI"))
        }
        # The relaunched Leadroom.exe must unpack its own files, not look for this one's.
        environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        return environment

    def install(self, quit_app: Callable[[], None]) -> dict[str, Any]:
        with self._lock:
            if self.phase != self.READY or self._staged is None or self.release is None:
                return self.snapshot()
            staged, release = self._staged, self.release
        # Written first: if Setup fails after this copy quits, the next copy to open learns it.
        self.home.mkdir(parents=True, exist_ok=True)
        self.installer_log.parent.mkdir(parents=True, exist_ok=True)
        self.pending_file.write_text(
            json.dumps({"version": release.version, "page": release.page, "started": datetime.now(UTC).isoformat()}),
            encoding="utf-8",
        )
        try:
            flags = 0
            if sys.platform == "win32":
                flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            subprocess.Popen(  # noqa: S603 - a signature-checked installer
                [str(staged), *self.installer_arguments()],
                env=self.installer_environment(),
                creationflags=flags,
                close_fds=True,
            )
        except OSError as exc:
            self.pending_file.unlink(missing_ok=True)
            self._log(f"failed: start of the installer: {exc}")
            with self._lock:
                self.phase = self.FAILED
                self.error = "The installer could not be started."
            return self.snapshot()
        self._log(f"installer started for {release.version}; quitting for it")
        quit_app()
        return self.snapshot()

    def open_page(self) -> None:
        page = self.release.page if self.release else RELEASES_PAGE
        try:
            if sys.platform == "win32":
                os.startfile(page)  # type: ignore[attr-defined]  # noqa: S606
            else:
                webbrowser.open(page)
        except OSError as exc:
            self._log(f"could not open {page}: {exc}")
