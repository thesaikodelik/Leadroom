# Windows Packaging

Leadroom currently targets 64-bit Windows 10 and Windows 11. The installer is a local release candidate until clean-machine validation and the binary dependency-licence review are complete.

## Build Requirements

- Python 3.12 or 3.13 with `requirements-dev.txt` installed
- Node.js 22+
- Inno Setup 6 (`winget install --id JRSoftware.InnoSetup --exact --source winget`)

## Build All Artifacts

```powershell
.\scripts\build-release.ps1
```

The version comes from `pyproject.toml` unless `-Version` is given, and is built into the app for the in-app updater. This produces ignored local artifacts in `dist`:

- `Leadroom-Setup.exe`
- `Leadroom-Setup.exe.sig`, when the update signing key is on this computer (see below)
- `Leadroom-Portable.zip`
- `checksums.txt`

The installer contains the application executable, licence and third-party notices, bootstrap scripts, and optional Full Local data scripts. Large models and map data are fetched only after explicit selection in the installer.

## Installer Experience

The Wizard provides:

1. Standard or Full Local installation mode
2. Separate workspace-data and large-download folders
3. Optional WebView2 and Ollama installation through `winget`, falling back to the vendors' official installers when `winget` is missing or fails
4. Optional verified `ollama pull` for `llama3.2:3b`
5. Optional WSL/PostgreSQL/PostGIS/OpenStreetMap setup for Full Local
6. Start Menu and optional Desktop shortcuts

The preparation page reports the active component while bootstrap runs. Ollama model downloads stream their current layer percentage and transferred size into the installer; package-manager and Full Local operations show named stage progress when their underlying tools do not expose a reliable overall percentage. Cancel remains available during preparation, signals active model downloads to stop, and lets Setup roll back the installation. Detailed events remain available in `%LOCALAPPDATA%\Leadroom\logs\install.log`.

The model checkbox is disabled while Ollama is neither installed nor selected; a silent install that requests a model without Ollama skips the model instead of failing. When Setup installs Ollama itself, it points `OLLAMA_MODELS` at the selected downloads folder before installation and restarts the Ollama background app afterwards, so Leadroom finds the downloaded model without a sign-out.

Upgrades preserve an existing `storage.json`. Uninstall removes application files and asks whether workspace data and downloads should be retained.

Setup also removes any earlier Leadroom that Windows lists under a different AppId (earlier builds used another one), quietly and only after the prerequisites are ready, so a failed preparation leaves the earlier version working. Workspace data, models and the map index are outside the program folder and are kept.

When Full Local is selected and WSL already holds an imported index with incremental updates, Setup keeps it and only refreshes the update service; a reinstall never rebuilds the index. The output of the Full Local helper scripts is written to `install.log`, and the line that stopped them is shown in Setup's error message.

## Silent Test Parameters

```powershell
.\dist\Leadroom-Setup.exe `
  /VERYSILENT /SUPPRESSMSGBOXES /NORESTART `
  /DIR="D:\Apps\Leadroom" `
  /DATAROOT="D:\LeadroomData\workspace" `
  /DOWNLOADSROOT="D:\LeadroomData\downloads" `
  /INSTALL_WEBVIEW=1 /INSTALL_OLLAMA=1 /DOWNLOAD_MODEL=1
```

Other parameters are `/INSTALLMODE=full`, `/SETUP_LOCAL_DATA=1`, `/RELAUNCH=1` (opens Leadroom when Setup finishes; used by the in-app updater), and the test-only `/FORCE_STORAGE=1`.

Setting the environment variable `LEADROOM_SETUP_DISABLE_WINGET=1` before running Setup simulates a computer without `winget` and exercises the direct-download fallback.

## Smoke Test

```powershell
.\scripts\test-installer.ps1
.\scripts\test-installer-cancel.ps1
```

The smoke test temporarily backs up the current Leadroom bootstrap folder, silently installs to `build`, starts the installed executable on a dedicated localhost port, checks `/api/v1/health`, runs the uninstaller, and restores the original bootstrap folder and Ollama environment setting.

The cancellation test begins a model download in an isolated folder, activates the installer's `Cancel setup` button, and verifies that Setup exits unsuccessfully, the bootstrap process stops, and no application executable remains installed.

## In-App Updates

Installed copies look for a newer release once an hour (`app/updater.py`). They read the repository's GitHub releases list, take the newest release that is not a draft or pre-release, has a `v<version>` tag, and carries both `Leadroom-Setup.exe` and `Leadroom-Setup.exe.sig`, and offer it in the sidebar. The user downloads it, the app checks the signature, and **Restart now** runs Setup with `/SILENT /RELAUNCH=1` (and no extra components) before quitting; Setup replaces the files and opens the new version.

- Leadroom has no code-signing certificate, so updates are signed with an Ed25519 key instead. The app installs only an installer whose `.sig` verifies against the public key in `app/updater.py`.
- The private key is kept in `%USERPROFILE%\.leadroom\update-signing.key`, encrypted with Windows DPAPI for the maintainer's account, and never in the repository. `python scripts/sign_update.py export` prints it for a backup (keep it in a password manager); `import` restores it on another computer. **Without it, installed copies can never update again.**
- `build-release.ps1` signs `Leadroom-Setup.exe` automatically when the key is present; `-RequireSignature` makes a missing key an error.
- `logs\update.log` and `logs\update-installer.log` in `%LOCALAPPDATA%\Leadroom` record every step. If Setup fails after the app has quit, the old version opens again with an explanation, because the app writes `update-pending.json` before quitting.
- A file `update-feed.txt` in `%LOCALAPPDATA%\Leadroom` holding an address points the app at a test feed; what it offers must still be signed and newer.
- GitHub answers anonymous release-list requests only for public repositories, so updates are offered once the repository is public.

## Publishing a Release

1. Bump `version` in `pyproject.toml`.
2. Run the **Installer clean-machine test** workflow and confirm both jobs pass. It also installs a stand-in earlier version, and updates the installed app in place to a newer test build signed with a throwaway key.
3. Build with `scripts/build-release.ps1 -RequireSignature`; it regenerates `THIRD_PARTY_LICENSES.txt` and signs the installer.
4. Tag the commit `v<version>` and attach `Leadroom-Setup.exe`, `Leadroom-Setup.exe.sig`, `Leadroom-Portable.zip`, and `checksums.txt` to a GitHub Release (not a pre-release, or installed copies will not see it) whose notes link to the source at that tag.

The licensing basis for binary releases is recorded in `DEPENDENCY_LICENSES.md`. A fresh Full Local import on a clean machine has not been tested yet.
