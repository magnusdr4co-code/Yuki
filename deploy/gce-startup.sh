#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="yuki-prod"
REGION="europe-southwest1"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/yuki/yuki-agent:latest"
DISK="/dev/disk/by-id/google-yuki-data"
DATA_DIR="/var/lib/yuki/data"
SECRET_NAME="projects/${PROJECT_ID}/secrets/yuki-openrouter-api-key/versions/latest"
DISCORD_SECRET_NAME="projects/${PROJECT_ID}/secrets/yuki-discord-bot-token/versions/latest"

export DEBIAN_FRONTEND=noninteractive
if ! command -v docker >/dev/null 2>&1; then
  apt-get -o Acquire::ForceIPv4=true update
  apt-get -o Acquire::ForceIPv4=true install -y --no-install-recommends docker.io curl ca-certificates python3
fi
systemctl enable --now docker

for _ in $(seq 1 30); do
  [[ -e "$DISK" ]] && break
  sleep 2
done
[[ -e "$DISK" ]]

if ! blkid "$DISK" >/dev/null 2>&1; then
  mkfs.ext4 -F "$DISK"
fi
mkdir -p "$DATA_DIR"
UUID="$(blkid -s UUID -o value "$DISK")"
grep -q "UUID=${UUID} ${DATA_DIR} " /etc/fstab || \
  echo "UUID=${UUID} ${DATA_DIR} ext4 defaults,nofail 0 2" >> /etc/fstab
mountpoint -q "$DATA_DIR" || mount "$DATA_DIR"
mkdir -p "$DATA_DIR/output" "$DATA_DIR/cache"
chown -R 10001:10001 "$DATA_DIR"

cat > /opt/yuki.env <<'YUKI_ENV'
ENVIRONMENT=production
LOG_LEVEL=INFO
DATABASE_PATH=/app/data/yuki_memory.db
NOUS_PORTAL_MODE=disabled
# Vertex AI usa la identidad de servicio de la VM (ADC), sin claves adicionales.
VERTEX_PROJECT_ID=yuki-prod
VERTEX_LOCATION=global
# Servidores autorizados (Temple, Dev Server) — sin restricción por canal por ahora
DISCORD_ALLOWED_GUILD_ID=1539988095523623065,1472671221027045648
# Sin restricción por canal (vacío = todos los canales permitidos en guilds autorizados)
DISCORD_ALLOWED_CHANNEL_ID=
# Productor emparejado para DMs Hermes (Dextrure); el pairing se confirma vía DM !pair
DISCORD_PAIRED_PRODUCER_ID=235796491988369408
YUKI_ENV

# Secret Manager es la fuente de verdad. El fichero de runtime vive solo durante
# el arranque y se elimina al salir; nunca se incluye en la imagen ni en el repo.
RUNTIME_ENV="$(mktemp /run/yuki-runtime-env.XXXXXX)"
trap 'rm -f "$RUNTIME_ENV"' EXIT
chmod 600 "$RUNTIME_ENV"
cat /opt/yuki.env > "$RUNTIME_ENV"
METADATA_TOKEN="$(curl -fsS -H 'Metadata-Flavor: Google' \
  'http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"
fetch_secret() {
  local secret_name="$1"
  local env_name="$2"
  curl -fsS -H "Authorization: Bearer ${METADATA_TOKEN}" \
    "https://secretmanager.googleapis.com/v1/${secret_name}:access" \
    | python3 -c "import base64,json,sys; print('${env_name}=' + base64.b64decode(json.load(sys.stdin)['payload']['data']).decode('utf-8'))" \
    >> "$RUNTIME_ENV"
}
fetch_secret "$SECRET_NAME" OPENROUTER_API_KEY
fetch_secret "$DISCORD_SECRET_NAME" DISCORD_BOT_TOKEN

# Secretos opcionales. `fetch_secret` es estricto —si falta, el arranque muere—
# y eso es correcto para los dos de arriba: sin ellos Yuki no habla con nadie.
# Éstos habilitan capacidades y su ausencia es un estado legítimo: la instancia
# arranca igual y `cli.py virtualize` dice qué quedó inactivo. Un secreto que
# falta no puede tumbar la VM.
fetch_secret_opcional() {
  local secret_name="$1"
  local env_name="$2"
  if fetch_secret "$secret_name" "$env_name" 2>/dev/null; then
    echo "yuki-startup: ${env_name} tomado de Secret Manager" >&2
  else
    echo "yuki-startup: ${env_name} no declarado; la capacidad queda inactiva" >&2
  fi
}
# Sin esto las rutas /api del Salón quedan ABIERTAS en el 8080 y la descarga de
# obra no se enciende. Es lo primero que conviene declarar tras el primer arranque.
fetch_secret_opcional "projects/${PROJECT_ID}/secrets/yuki-salon-api-token/versions/latest" SALON_API_TOKEN
# Sin bucket, la copia queda en el mismo disco que el original y no protege del
# escenario que la justifica: perder el disco.
fetch_secret_opcional "projects/${PROJECT_ID}/secrets/yuki-backup-gcs-bucket/versions/latest" BACKUP_GCS_BUCKET
# Difusión por Telegram. La salida es real; la entrada no está implementada.
fetch_secret_opcional "projects/${PROJECT_ID}/secrets/yuki-telegram-bot-token/versions/latest" TELEGRAM_BOT_TOKEN
fetch_secret_opcional "projects/${PROJECT_ID}/secrets/yuki-telegram-chat-id/versions/latest" TELEGRAM_DEFAULT_CHAT_ID
unset METADATA_TOKEN

# Refresh the image when possible so a new :latest is picked up after a deploy;
# keep a cached copy as a safe boot fallback during a transient registry failure.
TOKEN_JSON="$(curl -fsS -H 'Metadata-Flavor: Google' \
  'http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token')"
ACCESS_TOKEN="$(printf '%s' "$TOKEN_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"
printf '%s' "$ACCESS_TOKEN" | docker login -u oauth2accesstoken --password-stdin \
  "${REGION}-docker.pkg.dev" >/dev/null
unset TOKEN_JSON ACCESS_TOKEN
if ! docker pull "$IMAGE"; then
  docker image inspect "$IMAGE" >/dev/null 2>&1
fi
docker logout "${REGION}-docker.pkg.dev" >/dev/null 2>&1 || true
docker rm -f yuki-salon yuki-daemon >/dev/null 2>&1 || true
docker run -d --name yuki-salon --restart unless-stopped \
  --env-file "$RUNTIME_ENV" -p 8080:8080 \
  -v "$DATA_DIR:/app/data" -v "$DATA_DIR/output:/app/output" \
  "$IMAGE" python cli.py web
docker run -d --name yuki-daemon --restart unless-stopped \
  --no-healthcheck \
  --env-file "$RUNTIME_ENV" \
  -v "$DATA_DIR:/app/data" -v "$DATA_DIR/output:/app/output" \
  "$IMAGE" python cli.py run-daemon
