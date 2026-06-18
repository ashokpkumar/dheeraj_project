param(
    [string]$TarFile = "os_image.tar"
)

if (!(Test-Path $TarFile)) {
    Write-Host "File not found: $TarFile"
    exit 1
}

Write-Host "Checking Rancher Desktop / nerdctl..."

$nerdctlExists = Get-Command nerdctl -ErrorAction SilentlyContinue

if (-not $nerdctlExists) {
    Write-Host "nerdctl not found."
    Write-Host "Make sure Rancher Desktop is installed and nerdctl is available."
    exit 1
}

Write-Host ""
Write-Host "Loading image into Rancher Desktop..."

nerdctl load -i $TarFile

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Image load failed."
    exit 1
}

Write-Host ""
Write-Host "Image loaded successfully into Rancher Desktop."
Write-Host ""

Write-Host "Available images:"
nerdctl images