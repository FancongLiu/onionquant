$adapter = Get-NetRoute -DestinationPrefix "0.0.0.0/0" | Where-Object { $_.RouteMetric -lt 100 } | Select-Object -First 1
Write-Host "Default Gateway: $($adapter.NextHop)"
Write-Host "Interface Index: $($adapter.InterfaceIndex)"
Write-Host "Interface Alias: $($adapter.InterfaceAlias)"
Write-Host "---"
Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $adapter.InterfaceIndex | ForEach-Object {
    Write-Host "IP: $($_.IPAddress) / Prefix: $($_.PrefixLength)"
}
Write-Host "---"
$pubip = Invoke-RestMethod -Uri "https://api.ipify.org" -TimeoutSec 5
Write-Host "Public IPv4: $pubip"
