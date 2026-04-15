#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# LaborIA — Setup inicial del VPS (Hetzner CX21 / Ubuntu 24.04)
#
# Ejecutar UNA SOLA VEZ en el servidor:
#   ssh root@TU_IP 'bash -s' < scripts/server-setup.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

echo "=== [1/6] Actualizando sistema ==="
apt-get update -qq && apt-get upgrade -y -qq

echo "=== [2/6] Instalando Docker ==="
curl -fsSL https://get.docker.com | sh
systemctl enable docker
systemctl start docker

echo "=== [3/6] Instalando Docker Compose plugin ==="
apt-get install -y -qq docker-compose-plugin

echo "=== [4/6] Creando usuario laboria ==="
useradd -m -s /bin/bash -G docker laboria 2>/dev/null || echo "Usuario laboria ya existe"

echo "=== [5/6] Creando directorio de configuración ==="
mkdir -p /etc/laboria
chmod 700 /etc/laboria

echo "=== [6/6] Creando directorio nginx/certs ==="
# El repo se clonará aquí
mkdir -p /opt/laboria
chown laboria:laboria /opt/laboria

echo ""
echo "✅ Setup completo. Próximos pasos:"
echo ""
echo "  1. Sube el .env.prod al servidor:"
echo "     scp .env.production.example root@TU_IP:/etc/laboria/.env.prod"
echo "     # Edita /etc/laboria/.env.prod con tus valores reales"
echo ""
echo "  2. Clona el repositorio:"
echo "     cd /opt/laboria && git clone TU_REPO ."
echo ""
echo "  3. Ejecuta el deploy:"
echo "     bash /opt/laboria/scripts/deploy.sh"
