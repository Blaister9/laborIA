#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# LaborIA — Script de deploy en el VPS
#
# Ejecutar en el servidor (/opt/laboria/):
#   bash scripts/deploy.sh
#
# O remotamente desde tu máquina:
#   ssh root@TU_IP 'cd /opt/laboria && git pull && bash scripts/deploy.sh'
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

COMPOSE="docker compose -f docker-compose.prod.yml"
ENV_FILE="/etc/laboria/.env.prod"

echo "=== LaborIA Deploy ==="
date

# Verificar que el .env.prod existe
if [ ! -f "$ENV_FILE" ]; then
  echo "❌ ERROR: $ENV_FILE no encontrado."
  echo "   Copia .env.production.example → $ENV_FILE y rellena los valores."
  exit 1
fi

# Pull de la última imagen base (Qdrant, Nginx)
echo "=== [1/5] Actualizando imágenes base ==="
$COMPOSE pull qdrant nginx certbot --quiet

# Build de la imagen del backend
echo "=== [2/5] Building laboria-backend ==="
echo "    (Primera vez: ~10 min por descarga de modelos ML)"
docker build -t laboria-backend:latest .

# Crear directorio de certs si no existe
mkdir -p nginx/certs

# Reiniciar servicios con zero-downtime (Qdrant primero, luego backend)
echo "=== [3/5] Actualizando Qdrant ==="
$COMPOSE up -d --no-deps qdrant

echo "=== [4/5] Actualizando Backend ==="
$COMPOSE up -d --no-deps --remove-orphans backend

echo "=== [5/5] Actualizando Nginx ==="
$COMPOSE up -d --no-deps nginx

echo ""
echo "=== Estado de los servicios ==="
$COMPOSE ps

echo ""
echo "=== Healthcheck backend ==="
echo "Esperando que el backend esté listo (puede tardar ~90s por carga de modelos)..."
for i in $(seq 1 20); do
  if curl -sf http://localhost:8080/health > /dev/null 2>&1; then
    echo "✅ Backend listo!"
    curl -s http://localhost:8080/health | python3 -m json.tool 2>/dev/null || true
    break
  fi
  echo "   Intento $i/20 — esperando 10s..."
  sleep 10
done

echo ""
echo "✅ Deploy completado. Logs: docker compose -f docker-compose.prod.yml logs -f backend"
