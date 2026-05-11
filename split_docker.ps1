param(
    [string]$ImageName = "os_image:latest",
    [string]$OutputName = "C:\Users\ashok\Documents\dheeraj_project\dheeraj_project\backend\automation\os_image",
    [int]$ChunkSizeMB = 10
)

Write-Host "Saving docker image..."

docker save -o "$OutputName.tar" $ImageName

Write-Host "Compressing image..."

Compress-Archive -Path "$OutputName.tar" -DestinationPath "$OutputName.zip" -Force

Remove-Item "$OutputName.tar"

Write-Host "Splitting into chunks..."

$chunkSize = $ChunkSizeMB * 1MB
$file = "$OutputName.zip"

$stream = [System.IO.File]::OpenRead($file)
$buffer = New-Object byte[] $chunkSize
$part = 0

while (($read = $stream.Read($buffer, 0, $buffer.Length)) -gt 0) {
    $partFile = "{0}.part.{1:d3}" -f $file, $part
    $outStream = [System.IO.File]::Create($partFile)
    $outStream.Write($buffer, 0, $read)
    $outStream.Close()

    Write-Host "Created $partFile"

    $part++
}

$stream.Close()

Write-Host ""
Write-Host "Done."
Write-Host "Upload these files to GitHub:"
Write-Host "$OutputName.zip.part.*"