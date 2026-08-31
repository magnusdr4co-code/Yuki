# `deploy/gcp/` — Despliegue de Yuki en Google Cloud

Scripts de la fase 1 del plan de infraestructura. El manual paso a paso, con
las comprobaciones y la resolución de problemas, está en
[`docs/GCP_DEPLOYMENT.md`](../../docs/GCP_DEPLOYMENT.md).

| Fichero | Qué hace |
|---|---|
| `00-variables.sh` | Variables comunes. Se carga con `source`; sobreescribibles por entorno |
| `01-provision.sh` | APIs, cuenta de servicio, Artifact Registry, bucket, cortafuegos, disco y VM |
| `02-secrets.sh` | Sube el `.env` local a Secret Manager (el `.env` nunca llega a la VM) |
| `03-build-push.sh` | Construye con Cloud Build y publica en Artifact Registry |
| `04-deploy.sh` | Despliega una etiqueta en la VM y ejecuta las comprobaciones de salud |
| `05-operar.sh` | Operación diaria: `estado`, `logs`, `salon`, `backup`, `restaurar`, `parar` |
| `cloud-init.yaml` | Arranque de Container-Optimized OS: disco, swap, secretos, servicio y copias |

## Puesta en marcha

```bash
export PROJECT_ID=yuki-prod
./deploy/gcp/01-provision.sh
./deploy/gcp/02-secrets.sh .env
./deploy/gcp/03-build-push.sh
./deploy/gcp/04-deploy.sh
```

## Tres cosas que conviene no cambiar sin saber por qué

1. **`pd-standard`, no `pd-balanced`.** El nivel gratuito cubre 30 GB-mes de
   disco estándar; arranque (10) + datos (20) suman justo eso.
2. **La región.** `e2-micro` sólo es gratuita en `us-west1`, `us-central1` y
   `us-east1`. Cualquier otra factura tarifa completa.
3. **La VM lleva IP externa.** No es un descuido: sin ella haría falta Cloud
   NAT, que cuesta más. El ingreso está denegado en su totalidad y el acceso es
   por IAP.
