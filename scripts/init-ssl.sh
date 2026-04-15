#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# LaborIA — Obtener certificado Let's Encrypt (ejecutar UNA VEZ)
#
# Pre-requisitos:
#   1. El dominio api.laboria.app debe apuntar a la IP del VPS (DNS A record)
#   2. El servicio nginx debe estar corriendo (acepta el challenge HTTP-01)
#   3. Cambiar DOMAIN y EMAIL abajo
#
# Uso: bash scripts/init-ssl.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

DOMAIN="api.laboria.app"    # <-- CAMBIAR por tu dominio
EMAIL="tu@email.com"        # <-- CAMBIAR por tu email (notificaciones de expiración)
COMPOSE="docker compose -f docker-compose.prod.yml"

echo "=== Obteniendo certificado TLS para $DOMAIN ==="

# Levantar nginx en modo HTTP (solo para el challenge)
$COMPOSE up -d nginx

# Solicitar certificado
docker run --rm \
  -v "$(pwd)/nginx/certs:/etc/letsencrypt" \
  -v "$(pwd)/nginx/certbot_webroot:/var/www/certbot" \
  certbot/certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    -d "$DOMAIN"

echo "✅ Certificado obtenido en nginx/certs/live/$DOMAIN/"
echo ""
echo "Reiniciando nginx para activar HTTPS..."
$COMPOSE restart nginx

echo "✅ HTTPS activo en https://$DOMAIN"
