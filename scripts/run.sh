#!/usr/bin/env bash
# Arranca GeoSms911 en Linux/macOS.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ ! -d ".venv" ]; then
  echo "Creando entorno virtual…"
  python3 -m venv .venv
fi

echo "Instalando dependencias…"
./.venv/bin/python -m pip install --quiet --upgrade pip
./.venv/bin/python -m pip install --quiet -r backend/requirements.txt

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo ""
  echo "Se creó .env. Edítalo (mínimo APP_SECRET) y vuelve a ejecutar este script."
  exit 1
fi

echo ""
echo "GeoSms911 en http://127.0.0.1:8000  (Ctrl+C para detener)"
echo "Documentación de la API: http://127.0.0.1:8000/api/docs"
echo ""

cd backend
exec ../.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
