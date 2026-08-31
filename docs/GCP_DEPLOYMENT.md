# 🚀 Despliegue en Google Cloud — `e2-micro` (nivel gratuito)

*Pasos exactos para poner a Yuki en marcha 24/7 sobre una `e2-micro` de Compute Engine. Ejecuta la fase 1 del plan de [`INFRASTRUCTURE_IMPLEMENTATION.md`](INFRASTRUCTURE_IMPLEMENTATION.md) (decisiones D-7 y D-8).*

> **Tiempo total:** 45–60 minutos, casi todo espera de APIs y del primer build.
> **Coste objetivo:** 0 USD de infraestructura, salvo la IP externa (§8).
> Todo lo que sigue vive en [`deploy/gcp/`](../deploy/gcp/).

---

## 0. Qué vas a construir

```
Tu máquina                     Google Cloud (proyecto yuki-prod)
──────────                     ─────────────────────────────────
gcloud + .env  ──02──▶  Secret Manager ─┐
                                        │ (arranque)
código  ──03──▶  Cloud Build ──▶ Artifact Registry ──┐
                                        │            │
                                        ▼            ▼
                          ┌───────────────────────────────────┐
                          │  VM e2-micro · Container-Opt. OS  │
                          │  systemd: yuki.service            │
                          │    └ contenedor Yuki (Hermes)     │
                          │  swap 1 GB · sin ingreso          │
                          └──────────────┬────────────────────┘
                                         │
                     disco persistente 20 GB  ← SQLite FTS5 + output/
                                         │
                              Cloud Storage ← copia diaria
```

Decisiones que explican el diseño:

| Elección | Por qué |
|---|---|
| **Compute Engine, no Cloud Run** | SQLite FTS5 necesita un sistema de ficheros POSIX con bloqueo real. GCS FUSE no lo da y corrompería la memoria |
| **Container-Optimized OS** | Docker ya instalado, superficie mínima, actualizaciones automáticas. **No trae `docker compose`**: por eso el contenedor corre como unidad systemd, no con `docker-compose.yml` |
| **Build en Cloud Build** | Una `e2-micro` tiene 1 GB de RAM: un `docker build` local la tumba |
| **Swap de 1 GB** | Margen para los picos de `ffmpeg` al transcodificar voz |
| **Secretos en tmpfs** | `/run/yuki/yuki.env` desaparece al apagar; no hay `.env` en disco |
| **IP externa efímera** | Yuki necesita salida a internet. Sin IP haría falta Cloud NAT, que cuesta **más** que la propia IP. El ingreso está denegado por completo y el acceso es por IAP |

---

## 1. Requisitos previos (en tu máquina)

```bash
gcloud --version          # si no lo tienes: https://cloud.google.com/sdk/docs/install
gcloud auth login
gcloud components install beta      # necesario para los túneles IAP
```

Necesitas además:
- Una **cuenta de facturación** activa (el nivel gratuito la exige igualmente).
- Un `.env` relleno a partir de `.env.example`. Como mínimo `NOUS_PORTAL_API_KEY`.

---

## 2. Crear el proyecto y **poner el freno de mano del presupuesto**

Hazlo **antes** de crear nada. Un bucle de cron mal configurado puede gastar en un día lo previsto para un mes.

```bash
gcloud projects create yuki-prod --name="Yuki"
gcloud billing accounts list                       # copia el ACCOUNT_ID
gcloud billing projects link yuki-prod --billing-account=XXXXXX-XXXXXX-XXXXXX
```

Y en la consola → **Facturación → Presupuestos y alertas**: presupuesto de 30 USD/mes con avisos al 50 %, 90 % y 100 %. No se puede crear cómodamente por CLI; son dos minutos de interfaz y es el paso que evita sustos.

---

## 3. Provisionar la infraestructura

```bash
export PROJECT_ID=yuki-prod
./deploy/gcp/01-provision.sh
```

Crea, de forma idempotente:

1. **APIs** — compute, artifactregistry, secretmanager, storage, logging, monitoring, cloudbuild, iap.
2. **Cuenta de servicio `yuki-runtime`** con cuatro roles y ni uno más: `secretAccessor`, `logWriter`, `metricWriter`, `artifactregistry.reader`. Nunca la cuenta por defecto de Compute.
3. **Artifact Registry** (`yuki`) y **bucket** de media y copias, con versionado y acceso uniforme.
4. **Cortafuegos** — dos reglas: SSH sólo desde el rango de IAP (`35.235.240.0/20`) y **denegar todo el resto del ingreso**. Yuki sólo abre conexiones salientes.
5. **Disco persistente** `yuki-data` de 20 GB `pd-standard`.
6. **VM `e2-micro`** con COS, Shielded VM y el `cloud-init` que lo orquesta todo.

> ⚠️ **`pd-standard`, no `pd-balanced`.** El nivel gratuito cubre 30 GB-mes de disco *estándar*. El de arranque (10 GB) más el de datos (20 GB) suman exactamente 30. Un disco balanceado factura desde el primer byte.

---

## 4. Subir los secretos

```bash
./deploy/gcp/02-secrets.sh .env
```

Sube cada clave presente en el `.env` como un secreto, ignorando las que sigan con el valor de ejemplo. **El `.env` nunca viaja a la VM.**

**Token OAuth del Portal.** `hermes setup --portal` necesita un navegador, que la VM no tiene. Autentícate en local y sube el resultado:

```bash
hermes setup --portal
gcloud secrets create HERMES_AUTH_JSON --data-file="$HOME/.hermes/auth.json"
```

