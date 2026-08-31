#!/usr/bin/env bash
# ==========================================================
# Construye la imagen con Cloud Build y la publica en Artifact Registry.
#
# Se construye en Cloud Build, NO en la VM: una e2-micro con 1 GB de RAM
# no aguanta un `docker build` y se quedaría sin memoria.
# ==========================================================
source "$(dirname "$0")/00-variables.sh"

TAG="${IMAGE_TAG}"
GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo manual)"

echo "▸ Construyendo ${IMAGE}:${TAG} (y :${GIT_SHA}) con Cloud Build"
gcloud builds submit --tag "${IMAGE}:${TAG}" .

# Etiqueta adicional con el commit, para poder volver atrás.
gcloud artifacts docker tags add "${IMAGE}:${TAG}" "${IMAGE}:${GIT_SHA}" 2>/dev/null || true

echo "✔ Imagen publicada:
    ${IMAGE}:${TAG}
    ${IMAGE}:${GIT_SHA}   ← usa esta etiqueta para revertir"
