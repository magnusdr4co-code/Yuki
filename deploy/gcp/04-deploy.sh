#!/usr/bin/env bash
# ==========================================================
# Despliega la imagen actual en la VM y verifica que Yuki despierta.
#   ./deploy/gcp/04-deploy.sh [etiqueta]     (por defecto: latest)
# ==========================================================
source "$(dirname "$0")/00-variables.sh"
TAG="${1:-$IMAGE_TAG}"

ssh_vm() { gcloud compute ssh "$VM_NAME" --zone="$ZONE" --tunnel-through-iap --command "$1"; }

echo "▸ Desplegando ${IMAGE}:${TAG}"
ssh_vm "sudo sed -i 's|${IMAGE}:[^ ]*|${IMAGE}:${TAG}|g' /etc/systemd/system/yuki.service \
        && sudo systemctl daemon-reload \
        && sudo systemctl restart yuki-secrets yuki"

echo "▸ Esperando a que el contenedor levante"
sleep 15
ssh_vm "sudo systemctl is-active yuki && sudo docker ps --filter name=yuki --format '{{.Image}}  {{.Status}}'"

echo "
▸ Comprobaciones de salud"
ssh_vm "sudo docker exec yuki date"                      # ¿hora de Madrid?
ssh_vm "sudo docker exec yuki python3 cli.py memory-benchmark 2>&1 | tail -5"
ssh_vm "free -m | head -2"

echo "
✔ Desplegado. Registro en vivo:
  gcloud compute ssh $VM_NAME --zone=$ZONE --tunnel-through-iap --command 'sudo journalctl -u yuki -f'"
