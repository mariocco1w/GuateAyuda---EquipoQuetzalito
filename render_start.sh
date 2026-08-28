#!/usr/bin/env bash
# Punto de entrada para Render.
# - Inicializa/crea el esquema en PostgreSQL si hace falta.
# - Puebla datos demo solo si la base está vacía (safe, no destructivo).
# - Inicia el servidor WSGI con gunicorn.
set -e

echo "[GuateAyuda] Inicializando esquema si es necesario..."
python -c "import db; db.init_db()"

echo "[GuateAyuda] Sembrando datos demo (solo si la base está vacía)..."
python seed.py

echo "[GuateAyuda] Arrancando gunicorn..."
exec gunicorn app:app
