param(
    # Defaults to the version in pyproject.toml.
    [string]$Version = "",
    [switch]$SkipAppBuild,
    # A release must carry the update signature, or installed copies cannot update to it.
    [switch]$RequireSignature,
    # Test builds only: sign with a throwaway key file and build its public key in.
    [string]$UpdateKeyFile = ""
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$dist = Join-Path $root "dist"
$build = Join-Path $root "build"
$portableStage = Join-Path $build "Leadroom-Portable"
$portableArchive = Join-Path $dist "Leadroom-Portable.zip"
$python = Join-Path $root ".venv\Scripts\python.exe"
$signer = Join-Path $PSScriptRoot "sign_update.py"

if ([string]::IsNullOrWhiteSpace($Version)) {
    $match = Select-String -Path (Join-Path $root "pyproject.toml") -Pattern '^version = "([^"]+)"'
    if (-not $match) { throw "No version found in pyproject.toml." }
    $Version = $match.Matches[0].Groups[1].Value
}
Write-Host "Building Leadroom $Version"

$updatePublicKey = ""
$signerKeyArguments = @()
if ($UpdateKeyFile) {
    $signerKeyArguments = @("--key-file", $UpdateKeyFile)
    $updatePublicKey = (& $python $signer @signerKeyArguments public).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Could not read the test update key." }
}

if (-not $SkipAppBuild) {
    & (Join-Path $PSScriptRoot "package.ps1") -Version $Version -UpdatePublicKey $updatePublicKey
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
if (-not (Test-Path (Join-Path $dist "Leadroom.exe"))) {
    throw "dist\Leadroom.exe is missing. Run scripts\package.ps1 first."
}

New-Item -ItemType Directory -Force -Path $dist, $build | Out-Null
$licences = Join-Path $build "THIRD_PARTY_LICENSES.txt"
& (Join-Path $root ".venv\Scripts\python.exe") (Join-Path $PSScriptRoot "collect_licenses.py") $licences
if ($LASTEXITCODE -ne 0) { throw "Could not collect third-party licences." }
if (Test-Path -LiteralPath $portableStage) {
    $resolved = (Resolve-Path -LiteralPath $portableStage).Path
    if (-not $resolved.StartsWith($build, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe portable staging path: $resolved"
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $portableStage | Out-Null
Copy-Item (Join-Path $dist "Leadroom.exe") $portableStage
Copy-Item (Join-Path $root "LICENSE") $portableStage
Copy-Item (Join-Path $root "THIRD_PARTY_NOTICES.md") $portableStage
Copy-Item $licences $portableStage
New-Item -ItemType Directory -Force -Path (Join-Path $portableStage "licenses") | Out-Null
Copy-Item (Join-Path $root "licenses\GPL-3.0.txt") (Join-Path $portableStage "licenses")
Copy-Item (Join-Path $root "README.md") $portableStage
if (Test-Path -LiteralPath $portableArchive) { Remove-Item -LiteralPath $portableArchive -Force }
Compress-Archive -Path (Join-Path $portableStage "*") -DestinationPath $portableArchive -CompressionLevel Optimal

$isccCandidates = @(
    (Get-Command ISCC.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
$iscc = $isccCandidates | Select-Object -First 1
if (-not $iscc) {
    throw "Inno Setup 6 was not found. Install it with: winget install JRSoftware.InnoSetup"
}
& $iscc "/DAppVersion=$Version" (Join-Path $root "installer\Leadroom.iss")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$setup = Join-Path $dist "Leadroom-Setup.exe"
$signature = "$setup.sig"
if (Test-Path -LiteralPath $signature) { Remove-Item -LiteralPath $signature -Force }
$releaseKey = Join-Path $env:USERPROFILE ".leadroom\update-signing.key"
if ($UpdateKeyFile -or (Test-Path -LiteralPath $releaseKey)) {
    & $python $signer @signerKeyArguments sign $setup
    if ($LASTEXITCODE -ne 0) { throw "Could not sign the installer for the in-app updater." }
} elseif ($RequireSignature) {
    throw "No update signing key on this computer; installed copies could not update to this build."
} else {
    Write-Warning "No update signing key: Leadroom-Setup.exe is not signed for the in-app updater."
}

$artifacts = @(
    $setup,
    $portableArchive
)
$checksumLines = foreach ($artifact in $artifacts) {
    if (-not (Test-Path -LiteralPath $artifact)) { throw "Missing release artifact: $artifact" }
    $hash = Get-FileHash -Algorithm SHA256 -LiteralPath $artifact
    "{0}  {1}" -f $hash.Hash.ToLowerInvariant(), (Split-Path $artifact -Leaf)
}
$checksumLines | Set-Content -LiteralPath (Join-Path $dist "checksums.txt") -Encoding ASCII

Write-Host "Release artifacts are ready:"
$listed = $artifacts + (Join-Path $dist "checksums.txt")
if (Test-Path -LiteralPath $signature) { $listed += $signature }
Get-Item -LiteralPath $listed |
    Select-Object Name, Length, LastWriteTime
