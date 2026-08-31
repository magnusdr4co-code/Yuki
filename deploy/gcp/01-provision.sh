#!/usr/bin/env bash
# ==========================================================
# Fase 1 — Cimientos: APIs, identidad, registro, red, disco y VM.
# Idempotente: se puede ejecutar varias veces sin romper nada.
# ==========================================================
source "$(dirname "$0")/00-variables.sh"

gcloud config set project "$PROJECT_ID" >/dev/null

echo "▸ 1/7 Habilitando APIs (tarda un par de minutos la primera vez)"
gcloud services enable \
  compute.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com storage.googleapis.com \
  logging.googleapis.com monitoring.googleapis.com \
  cloudbuild.googleapis.com iap.googleapis.com

echo "▸ 2/7 Cuenta de servicio con permisos mínimos"
gcloud iam service-accounts describe "$SA_EMAIL" >/dev/null 2>&1 || \
  gcloud iam service-accounts create "$SA_NAME" --display-name="Yuki runtime"
for role in roles/secretmanager.secretAccessor roles/logging.logWriter \
            roles/monitoring.metricWriter roles/artifactregistry.reader; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA_EMAIL}" --role="$role" \
    --condition=None --quiet >/dev/null
done

echo "▸ 3/7 Registro de imágenes y bucket de media/backups"
gcloud artifacts repositories describe "$AR_REPO" --location="$REGION" >/dev/null 2>&1 || \
  gcloud artifacts repositories create "$AR_REPO" \
    --repository-format=docker --location="$REGION" \
    --description="Imágenes de Yuki"
gcloud storage buckets describe "gs://${BUCKET}" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://${BUCKET}" \
    --location="$REGION" --uniform-bucket-level-access
gcloud storage buckets update "gs://${BUCKET}" --versioning >/dev/null
# El bucket sólo lo escribe Yuki, y sólo dentro de él.
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member="serviceAccount:${SA_EMAIL}" --role="roles/storage.objectAdmin" >/dev/null

echo "▸ 4/7 Cortafuegos: cero ingreso salvo SSH por IAP"
gcloud compute firewall-rules describe yuki-allow-iap-ssh >/dev/null 2>&1 || \
  gcloud compute firewall-rules create yuki-allow-iap-ssh \
    --direction=INGRESS --action=allow --rules=tcp:22 \
    --source-ranges=35.235.240.0/20 --target-tags=yuki \
    --description="SSH sólo a través de Identity-Aware Proxy"
gcloud compute firewall-rules describe yuki-deny-all-ingress >/dev/null 2>&1 || \
  gcloud compute firewall-rules create yuki-deny-all-ingress \
    --direction=INGRESS --action=deny --rules=all \
    --source-ranges=0.0.0.0/0 --target-tags=yuki --priority=65000 \
    --description="Nada entra desde internet: Yuki sólo abre conexiones salientes"

echo "▸ 5/7 Disco persistente para la memoria SQLite"
gcloud compute disks describe "$DATA_DISK" --zone="$ZONE" >/dev/null 2>&1 || \
  gcloud compute disks create "$DATA_DISK" \
    --size="$DATA_DISK_SIZE" --type="$DISK_TYPE" --zone="$ZONE"

echo "▸ 6/7 Preparando cloud-init"
TMP_INIT="$(mktemp)"
sed -e "s|__IMAGE__|${IMAGE}|g" \
    -e "s|__TAG__|${IMAGE_TAG}|g" \
    -e "s|__REGION__|${REGION}|g" \
    -e "s|__BUCKET__|${BUCKET}|g" \
    -e "s|__AGENT_TZ__|${AGENT_TZ}|g" \
    -e "s|__SECRET_LIST__|${REQUIRED_SECRETS[*]} ${OPTIONAL_SECRETS[*]}|g" \
    "$(dirname "$0")/cloud-init.yaml" > "$TMP_INIT"

echo "▸ 7/7 Creando la VM"
if gcloud compute instances describe "$VM_NAME" --zone="$ZONE" >/dev/null 2>&1; then
  echo "  la VM ya existe; para aplicar un cloud-init nuevo usa 04-deploy.sh o recréala a mano"
else
  gcloud compute instances create "$VM_NAME" \
    --zone="$ZONE" --machine-type="$MACHINE_TYPE" \
    --image-family=cos-stable --image-project=cos-cloud \
    --boot-disk-size="$BOOT_DISK_SIZE" --boot-disk-type="$DISK_TYPE" \
    --disk="name=${DATA_DISK},device-name=${DATA_DISK},mode=rw,auto-delete=no" \
    --service-account="$SA_EMAIL" \
    --scopes=https://www.googleapis.com/auth/cloud-platform \
    --tags=yuki \
    --metadata-from-file=user-data="$TMP_INIT" \
    --shielded-secure-boot --shielded-vtpm --shielded-integrity-monitoring \
    --labels=app=yuki,env=prod
fi
rm -f "$TMP_INIT"

cat <<FIN

✔ Infraestructura lista.

  Siguiente:  ./deploy/gcp/02-secrets.sh      (subir las claves)
              ./deploy/gcp/03-build-push.sh   (construir la imagen)
              ./deploy/gcp/04-deploy.sh       (arrancar a Yuki)

  Nota sobre la IP: la VM se crea con IP externa efímera porque la alternativa
  (sin IP + Cloud NAT) cuesta más que la propia IP, y Yuki necesita salida a
  internet. No entra nada: el cortafuegos deniega todo el ingreso y el acceso
  es por IAP. Revisa esta línea en la factura del primer mes.
FIN
