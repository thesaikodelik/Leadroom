param(
    [Parameter(Mandatory = $true)]
    [string]$Version,
    # Only for test builds: an update key other than the release key in app/updater.py.
    [string]$UpdatePublicKey = ""
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")

# The version the in-app updater compares against, built into Leadroom.exe.
$buildInfo = Join-Path $root "app\_build_info.py"
$lines = @(
    "# Written by scripts/package.ps1 for each build; not kept in the repository.",
    "VERSION = `"$Version`"",
    "UPDATE_PUBLIC_KEY = `"$UpdatePublicKey`""
)
[IO.File]::WriteAllLines($buildInfo, $lines, [Text.UTF8Encoding]::new($false))

Push-Location (Join-Path $root "frontend")
try { & npm run build } finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& (Join-Path $root ".venv\Scripts\python.exe") -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --noconsole `
    --name Leadroom `
    --icon "assets/leadroom-icon.ico" `
    --add-data "frontend/dist;frontend/dist" `
    --add-data "assets/leadroom-icon.ico;assets" `
    --hidden-import app._build_info `
    --collect-data tldextract `
    --collect-data undetected_playwright `
    --collect-all tiktoken `
    --collect-all psycopg `
    --collect-all psycopg_binary `
    --collect-all webview `
    --hidden-import webview.platforms.edgechromium `
    --hidden-import tiktoken_ext.openai_public `
    --collect-all scrapling `
    --collect-all curl_cffi `
    --collect-all browserforge `
    --collect-all apify_fingerprint_datapoints `
    --collect-all scrapegraphai `
    run_desktop.py
exit $LASTEXITCODE
