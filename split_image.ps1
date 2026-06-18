param(
    [string]$InputFile = "os_image.tar",
    [int]$ChunkSizeMB = 10
)

if (!(Test-Path $InputFile)) {
    Write-Host "File not found: $InputFile"
    exit 1
}

$chunkSize = $ChunkSizeMB * 1MB

Write-Host "Splitting $InputFile into $ChunkSizeMB MB chunks..."

$stream = [System.IO.File]::OpenRead($InputFile)
$buffer = New-Object byte[] $chunkSize
$part = 0

while (($read = $stream.Read($buffer, 0, $buffer.Length)) -gt 0) {

    $partFile = "{0}.part.{1:d3}" -f $InputFile, $part

    $outStream = [System.IO.File]::Create($partFile)
    $outStream.Write($buffer, 0, $read)
    $outStream.Close()

    Write-Host "Created $partFile"

    $part++
}

$stream.Close()

Write-Host ""
Write-Host "Splitting complete."