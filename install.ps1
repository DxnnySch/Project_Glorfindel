# Projekt Glorfindel – Installation (Windows). Rechtsklick > "Mit PowerShell ausführen".
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
Write-Host "== Projekt Glorfindel: Installation ==" -ForegroundColor Yellow

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Host "uv (Python-Verwaltung) wird installiert …"
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
  Write-Host "ffmpeg wird über winget installiert …"
  winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
  Write-Host "Hinweis: Falls 'ffmpeg' danach nicht gefunden wird, bitte ein neues Terminal öffnen und install.ps1 erneut ausführen." -ForegroundColor Cyan
}

uv venv .venv
uv pip install -e "."
$gpu = Read-Host "Lokale Transkription mit Whisper (empfohlen, NVIDIA-GPU ideal) installieren? [J/n]"
if ($gpu -ne 'n') { uv pip install faster-whisper nvidia-cublas-cu12 nvidia-cudnn-cu12 }

if (-not (Test-Path .env)) {
  Copy-Item .env.example .env
  Write-Host ".env wurde angelegt – trage dort deinen ScaDS-API-Schlüssel ein (optional)." -ForegroundColor Cyan
}
Write-Host "Fertig. Start mit start.bat" -ForegroundColor Green
