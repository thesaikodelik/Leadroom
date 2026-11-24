from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app import updater as updater_module
from app.updater import (
    INSTALLER_NAME,
    PUBLIC_KEY,
    Updater,
    is_newer,
    newest_release,
    signed_message,
    verify_signature,
)

ROOT = Path(__file__).resolve().parents[1]


def _public(key: Ed25519PrivateKey) -> str:
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode()


def _sign(path: Path, key: Ed25519PrivateKey) -> str:
    return base64.b64encode(key.sign(signed_message(path))).decode()


def _release(tag: str, *, assets=(INSTALLER_NAME, INSTALLER_NAME + ".sig"), **extra) -> dict:
    return {
        "tag_name": tag,
        "html_url": f"https://github.com/thesaikodelik/Leadroom/releases/tag/{tag}",
        "draft": False,
        "prerelease": False,
        "body": f"Notes for {tag}",
        "assets": [
            {"name": name, "browser_download_url": f"https://downloads.test/{tag}/{name}", "size": 10}
            for name in assets
        ],
        **extra,
    }


def test_versions_compare_number_by_number() -> None:
    assert is_newer("0.1.10", "0.1.9")
    assert is_newer("0.2.0", "0.1.99")
    assert is_newer("v1.0.0", "0.9.9")
    assert not is_newer("0.1.3", "0.1.3")
    assert not is_newer("0.1.2", "0.1.3")
    assert is_newer("0.1.3", "0.0.0+dev")


def test_newest_release_skips_drafts_prereleases_and_unsigned_releases() -> None:
    feed = [
        _release("v0.1.9", draft=True),
        _release("v0.1.8", prerelease=True),
        _release("v0.1.7", assets=(INSTALLER_NAME,)),
        _release("v0.1.5"),
        _release("v0.1.4"),
        _release("v0.1.2"),
        _release("other-0.9.0"),
    ]
    release = newest_release(feed, "0.1.3")
    assert release is not None
    assert release.version == "0.1.5"
    assert release.installer_url.endswith("/v0.1.5/Leadroom-Setup.exe")
    assert release.signature_url.endswith("/v0.1.5/Leadroom-Setup.exe.sig")
    assert newest_release(feed, "0.1.5") is None
    assert newest_release({"message": "Not Found"}, "0.1.3") is None


def test_signature_check_accepts_only_the_trusted_key_and_untouched_files(tmp_path: Path) -> None:
    installer = tmp_path / INSTALLER_NAME
    installer.write_bytes(b"installer bytes" * 1000)
    key, other = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    signature = _sign(installer, key)

    assert verify_signature(installer, signature, _public(key))
    assert not verify_signature(installer, signature, _public(other))
    assert not verify_signature(installer, _sign(installer, other), _public(key))
    assert not verify_signature(installer, "not base64!", _public(key))
    installer.write_bytes(b"installer bytes" * 1000 + b"tampered")
    assert not verify_signature(installer, signature, _public(key))


def test_release_public_key_is_a_valid_ed25519_key() -> None:
    assert len(base64.b64decode(PUBLIC_KEY)) == 32


def _updater(tmp_path: Path, handler, *, version="0.1.3", installed=True) -> Updater:
    app_folder = tmp_path / "app"
    app_folder.mkdir(exist_ok=True)
    if installed:
        (app_folder / "unins000.exe").write_bytes(b"")
    transport = httpx.MockTransport(handler)
    return Updater(
        tmp_path / "home",
        version=version,
        executable=app_folder / "Leadroom.exe",
        frozen=True,
        client_factory=lambda: httpx.Client(transport=transport, follow_redirects=True),
    )


def test_update_is_found_downloaded_and_checked(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(updater_module.tempfile, "gettempdir", lambda: str(tmp_path / "temp"))
    key = Ed25519PrivateKey.generate()
    monkeypatch.setattr(updater_module, "trusted_public_key", lambda: _public(key))
    payload = b"new installer" * 5000
    staged = tmp_path / "signed.exe"
    staged.write_bytes(payload)
    signature = _sign(staged, key)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.github.com":
            return httpx.Response(200, json=[_release("v0.1.4")])
        if request.url.path.endswith(".sig"):
            return httpx.Response(200, text=signature)
        return httpx.Response(200, content=payload, headers={"content-length": str(len(payload))})

    updater = _updater(tmp_path, handler)
    assert updater.check(asked=True) == "found"
    assert updater.snapshot()["phase"] == "available"
    assert updater.snapshot()["version"] == "0.1.4"

    updater.download()
    deadline = time.monotonic() + 10
    while updater.phase == "downloading" and time.monotonic() < deadline:
        time.sleep(0.05)
    assert updater.phase == "ready", updater.error
    assert updater.progress == 1.0


def test_tampered_download_is_refused_and_removed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(updater_module.tempfile, "gettempdir", lambda: str(tmp_path / "temp"))
    key = Ed25519PrivateKey.generate()
    monkeypatch.setattr(updater_module, "trusted_public_key", lambda: _public(key))
    original = tmp_path / "signed.exe"
    original.write_bytes(b"genuine")
    signature = _sign(original, key)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.github.com":
            return httpx.Response(200, json=[_release("v0.1.4")])
        if request.url.path.endswith(".sig"):
            return httpx.Response(200, text=signature)
        return httpx.Response(200, content=b"replaced on the way")

    updater = _updater(tmp_path, handler)
    updater.check(asked=True)
    updater.download()
    deadline = time.monotonic() + 10
    while updater.phase == "downloading" and time.monotonic() < deadline:
        time.sleep(0.05)
    assert updater.phase == "failed"
    assert "signature check" in updater.error
    assert not list((tmp_path / "temp" / "leadroom-update").glob("*.exe"))


def test_a_private_or_unreachable_feed_is_not_an_error(tmp_path: Path) -> None:
    updater = _updater(tmp_path, lambda request: httpx.Response(404, json={"message": "Not Found"}))
    assert updater.check(asked=True) == "no_answer"
    assert updater.phase == "idle"
    assert updater.error == ""


def test_automatic_checks_are_at_most_hourly(tmp_path: Path) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=[])

    updater = _updater(tmp_path, handler)
    assert updater.check() == "up_to_date"
    assert updater.check() is None
    assert updater.check(asked=True) == "up_to_date"
    assert len(calls) == 2


