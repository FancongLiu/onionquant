Get-NetIPAddress -AddressFamily IPv6 | ForEach-Object {
    if ($_.IPAddress -notlike "fe80:*" -and $_.IPAddress -notlike "::1*") {
        Write-Host "$($_.IPAddress)  $($_.InterfaceAlias)  Scope:$($_.PrefixOrigin)"
    }
}
Write-Host "---"
Write-Host "IPv6 Default Route:"
Get-NetRoute -AddressFamily IPv6 -DestinationPrefix "::/0" | ForEach-Object {
    Write-Host "  via $($_.NextHop) on $($_.InterfaceAlias)"
}
Write-Host "---"
Write-Host "Ping6 test to google:"
Test-NetConnection -ComputerName ipv6.google.com -Port 443 -WarningAction SilentlyContinue 2>$null | ForEach-Object {
    Write-Host "  Result: $($_.TcpTestSucceeded)"
}
