param(
    [ValidateSet("Standard", "FullLocal")]
    [string]$Mode = "Standard",
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot,
    [string]$HelperRoot,
    [string]$ResourceRoot,
    [Parameter(Mandatory = $true)]
    [string]$DataRoot,
    [Parameter(Mandatory = $true)]
    [string]$DownloadsRoot,
    [string]$Model = "llama3.2:3b",
    [string]$OsmRegion = "great-britain",
    [switch]$InstallWebView,
    [switch]$InstallOllama,
    [switch]$DownloadModel,
    [switch]$SetupLocalData,
    [switch]$ForceStorage,
    [switch]$PlanOnly,
    [string]$StatusPath,
    [string]$CompletionPath,
    [string]$CancelPath,
    [string]$ProcessPath
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "Continue"
Add-Type -AssemblyName System.Net.Http
# Windows PowerShell 5.1 on older Windows 10 builds may still default to TLS 1.0,
# which modern download hosts reject. Enable TLS 1.2 (and 1.3 when available).
try {
    $protocols = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $tls13 = [Enum]::GetNames([Net.SecurityProtocolType]) -contains "Tls13"
    if ($tls13) { $protocols = $protocols -bor [Net.SecurityProtocolType]::Tls13 }
    [Net.ServicePointManager]::SecurityProtocol = $protocols
} catch {}

$WebViewDownloadUrl = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
$OllamaDownloadUrl = "https://ollama.com/download/OllamaSetup.exe"

$bootstrapRoot = Join-Path $env:LOCALAPPDATA "Leadroom"
$logDirectory = Join-Path $bootstrapRoot "logs"
$logPath = Join-Path $logDirectory "install.log"
$modelDirectoryChanged = $false
$previousModelDirectory = $null

if (-not [string]::IsNullOrWhiteSpace($ProcessPath)) {
    [IO.File]::WriteAllText(
        $ProcessPath,
        [string]$PID,
        [Text.UTF8Encoding]::new($false)
    )
}

function Write-InstallerStatus(
    [int]$Percent,
    [string]$Title,
    [string]$Detail
) {
    if ([string]::IsNullOrWhiteSpace($StatusPath)) { return }
    $safeTitle = ($Title -replace "[\r\n]+", " ").Trim()
    $safeDetail = ($Detail -replace "[\r\n]+", " ").Trim()
    $lines = @([string]$Percent, $safeTitle, $safeDetail)
    for ($attempt = 0; $attempt -lt 5; $attempt++) {
        try {
            [IO.File]::WriteAllLines(
                $StatusPath,
                $lines,
                [Text.UTF8Encoding]::new($false)
            )
            return
        } catch [IO.IOException] {
            Start-Sleep -Milliseconds (20 * ($attempt + 1))
        }
    }
    # Progress is advisory; a transient UI-file collision must not abort setup.
}

function Complete-InstallerBootstrap(
    [int]$ExitCode,
    [string]$Message = ""
) {
    if (-not [string]::IsNullOrWhiteSpace($CompletionPath)) {
        $safeMessage = ($Message -replace "[\r\n]+", " ").Trim()
        @([string]$ExitCode, $safeMessage) |
            Set-Content -LiteralPath $CompletionPath -Encoding UTF8
    }
}

function Assert-InstallerNotCancelled {
    if (-not [string]::IsNullOrWhiteSpace($CancelPath) -and (Test-Path -LiteralPath $CancelPath)) {
        throw [OperationCanceledException]::new("Setup was cancelled by the user.")
    }
}

trap {
    $message = $_.Exception.Message
    if ($modelDirectoryChanged) {
        [Environment]::SetEnvironmentVariable("OLLAMA_MODELS", $previousModelDirectory, "User")
    }
    if ($_.Exception -is [OperationCanceledException]) {
        Write-InstallerStatus 0 "Setup cancelled" "Stopping the current operation"
        try { Write-InstallLog "Bootstrap cancelled by the user." } catch {}
        Complete-InstallerBootstrap 2 "Setup was cancelled by the user."
        Remove-Item -LiteralPath $CancelPath -Force -ErrorAction SilentlyContinue
        exit 2
    } else {
        Write-InstallerStatus 0 "Setup could not continue" $message
        try {
            Write-InstallLog "Bootstrap failed: $message"
            if ($_.ScriptStackTrace) { Write-InstallLog "Bootstrap stack: $($_.ScriptStackTrace)" }
        } catch {}
        Complete-InstallerBootstrap 1 $message
        exit 1
    }
}

function Write-InstallLog([string]$Message) {
    $line = "{0:u} {1}" -f (Get-Date), $Message
    Write-Host $line
    if (-not $PlanOnly) {
        New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
        Add-Content -LiteralPath $logPath -Value $line -Encoding UTF8
    }
}

function Resolve-AbsoluteDirectory([string]$Value, [string]$Label) {
    if ([string]::IsNullOrWhiteSpace($Value) -or -not [IO.Path]::IsPathRooted($Value)) {
        throw "$Label must be an absolute Windows folder path."
    }
    return [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($Value))
}

function Get-FreeBytes([string]$Path) {
    $root = [IO.Path]::GetPathRoot($Path)
    if ([string]::IsNullOrWhiteSpace($root)) { return 0 }
    return ([IO.DriveInfo]::new($root)).AvailableFreeSpace
}

function Get-UbuntuStoragePath {
    $distributions = Get-ChildItem `
        -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss" `
        -ErrorAction SilentlyContinue
    foreach ($distribution in $distributions) {
        $properties = Get-ItemProperty -LiteralPath $distribution.PSPath
        if ($properties.DistributionName -eq "Ubuntu" -and $properties.BasePath) {
            return [Environment]::ExpandEnvironmentVariables([string]$properties.BasePath)
        }
    }
    return $null
}

function Assert-Capacity([string]$Path, [long]$RequiredBytes, [string]$Label) {
    $free = Get-FreeBytes $Path
    if ($free -lt $RequiredBytes) {
        $requiredGb = [math]::Ceiling($RequiredBytes / 1GB)
        $freeGb = [math]::Round($free / 1GB, 1)
        throw "$Label needs at least $requiredGb GB free; only $freeGb GB is available."
    }
}

function Find-Winget {
    # Test hook: simulate a computer without Windows Package Manager.
    if ($env:LEADROOM_SETUP_DISABLE_WINGET -eq "1") { return $null }
    $command = Get-Command winget.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    # The App Installer alias is not always on PATH (for example in elevated
    # or freshly provisioned sessions), so check its well-known location.
    $alias = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps\winget.exe"
    if (Test-Path -LiteralPath $alias) { return $alias }
    return $null
}

function Stop-InstallerProcessTree([Diagnostics.Process]$Process) {
    if (-not $Process -or $Process.HasExited) { return }
    & "$env:SystemRoot\System32\taskkill.exe" /PID $Process.Id /T /F 2>$null | Out-Null
    $Process.WaitForExit(5000) | Out-Null
}

function Invoke-CancellableProcess(
    [string]$FilePath,
    [string]$ArgumentLine,
    [string]$Label,
    [switch]$CaptureOutput
) {
    Assert-InstallerNotCancelled
    $outputPath = $null
    $errorPath = $null
    if ($CaptureOutput) {
        # Helper scripts report what went wrong on their output streams; keep both so a
        # failure can be explained in install.log and in Setup's own error message.
        $outputPath = [IO.Path]::GetTempFileName()
        $errorPath = [IO.Path]::GetTempFileName()
        $process = Start-Process `
            -FilePath $FilePath `
            -ArgumentList $ArgumentLine `
            -NoNewWindow `
            -RedirectStandardOutput $outputPath `
            -RedirectStandardError $errorPath `
            -PassThru
    } else {
        $process = Start-Process `
            -FilePath $FilePath `
            -ArgumentList $ArgumentLine `
            -WindowStyle Hidden `
            -PassThru
    }
    try {
        while (-not $process.WaitForExit(250)) {
            Assert-InstallerNotCancelled
        }
        if ($process.ExitCode -ne 0) {
            $reason = ""
            if ($CaptureOutput) {
                $reason = Write-ProcessOutputToLog $Label $outputPath $errorPath
            }
            if ($reason) { throw "$Label failed: $reason" }
            throw "$Label failed with exit code $($process.ExitCode)."
        }
        if ($CaptureOutput) { Write-ProcessOutputToLog $Label $outputPath $errorPath | Out-Null }
    } catch [OperationCanceledException] {
        Stop-InstallerProcessTree $process
        throw
    } finally {
        $process.Dispose()
        foreach ($path in @($outputPath, $errorPath)) {
            if ($path) { Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue }
        }
    }
}

# Appends the end of a helper's output to install.log and returns the most specific
# error line, or "" when there is none.
function Write-ProcessOutputToLog([string]$Label, [string]$OutputPath, [string]$ErrorPath) {
    $lines = @()
    foreach ($path in @($OutputPath, $ErrorPath)) {
        if ($path -and (Test-Path -LiteralPath $path)) {
            $lines += @(Get-Content -LiteralPath $path -ErrorAction SilentlyContinue |
                Where-Object { $_ -and $_.Trim() })
        }
    }
    if ($lines.Count -gt 0) {
        Write-InstallLog "$Label output (last lines):"
        foreach ($line in ($lines | Select-Object -Last 40)) { Write-InstallLog "    $line" }
    }
    $errors = @(Get-Content -LiteralPath $ErrorPath -ErrorAction SilentlyContinue |
        Where-Object { $_ -and $_.Trim() })
    # A terminating PowerShell error is written as its message followed by an "At <file>"
    # line; the last such message is the one that stopped the script.
    $message = ""
    for ($index = $errors.Count - 1; $index -ge 1; $index--) {
        if ($errors[$index] -match '^At (line:|[A-Za-z]:\\)') {
            $message = $errors[$index - 1]
            break
        }
    }
    if (-not $message -and $errors.Count -gt 0) { $message = $errors[$errors.Count - 1] }
    return ($message -replace '^[A-Za-z]:\\[^:]+\.ps1 : ', '').Trim()
}

# True when WSL already holds an imported Leadroom map index with incremental updates set
# up. Any failure (no database, PostgreSQL stopped, no WSL) counts as "no index".
function Test-ExistingLocalIndex {
    try {
        $query = "SELECT to_regclass('public.leadroom_osm_businesses') IS NOT NULL " +
            "AND to_regclass('public.osm2pgsql_properties') IS NOT NULL " +
            "AND EXISTS (SELECT 1 FROM osm2pgsql_properties WHERE property = 'replication_base_url')"
        # Captured whole: see setup-local-data.ps1 for why not Select-Object -First.
        $clusters = @(wsl.exe -d Ubuntu -u root -- pg_lsclusters --no-header | Where-Object { $_ -and $_.Trim() })
        if ($clusters.Count -gt 0) {
            $parts = $clusters[0].Trim() -split "\s+"
            wsl.exe -d Ubuntu -u root -- pg_ctlcluster $parts[0] $parts[1] start | Out-Null
        }
        $answer = @(wsl.exe -d Ubuntu -u postgres -- psql -d leadroom_osm -tAc $query)
        return ($LASTEXITCODE -eq 0) -and (($answer -join "").Trim() -eq "t")
    } catch {
        return $false
    }
}

function Quote-ProcessArgument([string]$Value) {
    return '"' + ($Value -replace '"', '\"') + '"'
}

function Save-InstallerDownload(
    [string]$Url,
    [string]$Destination,
    [string]$Name,
    [int]$Percent
) {
    $client = [System.Net.Http.HttpClient]::new()
    $client.Timeout = [System.Threading.Timeout]::InfiniteTimeSpan
    $client.DefaultRequestHeaders.UserAgent.ParseAdd("LeadroomSetup/1.0")
    $partial = "$Destination.partial"
    try {
        $sendTask = $client.GetAsync($Url, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead)
        while (-not $sendTask.Wait(250)) { Assert-InstallerNotCancelled }
        $response = $sendTask.GetAwaiter().GetResult()
        try {
            $response.EnsureSuccessStatusCode() | Out-Null
            $total = $response.Content.Headers.ContentLength
            $streamTask = $response.Content.ReadAsStreamAsync()
            while (-not $streamTask.Wait(250)) { Assert-InstallerNotCancelled }
            $source = $streamTask.GetAwaiter().GetResult()
            $target = [IO.File]::Create($partial)
            try {
                $buffer = New-Object byte[] 262144
                $received = [long]0
                $lastReport = [DateTime]::MinValue
                while ($true) {
                    Assert-InstallerNotCancelled
                    $readTask = $source.ReadAsync($buffer, 0, $buffer.Length)
                    while (-not $readTask.Wait(250)) { Assert-InstallerNotCancelled }
                    $count = $readTask.GetAwaiter().GetResult()
                    if ($count -le 0) { break }
                    $target.Write($buffer, 0, $count)
                    $received += $count
                    if (((Get-Date) - $lastReport).TotalMilliseconds -ge 500) {
                        $lastReport = Get-Date
                        $receivedMb = [math]::Round($received / 1MB, 1)
                        if ($total -and $total -gt 0) {
                            $totalMb = [math]::Round($total / 1MB, 1)
                            Write-InstallerStatus $Percent "Downloading $Name" "$receivedMb of $totalMb MB"
                        } else {
                            Write-InstallerStatus $Percent "Downloading $Name" "$receivedMb MB received"
                        }
                    }
                }
            } finally {
                $target.Dispose()
                $source.Dispose()
            }
            if ($total -and $total -gt 0 -and $received -ne $total) {
                throw "The $Name download was incomplete ($received of $total bytes)."
            }
        } finally {
            $response.Dispose()
        }
        Move-Item -LiteralPath $partial -Destination $Destination -Force
    } catch {
        Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
        throw
    } finally {
        $client.Dispose()
    }
}

function Install-Prerequisite(
    [string]$WingetId,
    [string]$Name,
    [string]$DownloadUrl,
    [string]$InstallerFileName,
    [string]$InstallerArguments,
    [int]$Percent,
    [scriptblock]$IsInstalled
) {
    if (& $IsInstalled) { return }

    # 1. Prefer Windows Package Manager when it exists and works.
    $winget = Find-Winget
    if ($winget) {
        Write-InstallLog "Installing $Name with winget."
        Write-InstallerStatus $Percent "Installing $Name" "Windows Package Manager is preparing $Name"
        $arguments = "install --id $WingetId --exact --silent --source winget " +
            "--accept-package-agreements --accept-source-agreements --disable-interactivity"
        try {
            Invoke-CancellableProcess $winget $arguments "$Name installation"
        } catch [OperationCanceledException] {
            throw
        } catch {
            Write-InstallLog "winget could not install ${Name}: $($_.Exception.Message) Falling back to a direct download."
        }
        if (& $IsInstalled) { return }
    } else {
        Write-InstallLog "Windows Package Manager is unavailable; downloading $Name directly."
    }

    # 2. Fall back to the vendor's official installer.
    $downloadRoot = Join-Path ([IO.Path]::GetTempPath()) ("leadroom-setup-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $downloadRoot | Out-Null
    try {
        $installer = Join-Path $downloadRoot $InstallerFileName
        Write-InstallLog "Downloading $Name from $DownloadUrl."
        Save-InstallerDownload $DownloadUrl $installer $Name $Percent
        Write-InstallerStatus $Percent "Installing $Name" "Running the $Name installer"
        Write-InstallLog "Running the downloaded $Name installer."
        try {
            Invoke-CancellableProcess $installer $InstallerArguments "$Name installation"
        } catch [OperationCanceledException] {
            throw
        } catch {
            # Vendor installers can return non-zero codes for benign outcomes such
            # as "already installed"; the presence check below is authoritative.
            Write-InstallLog "The $Name installer reported: $($_.Exception.Message)"
        }
    } finally {
        Remove-Item -LiteralPath $downloadRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
    if (-not (& $IsInstalled)) {
        throw "$Name could not be installed automatically. Check the internet connection and run setup again."
    }
}

function Stop-OllamaProcesses([string]$Executable) {
    if (-not $Executable) { return }
    $directory = Split-Path -Parent $Executable
    Get-Process -Name "ollama app", "ollama" -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and $_.Path.StartsWith($directory, [StringComparison]::OrdinalIgnoreCase) } |
        ForEach-Object { Stop-InstallerProcessTree $_ }
}

function Start-OllamaTray([string]$Executable) {
    if (-not $Executable) { return }
    $tray = Join-Path (Split-Path -Parent $Executable) "ollama app.exe"
    if (-not (Test-Path -LiteralPath $tray)) { return }
    # Launch through WMI so the long-lived tray app is not a descendant of Setup.
    # Otherwise tools that wait for Setup's whole process tree (deployment agents,
    # `Start-Process -Wait`) never see Setup finish. WMI also builds the process
    # environment from the registry, so the new OLLAMA_MODELS value is applied.
    try {
        $result = Invoke-CimMethod -ClassName Win32_Process -MethodName Create `
            -Arguments @{ CommandLine = '"' + $tray + '"' }
        if ($result.ReturnValue -ne 0) { throw "Win32_Process.Create returned $($result.ReturnValue)." }
    } catch {
        Write-InstallLog "Detached launch failed ($($_.Exception.Message)); starting Ollama directly."
        Start-Process -FilePath $tray -WindowStyle Hidden | Out-Null
    }
    Write-InstallLog "Started the Ollama background app."
}

function Invoke-OllamaModelPull([string]$Endpoint, [string]$ModelName) {
    $client = [System.Net.Http.HttpClient]::new()
    $client.Timeout = [System.Threading.Timeout]::InfiniteTimeSpan
    try {
        $payload = @{ name = $ModelName; stream = $true } | ConvertTo-Json -Compress
        $content = [System.Net.Http.StringContent]::new($payload, [System.Text.Encoding]::UTF8, "application/json")
        $request = [System.Net.Http.HttpRequestMessage]::new(
            [System.Net.Http.HttpMethod]::Post,
            "$Endpoint/api/pull"
        )
        $request.Content = $content
        $sendTask = $client.SendAsync(
            $request,
            [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead
        )
        while (-not $sendTask.Wait(250)) {
            Assert-InstallerNotCancelled
        }
        $response = $sendTask.GetAwaiter().GetResult()
        $response.EnsureSuccessStatusCode()
        $streamTask = $response.Content.ReadAsStreamAsync()
        while (-not $streamTask.Wait(250)) {
            Assert-InstallerNotCancelled
        }
        $stream = $streamTask.GetAwaiter().GetResult()
        $reader = [IO.StreamReader]::new($stream)
        try {
            while ($true) {
                Assert-InstallerNotCancelled
                $readTask = $reader.ReadLineAsync()
                while (-not $readTask.Wait(250)) {
                    Assert-InstallerNotCancelled
                }
                $line = $readTask.GetAwaiter().GetResult()
                if ($null -eq $line) { break }
                if ([string]::IsNullOrWhiteSpace($line)) { continue }
                $event = $line | ConvertFrom-Json
                if ($event.error) { throw [InvalidOperationException]::new([string]$event.error) }
                $status = if ($event.status) { [string]$event.status } else { "Receiving model data" }
                if ($event.total -and [long]$event.total -gt 0) {
                    $percent = [math]::Min(100, [math]::Floor(([double]$event.completed / [double]$event.total) * 100))
                    $receivedGb = [math]::Round([double]$event.completed / 1GB, 2)
                    $totalGb = [math]::Round([double]$event.total / 1GB, 2)
                    Write-InstallerStatus $percent "Downloading $ModelName" "$status - $percent% ($receivedGb of $totalGb GB)"
                } else {
                    Write-InstallerStatus 0 "Downloading $ModelName" $status
                }
            }
        } finally {
            $reader.Dispose()
            $stream.Dispose()
            $response.Dispose()
            $request.Dispose()
        }
    } finally {
        $client.Dispose()
    }
}

function Test-WebViewRuntime {
    $clientId = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    $keys = @(
        "HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\$clientId",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\$clientId",
        "HKCU:\SOFTWARE\Microsoft\EdgeUpdate\Clients\$clientId"
    )
    foreach ($key in $keys) {
        if (-not (Test-Path $key)) { continue }
        $version = (Get-ItemProperty -LiteralPath $key -Name pv -ErrorAction SilentlyContinue).pv
        if ($version -and $version -ne "0.0.0.0") { return $true }
    }
    return $false
}

function Find-Ollama {
    $command = Get-Command ollama.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"),
        (Join-Path $env:ProgramFiles "Ollama\ollama.exe")
    )
    return $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}

function Wait-Ollama([string]$Executable, [string]$Endpoint = "http://127.0.0.1:11434") {
    $started = $null
    try {
        Invoke-RestMethod -Uri "$Endpoint/api/tags" -TimeoutSec 2 | Out-Null
        return $null
    } catch {
        Write-InstallLog "Starting the local Ollama service."
        $started = Start-Process -FilePath $Executable -ArgumentList "serve" -WindowStyle Hidden -PassThru
    }
    try {
        $deadline = (Get-Date).AddSeconds(45)
        while ((Get-Date) -lt $deadline) {
            Assert-InstallerNotCancelled
            Start-Sleep -Milliseconds 750
            try {
                Invoke-RestMethod -Uri "$Endpoint/api/tags" -TimeoutSec 2 | Out-Null
                return $started
            } catch {}
        }
        throw "Ollama was installed but its local service did not become ready."
    } catch {
        Stop-InstallerProcessTree $started
        throw
    }
}

function Save-StorageLocator([string]$DataPath, [string]$DownloadsPath) {
    New-Item -ItemType Directory -Force -Path $bootstrapRoot, $DataPath, $DownloadsPath | Out-Null
    $configPath = Join-Path $bootstrapRoot "storage.json"
    if ((Test-Path -LiteralPath $configPath) -and -not $ForceStorage) {
        Write-InstallLog "Keeping the existing storage configuration during upgrade."
        return
    }
    $payload = [ordered]@{
        data_root = $DataPath
        downloads_root = $DownloadsPath
        data_action = "use"
        move_downloads = $false
    }
    $temporary = "$configPath.installing"
    # Windows PowerShell 5.1 writes a BOM with -Encoding UTF8, which Python's JSON
    # parser rejects; write plain UTF-8 so the app can read the file.
    [IO.File]::WriteAllText($temporary, ($payload | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporary -Destination $configPath -Force
    Write-InstallLog "Configured workspace storage at $DataPath and downloads at $DownloadsPath."
}

$InstallRoot = Resolve-AbsoluteDirectory $InstallRoot "Install folder"
$HelperRoot = if ([string]::IsNullOrWhiteSpace($HelperRoot)) {
    Join-Path $InstallRoot "scripts"
} else {
    Resolve-AbsoluteDirectory $HelperRoot "Setup helper folder"
}
$ResourceRoot = if ([string]::IsNullOrWhiteSpace($ResourceRoot)) {
    Join-Path $InstallRoot "infra\osm"
} else {
    Resolve-AbsoluteDirectory $ResourceRoot "Setup resource folder"
}
$DataRoot = Resolve-AbsoluteDirectory $DataRoot "Workspace data folder"
$DownloadsRoot = Resolve-AbsoluteDirectory $DownloadsRoot "Downloads folder"

$minimumDownloadSpace = if ($Mode -eq "FullLocal") { 35GB } elseif ($DownloadModel) { 5GB } else { 1GB }
Assert-Capacity $DataRoot 500MB "Workspace data folder"
Assert-Capacity $DownloadsRoot $minimumDownloadSpace "Downloads folder"

$plan = [ordered]@{
    mode = $Mode
    install_root = $InstallRoot
    data_root = $DataRoot
    downloads_root = $DownloadsRoot
    install_webview = [bool]$InstallWebView
    install_ollama = [bool]$InstallOllama
    download_model = [bool]$DownloadModel
    model = $Model
    setup_local_data = [bool]$SetupLocalData
    force_storage = [bool]$ForceStorage
    osm_region = $OsmRegion
}
if ($PlanOnly) {
    $plan | ConvertTo-Json
    Complete-InstallerBootstrap 0
    exit 0
}

Write-InstallerStatus 5 "Checking this computer" "Validating storage space and selected components"
Assert-InstallerNotCancelled
Write-InstallLog "Starting Leadroom $Mode bootstrap."

if (-not (Test-WebViewRuntime)) {
    Assert-InstallerNotCancelled
    if (-not $InstallWebView) { throw "Microsoft Edge WebView2 Runtime is required to open Leadroom." }
    Install-Prerequisite `
        -WingetId "Microsoft.EdgeWebView2Runtime" `
        -Name "Microsoft Edge WebView2 Runtime" `
        -DownloadUrl $WebViewDownloadUrl `
        -InstallerFileName "MicrosoftEdgeWebview2Setup.exe" `
        -InstallerArguments "/silent /install" `
        -Percent 10 `
        -IsInstalled { Test-WebViewRuntime }
}
Write-InstallerStatus 20 "WebView2 is ready" "Checking the local AI runtime"
Write-InstallLog "WebView2 runtime is ready."

$ollama = Find-Ollama
$ollamaInstalledNow = $false
$modelDirectory = Join-Path $DownloadsRoot "ollama\models"
if (-not $ollama -and $InstallOllama) {
    Assert-InstallerNotCancelled
    Assert-Capacity $env:LOCALAPPDATA 6GB "The Windows drive (for the Ollama runtime)"
    # Point Ollama at the selected models folder before it is installed, so the
    # background service it may auto-start already uses the right location.
    New-Item -ItemType Directory -Force -Path $modelDirectory | Out-Null
    $previousModelDirectory = [Environment]::GetEnvironmentVariable("OLLAMA_MODELS", "User")
    [Environment]::SetEnvironmentVariable("OLLAMA_MODELS", $modelDirectory, "User")
    $modelDirectoryChanged = $true
    $env:OLLAMA_MODELS = $modelDirectory
    Install-Prerequisite `
        -WingetId "Ollama.Ollama" `
        -Name "Ollama" `
        -DownloadUrl $OllamaDownloadUrl `
        -InstallerFileName "OllamaSetup.exe" `
        -InstallerArguments "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-" `
        -Percent 25 `
        -IsInstalled { [bool](Find-Ollama) }
    $env:Path = "$env:LOCALAPPDATA\Programs\Ollama;$env:Path"
    $ollama = Find-Ollama
    $ollamaInstalledNow = $true
    # A freshly installed Ollama may auto-start with an environment that predates
    # OLLAMA_MODELS. Stop only that new instance; it is restarted below.
    # The tray app can spawn its server a moment after the installer exits.
    Stop-OllamaProcesses $ollama
    Start-Sleep -Seconds 3
    Stop-OllamaProcesses $ollama
}
if ($DownloadModel -and -not $ollama) {
    Write-InstallLog "Skipping the $Model download because Ollama is not installed and was not selected."
    $DownloadModel = $false
}
if ($ollama -and ($InstallOllama -or $DownloadModel)) {
    New-Item -ItemType Directory -Force -Path $modelDirectory | Out-Null
    if (-not $modelDirectoryChanged) {
        $previousModelDirectory = [Environment]::GetEnvironmentVariable("OLLAMA_MODELS", "User")
        [Environment]::SetEnvironmentVariable("OLLAMA_MODELS", $modelDirectory, "User")
        $modelDirectoryChanged = $true
    }
    $env:OLLAMA_MODELS = $modelDirectory
    Write-InstallLog "Ollama is ready and new models will be stored at $modelDirectory."
    if ($DownloadModel) {
        Assert-InstallerNotCancelled
        Write-InstallerStatus 30 "Starting Ollama" "Preparing the recommended model download"
        $temporaryServer = $null
        $previousHost = $env:OLLAMA_HOST
        try {
            $defaultServerRunning = $false
            try {
                Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 2 | Out-Null
                $defaultServerRunning = $true
            } catch {}
            $endpoint = "http://127.0.0.1:11434"
            if ($defaultServerRunning -and $previousModelDirectory -ne $modelDirectory) {
                $env:OLLAMA_HOST = "127.0.0.1:11435"
                $endpoint = "http://127.0.0.1:11435"
                Write-InstallLog "Using an isolated Ollama download service for the selected model folder."
            }
            $temporaryServer = Wait-Ollama $ollama $endpoint
            Write-InstallLog "Downloading or verifying Ollama model $Model."
            Invoke-OllamaModelPull $endpoint $Model
            Write-InstallerStatus 90 "AI model is ready" "Finishing Leadroom setup"
            Write-InstallLog "Model $Model is ready."
        } finally {
            if ($temporaryServer) { Stop-Process -Id $temporaryServer.Id -Force -ErrorAction SilentlyContinue }
            if ($null -eq $previousHost) { Remove-Item Env:OLLAMA_HOST -ErrorAction SilentlyContinue }
            else { $env:OLLAMA_HOST = $previousHost }
        }
    }
} elseif ($ollama) {
    Write-InstallLog "Existing Ollama installation detected; no model download was selected."
}
if ($ollamaInstalledNow) {
    # Relaunch the Ollama background app with OLLAMA_MODELS in place so Leadroom
    # can reach the service immediately, without a sign-out or restart.
    Start-OllamaTray $ollama
}

if ($Mode -eq "FullLocal" -and $SetupLocalData) {
    Assert-InstallerNotCancelled
    Write-InstallerStatus 5 "Preparing local discovery" "Checking WSL2, Ubuntu, memory, and database tools"
    $memory = (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory
    if ($memory -lt 16GB) { throw "Full Local setup requires at least 16 GB RAM." }
    $ubuntu = @(wsl.exe -l -q 2>$null) -replace "`0", "" | Where-Object { $_.Trim() -eq "Ubuntu" }
    if (-not $ubuntu) {
        throw "Full Local setup needs WSL2 with Ubuntu. Run 'wsl --install -d Ubuntu', restart Windows, then rerun the installer."
    }
    $powershell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
    if (Test-ExistingLocalIndex) {
        # Reinstalling or upgrading must not rebuild the index: a fresh import takes hours
        # and would replace data that the incremental updates have already brought forward.
        Write-InstallerStatus 10 "Keeping your local index" "An existing OpenStreetMap index was found; refreshing its update service"
        Write-InstallLog "An existing local map index was found; keeping it and refreshing its update service."
        $updatesArguments = "-NoLogo -NoProfile -ExecutionPolicy Bypass -File " +
            (Quote-ProcessArgument (Join-Path $HelperRoot "setup-local-updates.ps1")) +
            " -ResourceDirectory " + (Quote-ProcessArgument $ResourceRoot)
        Invoke-CancellableProcess $powershell $updatesArguments "Local data update service" -CaptureOutput
    } else {
        $ubuntuStorage = Get-UbuntuStoragePath
        if (-not $ubuntuStorage) {
            throw "Setup could not locate Ubuntu's WSL storage folder to verify free disk space."
        }
        Assert-Capacity $ubuntuStorage 30GB "Ubuntu WSL storage drive"
        Write-InstallerStatus 10 "Building the local index" "Downloading and importing OpenStreetMap data; this can take a long time"
        Write-InstallLog "Installing the Full Local database engine."
        $setupScript = Join-Path $HelperRoot "setup-local-data.ps1"
        $setupArguments = "-NoLogo -NoProfile -ExecutionPolicy Bypass -File " +
            (Quote-ProcessArgument $setupScript)
        Invoke-CancellableProcess $powershell $setupArguments "Full Local database setup" -CaptureOutput

        $importScript = Join-Path $HelperRoot "import-osm.ps1"
        $importArguments = "-NoLogo -NoProfile -ExecutionPolicy Bypass -File " +
            (Quote-ProcessArgument $importScript) +
            " -Region " + (Quote-ProcessArgument $OsmRegion) +
            " -DataDirectory " + (Quote-ProcessArgument (Join-Path $DownloadsRoot "osm")) +
            " -ResourceDirectory " + (Quote-ProcessArgument $ResourceRoot) +
            " -UpdateScriptPath " +
            (Quote-ProcessArgument (Join-Path $HelperRoot "setup-local-updates.ps1"))
        Invoke-CancellableProcess $powershell $importArguments "OpenStreetMap import" -CaptureOutput
    }
}

Write-InstallerStatus 95 "Saving workspace settings" "Recording the selected storage folders"
Assert-InstallerNotCancelled
Save-StorageLocator $DataRoot $DownloadsRoot
Write-InstallLog "Leadroom bootstrap completed successfully."
Write-InstallerStatus 100 "Leadroom is ready" "Selected components were prepared successfully"
Complete-InstallerBootstrap 0
