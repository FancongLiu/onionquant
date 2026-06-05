try {
    $r = Invoke-WebRequest -Uri 'http://192.168.5.1' -TimeoutSec 5 -UseBasicParsing
    Write-Host "Status: $($r.StatusCode)"
    Write-Host "Server: $($r.Headers['Server'])"
    $text = $r.Content -replace '<[^>]+>', ' '
    $text = $text -replace '\s+', ' '
    if ($text.Length -gt 200) { $text = $text.Substring(0, 200) }
    Write-Host "Body: $text"
} catch {
    Write-Host "Error: $_"
}
