# Arranca GeoSms911 en Windows.
# Uso:  .\scripts\run.ps1
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv")) {
    Write-Host "Creando entorno virtual…" -ForegroundColor Cyan
    python -m venv .venv
}

Write-Host "Instalando dependencias…" -ForegroundColor Cyan
& .\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
& .\.venv\Scripts\python.exe -m pip install --quiet -r backend\requirements.txt

if (-not (Test-Path ".env")) {
    Copy-Item .env.example .env
    Write-Host ""
    Write-Host "Se creó .env. Edítalo (mínimo APP_SECRET) y vuelve a ejecutar este script." -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "GeoSms911 en http://127.0.0.1:8000  (Ctrl+C para detener)" -ForegroundColor Green
Write-Host "Documentación de la API: http://127.0.0.1:8000/api/docs" -ForegroundColor DarkGray
Write-Host ""

Set-Location backend
& ..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
