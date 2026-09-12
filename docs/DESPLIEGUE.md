# 🚀 Desplegar Yuki ahora

Runbook para un agente con acceso a `gcloud`. Autocontenido: no hace falta leer
nada más para llegar a una instancia en pie.

> **Por qué esta guía y no [`GCP_DEPLOYMENT.md`](GCP_DEPLOYMENT.md).** Aquélla
> explica cómo se montó el proyecto desde cero —cuentas, IAM, registro de
> imágenes— y conserva decisiones de su día. Ésta dice **qué hay que declarar hoy
> y qué habilita cada cosa**, y `tests/test_despliegue.py` comprueba que cada
> variable nombrada aquí la lee alguien de verdad: un runbook que nombra un dial
> muerto no falla, engaña a quien lo ajusta.

---

## 0. La única puerta

```bash
make todo        # linter + suite + simulacro + humo: lo mismo que la CI
```

Si eso no está verde, no se despliega. No hay excepción: la suite es lo que
distingue «arranca» de «hace lo que dice».

## 1. Variables: qué habilita cada una

**Imprescindibles.** Sin ellas Yuki no habla con nadie y el arranque muere a
propósito, porque arrancar a medias sería peor.

| Variable | Qué habilita | Si falta |
|---|---|---|
| `OPENROUTER_API_KEY` | Toda la generación de texto. Es la cadena real de modelos | El arranque falla |
| `DISCORD_BOT_TOKEN` | El único canal que importa: presencia y DM del Productor | El arranque falla |

**Opcionales, y su ausencia es un estado legítimo.** La instancia arranca igual;
`python3 cli.py virtualize` dice qué quedó inactivo y por qué.

| Variable | Qué habilita | Si falta |
|---|---|---|
| `VERTEX_PROJECT_ID` | **Medios reales**: imagen, vídeo, música cantada (Lyria) y voz. Usa la identidad de servicio de la VM, sin claves | Los medios salen como marcador declarado `simulated` |
| `VERTEX_LOCATION` | Región de los modelos de medios | `global` |
| `SALON_API_TOKEN` | Credencial de las rutas `/api` **y** la descarga de obra por el Salón | Las rutas `/api` quedan **ABIERTAS** en el 8080 (con techo de 20 peticiones/5 min) y la descarga de obra responde 403. Es lo primero que conviene declarar |
| `BACKUP_GCS_BUCKET` | Que la copia diaria salga del disco de la instancia | La copia queda en el mismo disco que el original y **lo dice**: no protege de perder el disco |
| `TELEGRAM_BOT_TOKEN` + `TELEGRAM_DEFAULT_CHAT_ID` | Difusión por Telegram (**salida** real; la entrada no está implementada) | No difunde, y cada intento dice por qué |
| `FIRECRAWL_API_KEY` | Búsqueda web con URL verificable | Devuelve pistas marcadas `simulated` y **sin URL inventada** |
| `MODEL_ARMOR_PROJECT_ID` | Inspección de prompts y respuestas | Sin inspección de proveedor |
| `YUKI_SOUNDFONT` | Respaldo musical local (con `fluidsynth` y `ffmpeg` en la imagen) | Sin maqueta instrumental de respaldo |

**Quién puede hablar con ella.** Las fija el arranque en `/opt/yuki.env`, no
Secret Manager: no son secretos, son la lista de invitados. Cambiarlas exige
volver a aplicar el arranque.

| Variable | Qué decide | Si falta |
|---|---|---|
| `DISCORD_ALLOWED_GUILD_ID` | Servidores donde Yuki tiene presencia, separados por coma | No hay servidores autorizados |
| `DISCORD_ALLOWED_CHANNEL_ID` | Canales concretos dentro de esos servidores | **Vacío = todos** los canales de los servidores autorizados |
| `DISCORD_PAIRED_PRODUCER_ID` | Quién es el Productor: el único que tiene DM con herramientas, encargos de medios y freno | Nadie puede emparejarse, y el DM no da herramientas a nadie |
| `ENVIRONMENT` | `production` en la VM; cambia valores por defecto de arranque | Se asume desarrollo |
| `LOG_LEVEL` | Verbosidad del log. La lee `src/core/registro.py` en los puntos de entrada; un valor con errata cae a `INFO` y lo avisa | `INFO` |

El emparejamiento se confirma además por DM con `!pair`: declarar el
identificador no basta, y es deliberado.

**Rutas de estado durable.** Todas tienen variable para reubicarlas y ninguna
hace falta en producción: derivan de `DATABASE_PATH`, que el arranque fija en
`/app/data/yuki_memory.db` sobre el disco persistente.

