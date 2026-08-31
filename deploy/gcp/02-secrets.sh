#!/usr/bin/env bash
# ==========================================================
# Sube a Secret Manager las claves de un .env local.
# El .env nunca llega a la VM: los secretos se leen en arranque
# y viven en tmpfs (/run/yuki/yuki.env).
#
#   ./deploy/gcp/02-secrets.sh [ruta-al-.env]   (por defecto: .env)
# ==========================================================
source "$(dirname "$0")/00-variables.sh"
ENV_FILE="${1:-.env}"

[[ -f "$ENV_FILE" ]] || { echo "✖ No encuentro $ENV_FILE (copia .env.example y rellénalo)"; exit 1; }

upload() {
  local name="$1" value="$2"
  if [[ -z "$value" || "$value" == your_* ]]; then
    echo "  ○ $name sin valor real, se omite"; return
  fi
  if gcloud secrets describe "$name" >/dev/null 2>&1; then
    printf '%s' "$value" | gcloud secrets versions add "$name" --data-file=- >/dev/null
    echo "  ↻ $name actualizado"
  else
    printf '%s' "$value" | gcloud secrets create "$name" --data-file=- \
      --replication-policy=automatic >/dev/null
    echo "  + $name creado"
  fi
}

echo "▸ Leyendo $ENV_FILE"
missing=0
for name in "${REQUIRED_SECRETS[@]}" "${OPTIONAL_SECRETS[@]}"; do
  # Toma la última definición no comentada de la variable.
  value=$(grep -E "^${name}=" "$ENV_FILE" | tail -1 | cut -d= -f2- || true)
  upload "$name" "$value"
done

for name in "${REQUIRED_SECRETS[@]}"; do
  gcloud secrets describe "$name" >/dev/null 2>&1 || { echo "✖ Falta el secreto obligatorio $name"; missing=1; }
done
[[ $missing -eq 0 ]] || exit 1

echo "
▸ Token OAuth del Portal
  'hermes setup --portal' se autentica con un navegador, que la VM no tiene.
  Autentícate en tu máquina y sube el token resultante:

    gcloud secrets create HERMES_AUTH_JSON --data-file=\$HOME/.hermes/auth.json

  Vigila su caducidad: si expira, Yuki deja de responder sin previo aviso.
"
echo "✔ Secretos sincronizados. Reinicia la carga con:
  gcloud compute ssh $VM_NAME --zone=$ZONE --tunnel-through-iap \\
    --command 'sudo systemctl restart yuki-secrets yuki'"
