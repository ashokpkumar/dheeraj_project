param(
    [string]$TarFile = "os_image.tar"
)

if (!(Test-Path $TarFile)) {
    Write-Host "File not found: $TarFile"
    exit 1
}

Write-Host "Loading Docker image..."

docker load -i $TarFile

if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker load failed."
    exit 1
}

Write-Host ""
Write-Host "Docker image loaded successfully."