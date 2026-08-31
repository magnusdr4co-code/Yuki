#!/usr/bin/env bash
# ==========================================================
# Atajos de operación diaria.
#   ./deploy/gcp/05-operar.sh logs|estado|salon|backup|restaurar|coste|parar|arrancar
# ==========================================================
source "$(dirname "$0")/00-variables.sh"
ssh_vm() { gcloud compute ssh "$VM_NAME" --zone="$ZONE" --tunnel-through-iap --command "$1"; }

case "${1:-estado}" in
  logs)     ssh_vm "sudo journalctl -u yuki -f" ;;
  estado)   ssh_vm "sudo systemctl status yuki --no-pager | head -12; echo; free -m | head -2; echo; df -h /mnt/disks/yuki-data | tail -1" ;;
  # Túnel al Salón Web: la VM no expone el 8080 a internet, se accede por IAP.
  salon)    echo "→ http://localhost:8080"; gcloud compute start-iap-tunnel "$VM_NAME" 8080 --local-host-port=localhost:8080 --zone="$ZONE" ;;
  backup)   ssh_vm "sudo systemctl start yuki-backup && sudo journalctl -u yuki-backup -n 5 --no-pager" ;;
  restaurar)
      [[ -n "${2:-}" ]] || { echo "uso: $0 restaurar gs://${BUCKET}/backups/yuki_memory_XXX.db"; exit 1; }
      echo "⚠ Esto sustituye la memoria viva de Yuki por la copia $2"
      read -r -p "Escribe 'restaurar' para continuar: " ok; [[ "$ok" == "restaurar" ]] || exit 1
      ssh_vm "sudo systemctl stop yuki && \
        sudo docker run --rm --network=host -v /mnt/disks/yuki-data/data:/data \
          gcr.io/google.com/cloudsdktool/google-cloud-cli:stable \
          gcloud storage cp '$2' /data/yuki_memory.db && \
        sudo systemctl start yuki" ;;
  coste)    gcloud billing accounts list; echo; echo "Detalle por servicio: consola → Facturación → Informes" ;;
  parar)    gcloud compute instances stop "$VM_NAME" --zone="$ZONE" ;;
  arrancar) gcloud compute instances start "$VM_NAME" --zone="$ZONE" ;;
  *)        grep '^#   ' "$0" ;;
esac
