#!/usr/bin/env bash
# ==========================================
# Prepara un proyecto de Google Cloud para Yuki:
# APIs, cuentas de servicio, permisos, secretos, registro y bucket.
#
# Es idempotente: se puede ejecutar varias veces sin romper nada.
#
#   ./scripts/gcp_bootstrap.sh yuki-diva europe-southwest1
#
# Después:
#   gcloud builds submit --config cloudbuild.yaml \
#     --substitutions=_REGION=<region>,_BUCKET=<project>-yuki-data
# ==========================================

set -euo pipefail

PROJECT_ID="${1:-}"
REGION="${2:-europe-southwest1}"

if [[ -z "$PROJECT_ID" ]]; then
  echo "Uso: $0 <PROJECT_ID> [REGION]" >&2
  exit 1
fi

if ! command -v gcloud >/dev/null 2>&1; then
  echo "❌ Falta la CLI de gcloud: https://cloud.google.com/sdk/docs/install" >&2
  exit 1
fi

RUNTIME_SA="yuki-runtime@${PROJECT_ID}.iam.gserviceaccount.com"
SCHEDULER_SA="yuki-scheduler@${PROJECT_ID}.iam.gserviceaccount.com"
BUCKET="${PROJECT_ID}-yuki-data"

echo "⛩️  Preparando Google Cloud para Yuki"
echo "   Proyecto: ${PROJECT_ID}"
echo "   Región:   ${REGION}"
echo

gcloud config set project "$PROJECT_ID" >/dev/null

# --- 1. APIs ---------------------------------------------------------------
echo "▸ Habilitando APIs..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  cloudscheduler.googleapis.com \
  storage.googleapis.com
echo "  ✓ APIs habilitadas"

# --- 2. Cuentas de servicio ------------------------------------------------
ensure_sa() {
  local name=$1 display=$2
  if gcloud iam service-accounts describe "${name}@${PROJECT_ID}.iam.gserviceaccount.com" >/dev/null 2>&1; then
    echo "  · ${name} ya existe"
  else
    gcloud iam service-accounts create "$name" --display-name="$display" >/dev/null
    echo "  ✓ ${name} creada"
  fi
}

echo "▸ Cuentas de servicio..."
ensure_sa yuki-runtime   "Yuki — identidad de ejecución"
ensure_sa yuki-scheduler "Yuki — disparador de tareas"

grant() {
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$1" --role="$2" --condition=None >/dev/null
  echo "  ✓ $2 → ${1%%@*}"
}

echo "▸ Permisos (mínimo necesario)..."
grant "$RUNTIME_SA"   roles/secretmanager.secretAccessor
grant "$RUNTIME_SA"   roles/storage.objectAdmin
grant "$RUNTIME_SA"   roles/logging.logWriter
grant "$SCHEDULER_SA" roles/run.invoker

# --- 3. Artifact Registry --------------------------------------------------
echo "▸ Registro de imágenes..."
if gcloud artifacts repositories describe yuki --location="$REGION" >/dev/null 2>&1; then
  echo "  · repositorio 'yuki' ya existe"
else
  gcloud artifacts repositories create yuki \
    --repository-format=docker --location="$REGION" \
    --description="Imágenes de Yuki" >/dev/null
  echo "  ✓ repositorio 'yuki' creado"
fi

# --- 4. Bucket de memoria --------------------------------------------------
echo "▸ Bucket de memoria persistente..."
if gcloud storage buckets describe "gs://${BUCKET}" >/dev/null 2>&1; then
  echo "  · gs://${BUCKET} ya existe"
else
  gcloud storage buckets create "gs://${BUCKET}" \
    --location="$REGION" --uniform-bucket-level-access >/dev/null
  echo "  ✓ gs://${BUCKET} creado"
fi

# --- 5. Secretos -----------------------------------------------------------
# Se leen del entorno si están definidos; si no, se pide por teclado.
# Un secreto vacío se omite: puedes añadirlo más tarde sin rehacer nada.
echo "▸ Secretos..."
put_secret() {
  local secret_name=$1 env_var=$2 value
  value="${!env_var:-}"

  if [[ -z "$value" ]]; then
    read -r -s -p "   ${env_var} (Enter para omitir): " value
    echo
  fi

  if [[ -z "$value" ]]; then
    echo "  · ${secret_name} omitido"
    return
  fi

  if gcloud secrets describe "$secret_name" >/dev/null 2>&1; then
    printf '%s' "$value" | gcloud secrets versions add "$secret_name" --data-file=- >/dev/null
    echo "  ✓ ${secret_name} actualizado (nueva versión)"
  else
    printf '%s' "$value" | gcloud secrets create "$secret_name" \
      --data-file=- --replication-policy=automatic >/dev/null
    echo "  ✓ ${secret_name} creado"
  fi
}

put_secret yuki-anthropic-api-key  ANTHROPIC_API_KEY
put_secret yuki-honcho-api-key     HONCHO_API_KEY
put_secret yuki-telegram-bot-token TELEGRAM_BOT_TOKEN
put_secret yuki-discord-bot-token  DISCORD_BOT_TOKEN

# --- Resumen ---------------------------------------------------------------
cat <<SUMMARY

──────────────────────────────────────────────
✅ Google Cloud preparado para Yuki

   Proyecto        ${PROJECT_ID}
   Región          ${REGION}
   Ejecución       ${RUNTIME_SA}
   Planificador    ${SCHEDULER_SA}
   Memoria         gs://${BUCKET}

Siguiente paso — desplegar:

   gcloud builds submit --config cloudbuild.yaml \\
     --substitutions=_REGION=${REGION},_BUCKET=${BUCKET}

Luego programa el ritmo circadiano siguiendo la sección 6 de
docs/GCP_DEPLOYMENT.md.

Recuerda poner un presupuesto con alertas antes de dejarlo solo.
──────────────────────────────────────────────
SUMMARY
