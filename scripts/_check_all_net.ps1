Write-Host "=== All IPv4 interfaces ==="
Get-NetIPAddress -AddressFamily IPv4 | ForEach-Object {
    Write-Host "$($_.IPAddress)/$($_.PrefixLength)  interface: $($_.InterfaceAlias) ($($_.InterfaceIndex))"
}

Write-Host ""
Write-Host "=== Default Route ==="
Get-NetRoute -DestinationPrefix "0.0.0.0/0" | ForEach-Object {
    Write-Host "Gateway: $($_.NextHop)  via $($_.InterfaceAlias) metric:$($_.RouteMetric)"
}

Write-Host ""
Write-Host "=== Active connections to :8765 or :8645 ==="
netstat -an | Select-String "8765|8645" | ForEach-Object { Write-Host $_ }
