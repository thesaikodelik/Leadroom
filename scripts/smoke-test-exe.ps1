param(
    [Parameter(Mandatory = $true)]
    [string]$Executable,
    [string]$Version = "",
    [int]$TimeoutSeconds = 120
)

# Starts a freshly built Leadroom.exe without a window, in a throwaway data folder,
# and waits for its health endpoint. A module PyInstaller left out only shows up when
# the exe starts, so a build is not done until this passes.

$ErrorActionPreference = "Stop"
$home_ = Join-Path ([IO.Path]::GetTempPath()) ("leadroom-smoke-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force $home_ | Out-Null

$listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
$listener.Start()
$port = $listener.LocalEndpoint.Port
$listener.Stop()

$saved = @{}
$settings = @{
    LEADROOM_BOOTSTRAP_ROOT = $home_
    LEADROOM_PORT = "$port"
    LEAD_SCRAPER_NO_BROWSER = "1"
}
foreach ($name in $settings.Keys) {
    $saved[$name] = [Environment]::GetEnvironmentVariable($name)
    [Environment]::SetEnvironmentVariable($name, $settings[$name])
}

$process = $null
try {
    $process = Start-Process -FilePath $Executable -PassThru -WindowStyle Hidden
    $null = $process.Handle
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $health = $null
    while ((Get-Date) -lt $deadline -and -not $process.HasExited) {
        try {
            $health = Invoke-RestMethod "http://127.0.0.1:$port/api/v1/health" -TimeoutSec 3
            break
        } catch {
            Start-Sleep -Milliseconds 750
        }
    }
    if (-not $health) {
        $log = Join-Path $home_ "logs\leadroom.log"
        if (Test-Path -LiteralPath $log) { Get-Content -LiteralPath $log -Tail 30 | Write-Host }
        if ($process.HasExited) {
            throw "Leadroom.exe exited with code $($process.ExitCode) before it answered."
        }
        throw "Leadroom.exe did not answer within $TimeoutSeconds seconds (a startup error dialog is the usual cause)."
    }
    if ($Version -and $health.version -ne $Version) {
        throw "Leadroom.exe reports version $($health.version), expected $Version."
    }
    Write-Host "Smoke test passed: Leadroom.exe $($health.version) answered on port $port."
} finally {
    if ($process -and -not $process.HasExited) {
        & "$env:SystemRoot\System32\taskkill.exe" /PID $process.Id /T /F 2>$null | Out-Null
        $process.WaitForExit(10000) | Out-Null
    }
    foreach ($name in $saved.Keys) { [Environment]::SetEnvironmentVariable($name, $saved[$name]) }
    Start-Sleep -Milliseconds 500
    Remove-Item -LiteralPath $home_ -Recurse -Force -ErrorAction SilentlyContinue
}
