# debug-build-context.ps1
#
# Diagnoses the Docker build context (the current directory) for files/folders
# that commonly trigger:
#   ERROR: failed to build: failed to solve: archive/tar: unknown file mode ?rwxr-xr-x
#
# This happens when a file/folder on disk has metadata (reparse points, "cloud"
# placeholder attributes, or epoch/1970 timestamps left over from an extracted
# OCI/Docker image layout) that Go's archive/tar can't classify.
#
# Usage (run from the same folder you run `docker build` / build-and-deploy.bat in):
#   powershell -ExecutionPolicy Bypass -File .\debug-build-context.ps1

param(
    [string]$Path = "."
)

$root = (Resolve-Path $Path).Path
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Docker Build Context Debug" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Context path: $root`n"

# ---------------- Load .dockerignore ----------------
$ignoreFile = Join-Path $root ".dockerignore"
$ignorePatterns = @()
if (Test-Path $ignoreFile) {
    $ignorePatterns = Get-Content $ignoreFile |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ -and -not $_.StartsWith("#") }
    Write-Host "Loaded $($ignorePatterns.Count) pattern(s) from .dockerignore" -ForegroundColor Green
} else {
    Write-Host "WARNING: No .dockerignore found at $ignoreFile" -ForegroundColor Yellow
    Write-Host "         Everything in this folder will be sent to Docker as build context.`n"
}

function Test-Ignored {
    param([string]$RelPath)
    $normalized = $RelPath -replace '\\', '/'
    foreach ($pattern in $ignorePatterns) {
        $p = $pattern.TrimEnd('/')
        if ($normalized -eq $p) { return $true }
        if ($normalized -like "$p/*") { return $true }
        if ($normalized -like "*/$p") { return $true }
        if ($normalized -like "*/$p/*") { return $true }
        if ($normalized -like $p) { return $true }
    }
    return $false
}

# ---------------- Scan for suspicious entries ----------------
Write-Host "Scanning for files/folders that can break 'docker build'..." -ForegroundColor Cyan

$suspects = @()
$ignoredCount = 0
$totalCount = 0

Get-ChildItem -Recurse -Force -ErrorAction SilentlyContinue -LiteralPath $root | ForEach-Object {
    $totalCount++
    $rel = $_.FullName.Substring($root.Length).TrimStart('\', '/')

    $isIgnored = Test-Ignored $rel
    if ($isIgnored) { $ignoredCount++ }

    $flags = @()

    if ($_.Attributes -match "ReparsePoint") { $flags += "ReparsePoint (symlink/junction/cloud-placeholder)" }
    if ($_.Attributes -match "Offline")      { $flags += "Offline (cloud placeholder)" }

    if ($_.LastWriteTime.Year -lt 1990)  { $flags += "epoch LastWriteTime ($($_.LastWriteTime))" }
    if ($_.CreationTime.Year -lt 1990)   { $flags += "epoch CreationTime ($($_.CreationTime))" }

    if ($flags.Count -gt 0) {
        $suspects += [PSCustomObject]@{
            Path     = $rel
            Type     = if ($_.PSIsContainer) { "Dir" } else { "File" }
            Ignored  = $isIgnored
            Issues   = ($flags -join "; ")
        }
    }
}

Write-Host "Scanned $totalCount item(s); $ignoredCount match .dockerignore patterns.`n"

if ($suspects.Count -eq 0) {
    Write-Host "No suspicious files/folders found." -ForegroundColor Green
    Write-Host "If the build still fails with 'unknown file mode', try:" -ForegroundColor Yellow
    Write-Host "  1. Re-run with DOCKER_BUILDKIT=0 to get a different (sometimes more informative) error."
    Write-Host "  2. Move the Dockerfile + minimal app files into a clean folder and build from there"
    Write-Host "     to bisect which subfolder is the culprit."
} else {
    Write-Host "Found $($suspects.Count) suspicious item(s) - these are likely candidates for" -ForegroundColor Red
    Write-Host "'archive/tar: unknown file mode ?rwxr-xr-x':`n" -ForegroundColor Red
    $suspects | Format-Table -AutoSize -Wrap

    $notIgnored = $suspects | Where-Object { -not $_.Ignored }
    if ($notIgnored.Count -gt 0) {
        Write-Host "`nThe following are NOT excluded by .dockerignore and are sent to Docker as-is:" -ForegroundColor Red
        $notIgnored | Select-Object -ExpandProperty Path -Unique | ForEach-Object { Write-Host "  $_" }
        Write-Host "`nFix: add these path(s) to .dockerignore, or delete them if they're leftover build artifacts" -ForegroundColor Yellow
        Write-Host "(e.g. an extracted 'docker save'/OCI image layout such as 'myimage/blobs/...')." -ForegroundColor Yellow
    }

    $ignoredButPresent = $suspects | Where-Object { $_.Ignored }
    if ($ignoredButPresent.Count -gt 0) {
        Write-Host "`nNote: the following ARE excluded by .dockerignore, so they should NOT be" -ForegroundColor Yellow
        Write-Host "sent to Docker. If the build error mentions them anyway, the .dockerignore" -ForegroundColor Yellow
        Write-Host "pattern may not match correctly, or this isn't the build context being used:" -ForegroundColor Yellow
        $ignoredButPresent | Select-Object -ExpandProperty Path -Unique | ForEach-Object { Write-Host "  $_" }
    }
}

# ---------------- Check base image availability ----------------
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Base image check" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$dockerfile = Join-Path $root "Dockerfile"
if (Test-Path $dockerfile) {
    $fromLine = Get-Content $dockerfile | Where-Object { $_ -match '^\s*FROM\s+' } | Select-Object -First 1
    Write-Host "Dockerfile FROM line: $fromLine"

    if ($fromLine -match '^\s*FROM\s+(\S+)') {
        $baseImage = $Matches[1]
        try {
            $found = docker images --format "{{.Repository}}:{{.Tag}}" 2>$null | Where-Object { $_ -eq $baseImage }
            if ($found) {
                Write-Host "OK: base image '$baseImage' is present locally." -ForegroundColor Green
            } else {
                Write-Host "WARNING: base image '$baseImage' was NOT found in 'docker images'." -ForegroundColor Yellow
                Write-Host "         Run 'docker load -i os_image.tar' (after joining the .part chunks" -ForegroundColor Yellow
                Write-Host "         with join_chunks.ps1, if present) before building." -ForegroundColor Yellow
            }
        } catch {
            Write-Host "Could not query Docker (is Docker Desktop running?)." -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "No Dockerfile found at $dockerfile" -ForegroundColor Yellow
}

Write-Host "`nDone." -ForegroundColor Cyan