Ese token caduca. Cuando lo haga, Yuki dejará de responder **sin dar error visible**: por eso el paso 7 configura una alerta específica.

---

## 5. Construir y publicar la imagen

```bash
./deploy/gcp/03-build-push.sh
```

Cloud Build construye el `Dockerfile` y publica dos etiquetas: `:latest` y `:<sha-de-git>`. La segunda es tu marcha atrás.

---

## 6. Desplegar y verificar

```bash
./deploy/gcp/04-deploy.sh
```

Arranca el servicio y ejecuta las comprobaciones de aceptación de la fase 1:

| Comprobación | Qué esperas ver |
|---|---|
| `systemctl is-active yuki` | `active` |
| `docker exec yuki date` | **Hora peninsular**, no UTC. Es lo que valida `tzdata` y `TZ` en la imagen |
| `cli.py memory-benchmark` | Latencia **< 150 ms** |
| `free -m` | ~1 GB de RAM con la swap disponible |

Prueba también que sobrevive a un reinicio, que es donde fallan los despliegues mal montados:

```bash
gcloud compute instances reset yuki-agent --zone=us-central1-a
sleep 60 && ./deploy/gcp/05-operar.sh estado
```

La base SQLite debe seguir intacta en el disco persistente.

---

## 7. Vigilancia mínima

En **Monitoring → Alertas**, tres alertas basadas en registros valen más que un panel bonito:

| Alerta | Condición | Por qué importa |
|---|---|---|
| **Agente caído** | Sin entradas de `yuki.service` en 30 min | El daemon murió o entró en bucle de reinicio |
| **Autenticación del Portal** | Registro con `401`, `unauthorized` o `invalid_token` | El token OAuth caducó: Yuki se queda muda en silencio |
| **Memoria al límite** | RAM > 850 MB sostenida | La `e2-micro` va justa; señal de que toca `e2-small` |

Y en **Facturación → Informes**, revisa a los pocos días la línea de **dirección IP externa**: es la única partida que puede salirse del nivel gratuito en este diseño.

---

## 8. Operación diaria

```bash
./deploy/gcp/05-operar.sh estado      # servicio, RAM y disco
./deploy/gcp/05-operar.sh logs        # registro en vivo
./deploy/gcp/05-operar.sh salon       # Salón Web en http://localhost:8080 por túnel IAP
./deploy/gcp/05-operar.sh backup      # copia manual de la memoria
./deploy/gcp/05-operar.sh parar       # apaga la VM (deja de consumir horas)
```

**Copias de seguridad.** Un temporizador systemd copia la memoria cada día a las 04:30 UTC usando `sqlite3 .backup` —consistente con la base en uso, cosa que un `cp` no garantiza— y la sube al bucket con versionado.

**Restauración** (probada, no teórica):

```bash
gcloud storage ls gs://yuki-prod-yuki-media/backups/
./deploy/gcp/05-operar.sh restaurar gs://yuki-prod-yuki-media/backups/yuki_memory_XXX.db
```

Pide confirmación escrita porque sustituye la memoria viva de Yuki.

---

## 9. Actualizar y revertir

```bash
git push                              # tu cambio
./deploy/gcp/03-build-push.sh         # nueva imagen
./deploy/gcp/04-deploy.sh             # despliegue

./deploy/gcp/04-deploy.sh a1b2c3d     # volver a un commit anterior
```

---

## 10. Cuando la `e2-micro` se quede corta

Señales: la alerta de RAM salta con frecuencia, el transcodificado de voz tarda, o la latencia con el productor molesta.

```bash
gcloud compute instances stop yuki-agent --zone=us-central1-a
gcloud compute instances set-machine-type yuki-agent --zone=us-central1-a --machine-type=e2-small
gcloud compute instances start yuki-agent --zone=us-central1-a
```

Sale del nivel gratuito (≈ 13–15 USD/mes). Para **mudarse a Europa** (supuesto S-1) hay que recrear la VM desde una instantánea del disco en `europe-southwest1`; son unos 30 minutos.

---

## 11. Problemas frecuentes

| Síntoma | Causa probable | Solución |
|---|---|---|
| `yuki.service` reinicia en bucle | Falta un secreto obligatorio | `journalctl -u yuki-secrets`; revisa `NOUS_PORTAL_API_KEY` |
| Yuki responde en texto pero no manda voz | `ffmpeg` sin memoria | Comprueba que la swap está activa: `swapon --show` |
| El *morning drop* llega una hora tarde | Falta `tzdata`/`TZ` en la imagen | `docker exec yuki date`; reconstruye la imagen |
| Yuki calla sin errores en el registro | Token OAuth del Portal caducado | Renueva `HERMES_AUTH_JSON` y `systemctl restart yuki-secrets yuki` |
| `docker pull` deniega el acceso | Falta el rol `artifactregistry.reader` | Reejecuta `01-provision.sh` |
| No hay salida a internet | Se creó la VM con `--no-address` | Necesita IP externa o Cloud NAT |
| El disco de datos aparece vacío | El formateo inicial no llegó a correr | `journalctl -u yuki-disk-init` |

---

## 12. Desmontarlo todo

```bash
gcloud compute instances delete yuki-agent --zone=us-central1-a
gcloud compute disks delete yuki-data --zone=us-central1-a   # ⚠ borra la memoria de Yuki
gcloud projects delete yuki-prod
```

Antes de borrar el disco, baja una copia: es la memoria completa de Yuki, y no hay otra.
