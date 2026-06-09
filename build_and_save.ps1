param(
    [string]$Dockerfile = "Dockerfilebase",
    [string]$ImageName = "os_image:latest",
    [string]$TarName = "os_image.tar"
)

Write-Host "Building Docker image..."

docker build -f $Dockerfile -t $ImageName .

if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker build failed."
    exit 1
}

Write-Host "Saving Docker image to tar..."

docker save -o $TarName $ImageName

if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker save failed."
    exit 1
}

Write-Host ""
Write-Host "Done."
Write-Host "Created: $TarName"