def test_a_copy_not_installed_by_setup_is_sent_to_the_release_page(tmp_path: Path, monkeypatch) -> None:
    opened = []
    updater = _updater(tmp_path, lambda request: httpx.Response(200, json=[_release("v0.1.4")]), installed=False)
    monkeypatch.setattr(updater, "open_page", lambda: opened.append(True))
    updater.check(asked=True)
    updater.download()
    assert opened == [True]
    assert updater.phase == "available"


def test_unfinished_update_is_reported_by_the_old_version(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "update-pending.json").write_text(json.dumps({"version": "0.1.4", "page": "https://example.test/r"}))

    updater = _updater(tmp_path, lambda request: httpx.Response(200, json=[]), version="0.1.3")

    assert updater.phase == "failed"
    assert "0.1.4 did not finish" in updater.error
    assert not (home / "update-pending.json").exists()


def test_arrived_update_clears_its_note(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "update-pending.json").write_text(json.dumps({"version": "0.1.4", "page": "x"}))

    updater = _updater(tmp_path, lambda request: httpx.Response(200, json=[]), version="0.1.4")

    assert updater.phase == "idle"
    assert not (home / "update-pending.json").exists()


def test_install_records_the_update_runs_setup_quietly_and_quits(tmp_path: Path, monkeypatch) -> None:
    launched = []
    quits = []
    monkeypatch.setattr(
        updater_module.subprocess, "Popen", lambda args, **kwargs: launched.append((args, kwargs))
    )
    updater = _updater(tmp_path, lambda request: httpx.Response(200, json=[]))
    staged = tmp_path / "Leadroom-Setup-0.1.4.exe"
    staged.write_bytes(b"x")
    updater.release = updater_module.Release("0.1.4", "https://example.test/r", "", "")
    updater._staged = staged
    updater.phase = updater.READY
    monkeypatch.setenv("LEAD_SCRAPER_FRONTEND_DIR", r"C:\Temp\_MEI123\frontend\dist")
    monkeypatch.setenv("LEADROOM_LAUNCH_TOKEN", "secret")

    updater.install(lambda: quits.append(True))

    args, kwargs = launched[0]
    assert args[0] == str(staged)
    for flag in ("/SILENT", "/SUPPRESSMSGBOXES", "/CLOSEAPPLICATIONS", "/RELAUNCH=1", "/INSTALL_OLLAMA=0", "/DOWNLOAD_MODEL=0", "/SETUP_LOCAL_DATA=0"):
        assert flag in args
    # The reopened app must not inherit this copy's unpacked folder or its session token.
    assert "LEAD_SCRAPER_FRONTEND_DIR" not in kwargs["env"]
    assert "LEADROOM_LAUNCH_TOKEN" not in kwargs["env"]
    assert kwargs["env"]["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
    assert json.loads((tmp_path / "home" / "update-pending.json").read_text())["version"] == "0.1.4"
    assert quits == [True]


def test_installer_relaunches_only_for_the_updater() -> None:
    definition = (ROOT / "installer" / "Leadroom.iss").read_text(encoding="utf-8")
    assert "Check: RelaunchRequested" in definition
    assert "ParamEnabled('RELAUNCH', False)" in definition
    # Other quiet installs (scripts, the clean-machine test) still do not open the app.
    assert 'Flags: nowait postinstall skipifsilent' in definition


def test_installer_removes_earlier_installs_registered_under_another_id() -> None:
    definition = (ROOT / "installer" / "Leadroom.iss").read_text(encoding="utf-8")
    assert "RemoveEarlierInstalls;" in definition
    assert "'/VERYSILENT /SUPPRESSMSGBOXES /NORESTART'" in definition
    # No earlier AppId is written into the repository; entries are found by their name.
    assert "CompareText(Copy(DisplayName, 1, 8), 'Leadroom')" in definition


@pytest.mark.parametrize("script", ["setup-local-data.ps1", "import-osm.ps1"])
def test_cluster_lookup_does_not_cut_off_wsl(script: str) -> None:
    text = (ROOT / "scripts" / script).read_text(encoding="utf-8")
    assert "pg_lsclusters --no-header | Select-Object" not in text
    assert "$clusters = @(wsl -d Ubuntu -u root -- pg_lsclusters --no-header)" in text


def test_reinstall_keeps_an_existing_map_index() -> None:
    text = (ROOT / "scripts" / "install-bootstrap.ps1").read_text(encoding="utf-8")
    assert "if (Test-ExistingLocalIndex) {" in text
    assert '"Full Local database setup" -CaptureOutput' in text
    assert '"OpenStreetMap import" -CaptureOutput' in text


def test_quiet_update_waits_for_the_app_and_reopens_it_if_setup_fails() -> None:
    definition = (ROOT / "installer" / "Leadroom.iss").read_text(encoding="utf-8")
    # A quiet Setup cannot close a window-less Leadroom and would abort; it waits instead.
    assert "(WizardSilent or RelaunchRequested) and not WaitForAppToClose" in definition
    # An update that does not complete reopens the installed version.
    assert "procedure DeinitializeSetup;" in definition
    assert "if InstallFinished or not RelaunchRequested then Exit;" in definition