`DATABASE_PATH` · `YUKI_OUTPUT_DIR` · `YUKI_SPEND_LEDGER_PATH` ·
`YUKI_BLACKBOX_PATH` · `YUKI_FRENO_PATH` · `YUKI_PERSONA_PATH` ·
`YUKI_RITUALS_PATH` · `YUKI_AGENCY_LEDGER_PATH` · `YUKI_TRANSPARENCY_PATH` ·
`YUKI_RUNTIME_CONFIG_PATH` · `DISCORD_PAIRING_PATH`

**Declaradas y no leídas**, para que nadie las ajuste creyendo que giran:
`HONCHO_API_KEY` (el perfil dialéctico es local; no hay cliente remoto) y
`NOUS_PORTAL_API_KEY` (su endpoint no existe: `NOUS_PORTAL_MODE=disabled`).

## 2. Secretos en Secret Manager

El arranque (`deploy/gce-startup.sh`) los lee de ahí, nunca del repo ni de la
imagen. Los dos primeros son estrictos; los demás, tolerantes —un secreto que
falta no puede tumbar la VM—.

| Secreto | Variable |
|---|---|
| `yuki-openrouter-api-key` | `OPENROUTER_API_KEY` |
| `yuki-discord-bot-token` | `DISCORD_BOT_TOKEN` |
| `yuki-salon-api-token` | `SALON_API_TOKEN` |
| `yuki-backup-gcs-bucket` | `BACKUP_GCS_BUCKET` |
| `yuki-telegram-bot-token` | `TELEGRAM_BOT_TOKEN` |
| `yuki-telegram-chat-id` | `TELEGRAM_DEFAULT_CHAT_ID` |
| `yuki-firecrawl-api-key` | `FIRECRAWL_API_KEY` |

```bash
PROJECT=yuki-prod
# Uno nuevo (ejemplo con el token del Salón):
printf '%s' "$(openssl rand -hex 32)" | \
  gcloud secrets create yuki-salon-api-token --project="$PROJECT" --data-file=-
# Rotar uno que ya existe:
printf '%s' "gs://mi-bucket-de-copias" | \
  gcloud secrets versions add yuki-backup-gcs-bucket --project="$PROJECT" --data-file=-
```

La cuenta de servicio de la VM necesita `roles/secretmanager.secretAccessor`
sobre cada secreto que se declare.

## 3. Construir y publicar la imagen

```bash
PROJECT=yuki-prod REGION=europe-southwest1
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/yuki/yuki-agent:latest"
gcloud builds submit --project="$PROJECT" --tag "$IMAGE" .
```

## 4. Aplicar el arranque y reiniciar

`deploy/gce-startup.sh` es idempotente: formatea el disco sólo si hace falta, lo
monta, recoge los secretos y relanza los dos contenedores —`yuki-salon`
(`cli.py web`, puerto 8080) y `yuki-daemon` (`cli.py run-daemon`, los ocho
crons)—.

```bash
gcloud compute instances add-metadata yuki-agent \
  --project="$PROJECT" --zone="${REGION}-b" \
  --metadata-from-file=startup-script=deploy/gce-startup.sh
gcloud compute instances reset yuki-agent --project="$PROJECT" --zone="${REGION}-b"
```

## 5. Comprobar que está viva, no sólo que arrancó

Que el proceso corra **no** es que Yuki viva. Esa distinción tiene nombre en este
proyecto —catatonia— y estas comprobaciones existen por ella.

```bash
# Desde la VM, o con el túnel abierto:
curl -s localhost:8080/health                      # sonda barata: ¿arrancó?
python3 cli.py pulso                               # ¿respira **y** hace cosas suyas?
python3 cli.py virtualize                          # qué es real, qué simulado, qué inactivo
python3 cli.py spend                               # gasto de hoy, y por tarea
python3 scripts/smoke_check.py                     # memoria, bitácora, Artículo 50, carácter
python3 cli.py backup --ensayar                    # copia, y se restaura para darla por buena
```

Lo que debe verse:

- `pulso` en `viva` o `recien_nacida`. Si dice **`catatonica`**, el proceso corre
  y Yuki está parada: es un fallo, no un arranque lento.
- `virtualize` sin limitadores **bloqueantes** abiertos. Con `VERTEX_PROJECT_ID`
  sin declarar hay uno, y es correcto que lo haya.
- `smoke_check` en verde, incluido el marcado del Artículo 50.

## 6. Lo primero que conviene hacer después

