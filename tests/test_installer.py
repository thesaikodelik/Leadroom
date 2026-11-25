from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(os.name != "nt", reason="Windows installer scripts")
def test_bootstrap_plan_is_non_destructive_and_serializable(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "install-bootstrap.ps1"
    data_root = tmp_path / "workspace"
    downloads_root = tmp_path / "downloads"
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Mode",
            "Standard",
            "-InstallRoot",
            str(ROOT),
            "-DataRoot",
            str(data_root),
            "-DownloadsRoot",
            str(downloads_root),
            "-InstallWebView",
            "-InstallOllama",
            "-DownloadModel",
            "-PlanOnly",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    plan = json.loads(result.stdout)
    assert plan["mode"] == "Standard"
    assert plan["model"] == "llama3.2:3b"
    assert plan["install_webview"] is True
    assert plan["install_ollama"] is True
    assert plan["download_model"] is True
    assert not data_root.exists()
    assert not downloads_root.exists()


def test_inno_setup_defines_install_and_uninstall_workflows() -> None:
    definition = (ROOT / "installer" / "Leadroom.iss").read_text(encoding="utf-8")
    assert "PrivilegesRequired=lowest" in definition
    assert "ArchitecturesAllowed=x64compatible" in definition
    assert "install-bootstrap.ps1" in definition
    assert "clean-install-state.ps1" in definition
    assert "CreateInputDirPage" in definition
    assert "Leadroom-Setup" in definition
    assert "-ProcessPath" in definition
    assert "IsProcessRunning(BootstrapProcessId)" in definition
    assert "stopped unexpectedly" in definition
    # Fresh Windows installs can take well over ten seconds to start PowerShell.
    assert "ProcessWaitCycles >= 2400" in definition


def test_bootstrap_long_running_children_are_cancellable() -> None:
    definition = (ROOT / "scripts" / "install-bootstrap.ps1").read_text(encoding="utf-8")
    assert "[string]$ProcessPath" in definition
    assert "Invoke-CancellableProcess $winget" in definition
    assert "Stop-InstallerProcessTree $process" in definition
    assert 'Invoke-CancellableProcess $powershell $setupArguments' in definition
    assert 'Invoke-CancellableProcess $powershell $importArguments' in definition
    assert "$reader.ReadLineAsync()" in definition
    assert "while (-not $readTask.Wait(250))" in definition
    assert "while (-not $reader.EndOfStream)" not in definition
    assert "while (-not $sendTask.Wait(250))" in definition
    assert "Stop-InstallerProcessTree $started" in definition
    assert "Assert-Capacity $ubuntuStorage 30GB" in definition


def test_bootstrap_reads_exit_codes_of_redirected_children() -> None:
    # Windows PowerShell leaves ExitCode empty for a Start-Process child whose handle
    # was not opened before it exited, so a child that succeeded looked like a failure.
    definition = (ROOT / "scripts" / "install-bootstrap.ps1").read_text(encoding="utf-8")
    handle = definition.index("$null = $process.Handle")
    assert definition.index("-RedirectStandardOutput $outputPath") < handle
    assert handle < definition.index("while (-not $process.WaitForExit(250))")


@pytest.mark.parametrize(
    "script_name",
    ["setup-local-data.ps1", "import-osm.ps1", "setup-local-updates.ps1"],
)
def test_full_local_scripts_fail_fast_on_native_command_errors(script_name: str) -> None:
    definition = (ROOT / "scripts" / script_name).read_text(encoding="utf-8")
    assert "function Assert-NativeSuccess" in definition
    assert definition.count("Assert-NativeSuccess") >= 3


@pytest.mark.skipif(os.name != "nt", reason="Windows cleanup script")
def test_cleanup_refuses_to_run_without_confirmation() -> None:
    script = ROOT / "scripts" / "clean-install-state.ps1"
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Cleanup is destructive" in (result.stdout + result.stderr)


def test_bootstrap_falls_back_when_winget_is_unavailable() -> None:
    definition = (ROOT / "scripts" / "install-bootstrap.ps1").read_text(encoding="utf-8")
    assert "https://ollama.com/download/OllamaSetup.exe" in definition
    assert "https://go.microsoft.com/fwlink/p/?LinkId=2124703" in definition
    assert "Falling back to a direct download" in definition
    assert "SecurityProtocolType]::Tls12" in definition
    assert 'LEADROOM_SETUP_DISABLE_WINGET' in definition
    # A model request without Ollama is skipped instead of failing setup.
    assert "cannot be downloaded because Ollama is not installed" not in definition
    assert "$DownloadModel = $false" in definition
    # The Ollama tray must not stay inside Setup's process tree.
    assert "-ClassName Win32_Process -MethodName Create" in definition


def test_installer_links_model_checkbox_to_ollama() -> None:
    definition = (ROOT / "installer" / "Leadroom.iss").read_text(encoding="utf-8")
    assert "OnClickCheck := @DependencyClickCheck" in definition
    assert "ItemEnabled[2] := ModelAvailable" in definition


@pytest.mark.skipif(os.name != "nt", reason="Windows installer scripts")
def test_bootstrap_storage_file_is_readable_by_the_app(tmp_path: Path) -> None:
    """Setup's storage.json must load in the app (regression: PowerShell UTF-8 BOM)."""
    from app.storage import load_storage_config

    local_app_data = tmp_path / "localappdata"
    local_app_data.mkdir()
    data_root = tmp_path / "workspace"
    downloads_root = tmp_path / "downloads"
    env = {**os.environ, "LOCALAPPDATA": str(local_app_data)}
    subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "scripts" / "install-bootstrap.ps1"),
            "-Mode",
            "Standard",
            "-InstallRoot",
            str(tmp_path / "app"),
            "-DataRoot",
            str(data_root),
            "-DownloadsRoot",
            str(downloads_root),
            "-InstallWebView",
            "-ForceStorage",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    bootstrap_root = local_app_data / "Leadroom"
    config_path = bootstrap_root / "storage.json"
    assert not config_path.read_bytes().startswith(b"\xef\xbb\xbf")
    config = load_storage_config(config_path, bootstrap_root)
    assert Path(config["data_root"]) == data_root
    assert Path(config["downloads_root"]) == downloads_root


def test_setup_icon_is_distinct_from_the_app_icon() -> None:
    definition = (ROOT / "installer" / "Leadroom.iss").read_text(encoding="utf-8")
    assert r"SetupIconFile=..\assets\leadroom-setup.ico" in definition
    app_icon = (ROOT / "assets" / "leadroom-icon.ico").read_bytes()
    setup_icon = (ROOT / "assets" / "leadroom-setup.ico").read_bytes()
    assert app_icon != setup_icon
    for line in definition.splitlines():
        if line.startswith(("WizardImageFile=", "WizardSmallImageFile=")):
            for image in line.split("=", 1)[1].split(","):
                assert (ROOT / "installer" / image).is_file(), image
