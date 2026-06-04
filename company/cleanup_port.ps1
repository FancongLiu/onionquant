$conn = netstat -ano | Select-String ':8765' | Select-String 'LISTENING'
if ($conn) {
    $parts = $conn -split '\s+'
    $procId = $parts[$parts.Length - 1]
    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    Write-Output "Killed PID $procId"
} else {
    Write-Output "Port 8765 is free"
}
