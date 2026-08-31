#!/usr/bin/env bash
# ==========================================================
# Variables compartidas por todos los scripts de despliegue.
# Cárgalo con:  source deploy/gcp/00-variables.sh
# ==========================================================
set -euo pipefail

# --- Identidad del proyecto ---
export PROJECT_ID="${PROJECT_ID:-yuki-prod}"

# --- Región y zona ---
# El nivel Always Free de e2-micro SÓLO aplica en us-west1, us-central1 y us-east1.
# Cambiar esto a una región europea implica pagar la VM (~15 USD/mes). Ver S-1 del
# documento de infraestructura.
export REGION="${REGION:-us-central1}"
export ZONE="${ZONE:-us-central1-a}"

# --- Recursos ---
export VM_NAME="${VM_NAME:-yuki-agent}"
export MACHINE_TYPE="${MACHINE_TYPE:-e2-micro}"
export DATA_DISK="${DATA_DISK:-yuki-data}"
export DATA_DISK_SIZE="${DATA_DISK_SIZE:-20GB}"   # 20 + 10 de arranque = 30 GB-mes gratis
export BOOT_DISK_SIZE="${BOOT_DISK_SIZE:-10GB}"
export DISK_TYPE="${DISK_TYPE:-pd-standard}"      # pd-balanced NO entra en el nivel gratuito

export SA_NAME="${SA_NAME:-yuki-runtime}"
export SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

export AR_REPO="${AR_REPO:-yuki}"
export IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/yuki"
export IMAGE_TAG="${IMAGE_TAG:-latest}"

export BUCKET="${BUCKET:-${PROJECT_ID}-yuki-media}"

# --- Zona horaria del agente (independiente de la región de la VM) ---
export AGENT_TZ="${AGENT_TZ:-Europe/Madrid}"

# --- Secretos esperados en Secret Manager ---
# El primero es obligatorio; el resto son opcionales según la fase.
export REQUIRED_SECRETS=(
  NOUS_PORTAL_API_KEY
)
export OPTIONAL_SECRETS=(
  OPENROUTER_API_KEY
  HONCHO_API_KEY
  TELEGRAM_BOT_TOKEN
  TELEGRAM_DEFAULT_CHAT_ID
  DISCORD_BOT_TOKEN
  DISCORD_ANNOUNCE_CHANNEL_ID
  ANTHROPIC_API_KEY
  OPENAI_API_KEY
)

echo "▸ Proyecto ${PROJECT_ID} · ${ZONE} · ${MACHINE_TYPE} · imagen ${IMAGE}:${IMAGE_TAG}"
