$ErrorActionPreference = "Stop"

function Stop-OnionPythonProcess {
    param([string]$Pattern)
    $processes = @(
        Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
            Where-Object { $_.CommandLine -like "*$Pattern*" }
    )
    foreach ($proc in $processes) {
        Write-Host "Stopping PID $($proc.ProcessId): $Pattern"
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

Stop-OnionPythonProcess -Pattern "company\server.py"
Stop-OnionPythonProcess -Pattern "company/server.py"
Stop-OnionPythonProcess -Pattern "scripts\background_scheduler.py"
Stop-OnionPythonProcess -Pattern "scripts/background_scheduler.py"
