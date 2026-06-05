$result = Test-NetConnection -ComputerName 8.8.8.8 -TraceRoute -WarningAction SilentlyContinue
Write-Host "Traceroute to 8.8.8.8:"
if ($result.TraceRoute) {
    for ($i = 0; $i -lt [Math]::Min(5, $result.TraceRoute.Count); $i++) {
        Write-Host "  $($i+1): $($result.TraceRoute[$i])"
    }
}

Write-Host ""
Write-Host "=== IPv6 on WLAN adapter ==="
$wlan = Get-NetAdapter -Name "WLAN" -ErrorAction SilentlyContinue
if (-not $wlan) {
    $wlan = Get-NetAdapter | Where-Object { $_.Name -like "*Wi-Fi*" -or $_.Name -like "*WLAN*" -or $_.InterfaceDescription -like "*wireless*" -or $_.InterfaceDescription -like "*Wi-Fi*" } | Select-Object -First 1
}
if ($wlan) {
    Write-Host "Adapter: $($wlan.Name) ($($wlan.InterfaceDescription))"
    $ipv6 = Get-NetIPAddress -InterfaceIndex $wlan.InterfaceIndex -AddressFamily IPv6 -ErrorAction SilentlyContinue
    foreach ($ip in $ipv6) {
        Write-Host "  IPv6: $($ip.IPv6Address)  PrefixOrigin:$($ip.PrefixOrigin)  SuffixOrigin:$($ip.SuffixOrigin)"
    }
}
