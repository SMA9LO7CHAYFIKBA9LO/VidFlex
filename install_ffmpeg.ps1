Write-Host "Downloading FFmpeg (this may take a minute)..." -ForegroundColor Cyan

$url  = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
$zip  = Join-Path $env:TEMP "ffmpeg.zip"
$tmp  = Join-Path $env:TEMP "ffmpeg_extracted"
$dest = "C:\ffmpeg"

# Download
try {
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    Write-Host "Download complete." -ForegroundColor Green
} catch {
    Write-Host "ERROR downloading: $_" -ForegroundColor Red
    exit 1
}

# Extract
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
Expand-Archive -Path $zip -DestinationPath $tmp -Force
Write-Host "Extraction complete." -ForegroundColor Green

# Move the inner folder (ffmpeg-master-*) to C:\ffmpeg
$inner = Get-ChildItem $tmp | Select-Object -First 1
if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
Move-Item $inner.FullName $dest
Write-Host "Installed to $dest" -ForegroundColor Green

# Clean up
Remove-Item $zip  -Force -ErrorAction SilentlyContinue
Remove-Item $tmp  -Recurse -Force -ErrorAction SilentlyContinue

# Add to PATH (current user, permanent)
$binPath  = "$dest\bin"
$userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($userPath -notlike "*$binPath*") {
    [Environment]::SetEnvironmentVariable("PATH", "$userPath;$binPath", "User")
    Write-Host "Added $binPath to your user PATH." -ForegroundColor Green
} else {
    Write-Host "$binPath is already in PATH." -ForegroundColor Yellow
}

# Also add to current session
$env:PATH += ";$binPath"

# Verify
$v = & "$binPath\ffmpeg.exe" -version 2>&1 | Select-Object -First 1
Write-Host ""
Write-Host "FFmpeg verified: $v" -ForegroundColor Green
Write-Host ""
Write-Host "SUCCESS! FFmpeg is installed. Restart the Flask server to use it." -ForegroundColor Cyan
