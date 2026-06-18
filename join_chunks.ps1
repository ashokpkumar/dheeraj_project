param(
    [string]$BaseFileName = "os_image.tar"
)

Write-Host "Joining chunks..."

Get-Content "$BaseFileName.part.*" -Encoding Byte -ReadCount 0 |
Set-Content $BaseFileName -Encoding Byte

Write-Host ""
Write-Host "Created: $BaseFileName"