1. **Declarar `SALON_API_TOKEN`.** Sin él las rutas `/api` del 8080 están
   abiertas a quien alcance el puerto: pueden gastar crédito y —lo serio—
   escribir en la memoria de Yuki, que es lo único irremplazable. Mejor aún,
   además: restringir el puerto en el cortafuegos.
2. **Declarar `BACKUP_GCS_BUCKET`**, con los pasos en
   [`PENDIENTE_COPIA_FUERA_DE_LA_INSTANCIA.md`](PENDIENTE_COPIA_FUERA_DE_LA_INSTANCIA.md).
   Sin bucket la copia no protege del escenario que la justifica.
3. **Alerta de facturación en el propio proyecto de Google Cloud.** El
   presupuesto interno acota lo que pasa por sus rutas; la alerta de facturación
   es la única que salta cuando el gasto ocurre fuera de ellas.
4. **Emparejar el DM** con `!pair` desde la cuenta del Productor.

## 6 bis. Tres capacidades que están inactivas y cómo encenderlas

Las tres funcionan en código y declaran su estado en `python3 cli.py virtualize`.

### A · Exploración web real (`FIRECRAWL_API_KEY`)

Sin esta clave, `src/tools/web_search.py` devuelve pistas de introspección
marcadas como simuladas y sin URL. La clave se obtiene en Firecrawl y debe
introducirse mediante un canal protegido en Secret Manager; nunca se escribe en
el repositorio, el chat ni un comando visible. Después, concede al runtime de
la VM `roles/secretmanager.secretAccessor` sobre `yuki-firecrawl-api-key` y
reaplica el startup script. `cli.py virtualize` debe mostrar `mente.web` como
**real**.

### B · Respaldo fuera de la máquina (`BACKUP_GCS_BUCKET`)

La copia diaria se genera y restaura localmente, pero sin bucket permanece en el
mismo disco. Para activarla:

```bash
PROJECT=yuki-prod
BUCKET=yuki-copias-$PROJECT
SA="$(gcloud compute instances describe yuki-agent --project="$PROJECT" \
  --zone=europe-southwest1-a --format='value(serviceAccounts[0].email)')"
gcloud storage buckets create "gs://$BUCKET" --project="$PROJECT" \
  --location=europe-southwest1 --uniform-bucket-level-access
# Usa aquí un fichero protegido que contenga sólo el nombre del bucket.
gcloud secrets create yuki-backup-gcs-bucket --project="$PROJECT" \
  --data-file=/ruta/protegida/nombre-del-bucket
gcloud secrets add-iam-policy-binding yuki-backup-gcs-bucket --project="$PROJECT" \
  --member="serviceAccount:${SA}" --role=roles/secretmanager.secretAccessor
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --project="$PROJECT" \
  --member="serviceAccount:${SA}" --role=roles/storage.objectCreator
```

El valor del bucket se introduce en la creación del secreto por un canal
protegido. La VM ya debe tener `devstorage.read_write` o `cloud-platform`; se
comprueba con:

```bash
gcloud compute instances describe yuki-agent --project="$PROJECT" \
  --zone=europe-southwest1-a --format='value(serviceAccounts[0].scopes)'
```

La prueba real es `python3 cli.py backup --ensayar`: debe nombrar el `gs://…`
subido. Si indica que la copia queda en disco, falta configuración.

### C · Ritmos propios (**no es configuración: es del Productor**)

El albedrío está activo, pero los ritmos propios sólo se proponen con
experiencia suficiente: al menos tres intentos en una franja y dos en un tipo
de acto. Sin esos datos devuelve `None`, correctamente. El Productor aprueba
por DM con `!ritmo aprobar <id>`; Yuki no se concede ese permiso a sí misma.

La única comprobación operativa es `python3 cli.py albedrio`. Que muestre cero
ritmos o cero actos no es un fallo en una instancia con poca experiencia.

## 7. Si algo va mal

| Síntoma | Dónde mirar |
|---|---|
| Arranca y muere | `gcloud compute instances get-serial-port-output yuki-agent` — busca `yuki-startup:` |
| `/health` responde y no contesta en Discord | `docker logs yuki-daemon`; y `cli.py pulso`, que distingue proceso de voluntad |
| Un encargo multimedia no llegó | `!status` en el DM, `/api/trabajos` en el Salón, o `data/media_jobs/` |
| Medios que salen como marcador | Falta `VERTEX_PROJECT_ID`. Es un estado declarado, no un fallo silencioso |
| La copia no sale del disco | Falta `BACKUP_GCS_BUCKET`; el resultado de `cli.py backup` lo dice |

Con lo urgente en [`OPERACION.md`](OPERACION.md).
