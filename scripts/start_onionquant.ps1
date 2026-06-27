param(
    [switch]$Restart,
    [switch]$NoServer,
    [switch]$NoScheduler
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Logs = Join-Path $Root "logs"
$Runtime = Join-Path $Root "company\runtime"

if (-not (Test-Path $Python)) {
    throw "Python venv not found: $Python"
}

New-Item -ItemType Directory -Force -Path $Logs, $Runtime | Out-Null

function Get-OnionPythonProcess {
    param([string]$Pattern)
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like "*$Pattern*" }
}

function Stop-OnionPythonProcess {
    param([string]$Pattern)
    $processes = @(Get-OnionPythonProcess -Pattern $Pattern)
    foreach ($proc in $processes) {
        Write-Host "Stopping PID $($proc.ProcessId): $Pattern"
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

function Start-OnionProcess {
    param(
        [string]$Name,
        [string]$Script,
        [string]$Stdout,
        [string]$Stderr
    )
    Write-Host "Starting $Name"
    Start-Process `
        -FilePath $Python `
        -ArgumentList $Script `
        -WorkingDirectory $Root `
        -RedirectStandardOutput (Join-Path $Logs $Stdout) `
        -RedirectStandardError (Join-Path $Logs $Stderr) `
        -WindowStyle Hidden
}

function Get-LogicalProcessCount {
    param([array]$Processes)
    $ids = @($Processes | ForEach-Object { $_.ProcessId })
    @($Processes | Where-Object { $ids -notcontains $_.ParentProcessId }).Count
}

if ($Restart) {
    Stop-OnionPythonProcess -Pattern "company\server.py"
    Stop-OnionPythonProcess -Pattern "company/server.py"
    Stop-OnionPythonProcess -Pattern "scripts\background_scheduler.py"
    Stop-OnionPythonProcess -Pattern "scripts/background_scheduler.py"
    Start-Sleep -Seconds 2
}

if (-not $NoServer) {
    $serverProcs = @(Get-OnionPythonProcess -Pattern "company\server.py") +
        @(Get-OnionPythonProcess -Pattern "company/server.py")
    $port = Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue
    if ($serverProcs.Count -eq 0 -and -not $port) {
        Start-OnionProcess -Name "server" -Script "company\server.py" -Stdout "server.log" -Stderr "server_error.log"
    } else {
        Write-Host "Server already appears to be running."
    }
}

if (-not $NoScheduler) {
    $schedulerProcs = @(Get-OnionPythonProcess -Pattern "scripts\background_scheduler.py") +
        @(Get-OnionPythonProcess -Pattern "scripts/background_scheduler.py")
    if ($schedulerProcs.Count -eq 0) {
        Start-OnionProcess -Name "background_scheduler" -Script "scripts\background_scheduler.py" -Stdout "bg_scheduler.log" -Stderr "bg_scheduler_err.log"
    } else {
        Write-Host "Background scheduler already appears to be running."
    }
}

Start-Sleep -Seconds 5

$serverPort = Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue
$server = @(Get-OnionPythonProcess -Pattern "company\server.py") +
    @(Get-OnionPythonProcess -Pattern "company/server.py")
$scheduler = @(Get-OnionPythonProcess -Pattern "scripts\background_scheduler.py") +
    @(Get-OnionPythonProcess -Pattern "scripts/background_scheduler.py")

$status = [ordered]@{
    updated_at = (Get-Date).ToString("o")
    python = $Python
    server_port_listening = [bool]$serverPort
    server_logical_instances = Get-LogicalProcessCount -Processes $server
    server_pids = @($server | ForEach-Object { $_.ProcessId })
    scheduler_logical_instances = Get-LogicalProcessCount -Processes $scheduler
    scheduler_pids = @($scheduler | ForEach-Object { $_.ProcessId })
}

$statusPath = Join-Path $Runtime "process_status.json"
$status | ConvertTo-Json -Depth 4 | Set-Content -Path $statusPath -Encoding UTF8
$status | ConvertTo-Json -Depth 4
