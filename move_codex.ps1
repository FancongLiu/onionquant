# PowerShell script to move Codex installer to E:\Codex_Project
$source = "C:\Users\28462\Downloads\Codex Installer.exe"
$destFolder = "E:\Codex_Project"
$dest = Join-Path $destFolder "Codex Installer.exe"
nif (-not (Test-Path $destFolder)) {
    New-Item -ItemType Directory -Path $destFolder -Force | Out-Null
    Write-Host "Created folder: $destFolder"
}
nif (Test-Path $source) {
    Move-Item -Path $source -Destination $destFolder -Force
    Write-Host "Moved $source to $destFolder"
    Write-Host "Contents of $destFolder:"
    Get-ChildItem $destFolder | Format-Table Name,Length
} else {
    Write-Host "Source not found: $source"
}
