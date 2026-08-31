# ☁️ Despliegue de Yuki en Google Cloud

Guía completa: qué cuentas crear, qué secretos guardar y cómo desplegar.

> **Antes de empezar — proveedores.** La arquitectura declarada en
> `hermes_config.yaml` y `config.yaml` es: **Nous Portal** como pasarela de
> herramientas (`gateway: nous_portal`) y **OpenRouter** como agregador de LLM
> (`default_aggregator: openrouter`). Los modelos concretos se nombran siempre
> a través del agregador (`openrouter/anthropic/claude-3.5-sonnet`,
> `openrouter/google/gemini-2.0-flash`), de modo que **no hace falta contratar
> cuenta directa con ningún proveedor de modelos**: basta con OpenRouter.
>
> El código sigue esa cadena en `src/core/llm_router.py`: Nous Portal primero,
> OpenRouter después y la voz local de Yuki como último recurso. Como el
> endpoint de Nous Portal aún no existe, se declara no disponible y el tráfico
> real sale por OpenRouter, así que **el único secreto imprescindible para que
> Yuki genere texto es `OPENROUTER_API_KEY`**.
>
> Pendiente: el enrutado por tiers de `provider_routing.routes` (modelos
> distintos según la tarea) todavía no se lee; se usa `agent.model`.
>
> Los módulos de medios (`src/tools/nous_portal.py`) y los adaptadores de
> Telegram y Discord son simulaciones deliberadas: escriben ficheros marcador
> y registran en log. **Espera** a dar de alta las cuentas de pago de FAL,
> Suno o Firecrawl hasta que exista el cliente HTTP que las consuma. Ver
> `README.md` para el estado por módulo.

---

## Arquitectura en GCP

| Pieza | Servicio GCP | Por qué |
|---|---|---|
| Salón web + API | Cloud Run (Service) | Escala a cero; solo paga cuando alguien visita |
| Tareas autónomas (03:00, 07:30, 23:30) | Cloud Run Jobs + Cloud Scheduler | Evita una instancia encendida 24/7 solo para mirar el reloj |
| Memoria SQLite FTS5 | Bucket GCS montado en `/app/data` | El disco de Cloud Run es efímero |
| Claves API | Secret Manager | Nunca en la imagen ni en variables de entorno planas |
| Imágenes Docker | Artifact Registry | Registro privado del proyecto |

**Por qué no el daemon interno en Cloud Run:** `cli.py run-daemon` tiene un bucle
que comprueba el reloj cada 30 s. Eso obliga a `min-instances=1` (una instancia
siempre encendida, ~15-20 €/mes) y contradice el "coste cero en inactividad".
Cloud Scheduler hace el mismo trabajo por céntimos. El daemon sigue siendo la
opción correcta en un VPS (`docker-compose up -d`).

---

## 1. Cuentas y proyecto

```bash
# Requiere la CLI de gcloud: https://cloud.google.com/sdk/docs/install
gcloud auth login

export PROJECT_ID="yuki-diva"          # debe ser único en todo Google Cloud
export REGION="europe-southwest1"      # Madrid
export BILLING_ACCOUNT="XXXXXX-XXXXXX-XXXXXX"   # gcloud billing accounts list

gcloud projects create "$PROJECT_ID" --name="Yuki Digital Diva"
gcloud config set project "$PROJECT_ID"
gcloud billing projects link "$PROJECT_ID" --billing-account="$BILLING_ACCOUNT"
```

La cuenta de facturación es obligatoria incluso dentro del nivel gratuito.
Con el tráfico de un solo productor, este despliegue cae casi entero dentro de
la capa gratuita de Cloud Run.

### APIs a habilitar

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  cloudscheduler.googleapis.com \
  storage.googleapis.com
```

---

## 2. Cuenta de servicio (la "cuenta" de Yuki)

Yuki no debe correr con la cuenta por defecto de Compute, que es
excesivamente permisiva. Se le crea una identidad propia con lo mínimo:

```bash
gcloud iam service-accounts create yuki-runtime \
  --display-name="Yuki — identidad de ejecución"

export SA="yuki-runtime@${PROJECT_ID}.iam.gserviceaccount.com"

# Leer sus propios secretos
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA}" \
  --role="roles/secretmanager.secretAccessor"

# Leer y escribir su memoria en el bucket
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA}" \
  --role="roles/storage.objectAdmin"

# Escribir logs
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA}" \
  --role="roles/logging.logWriter"
```

Una segunda identidad, solo para que Cloud Scheduler pueda invocar los Jobs:

```bash
gcloud iam service-accounts create yuki-scheduler \
  --display-name="Yuki — disparador de tareas"

export SCHED_SA="yuki-scheduler@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SCHED_SA}" \
  --role="roles/run.invoker"
```

---

## 3. Secretos

Nunca subas un `.env` a la imagen — el `.dockerignore` lo impide, pero el
sitio correcto es Secret Manager:

```bash
create_secret() {
  printf '%s' "$2" | gcloud secrets create "$1" --data-file=- --replication-policy=automatic \
    || printf '%s' "$2" | gcloud secrets versions add "$1" --data-file=-
}

# Pasarela de herramientas y agregador de LLM: el núcleo de la arquitectura
create_secret yuki-nous-portal-api-key "..."
create_secret yuki-openrouter-api-key  "sk-or-..."

# Modelado dialéctico y adaptadores sociales
create_secret yuki-honcho-api-key      "..."
create_secret yuki-telegram-bot-token  "..."
create_secret yuki-discord-bot-token   "..."

# Opcional: acceso directo a un proveedor, saltándose el agregador.
# La arquitectura no lo requiere; OpenRouter ya da acceso a estos modelos.
# create_secret yuki-anthropic-api-key "sk-ant-..."
# create_secret yuki-gemini-api-key    "..."
```

Crea solo los secretos que vayas a usar y recorta en consecuencia la
sustitución `_SECRETS` de `cloudbuild.yaml`: `gcloud` falla al desplegar si
referencias un secreto que no existe.

Para rotar una clave más adelante basta con `gcloud secrets versions add`; el
servicio la recoge en el siguiente arranque porque está anclado a `:latest`.

---

## 4. Registro de imágenes y bucket de memoria

```bash
gcloud artifacts repositories create yuki \
  --repository-format=docker \
  --location="$REGION" \
  --description="Imágenes de Yuki"

export BUCKET="${PROJECT_ID}-yuki-data"
gcloud storage buckets create "gs://${BUCKET}" \
  --location="$REGION" \
  --uniform-bucket-level-access
```

> **Límite conocido.** SQLite sobre GCS FUSE tolera **un solo escritor**. Por eso
> el servicio se despliega con `--max-instances=1` y las tareas programadas no se
> solapan. Es suficiente para una diva y su productor. Si algún día Yuki necesita
> concurrencia real, el paso siguiente es migrar la memoria a Cloud SQL
> (PostgreSQL con `tsvector` en lugar de FTS5), que es un cambio de calado en
> `src/memory/fts5_memory.py`.

Siembra inicial de la memoria (una sola vez, desde tu máquina):

```bash
python scripts/seed_memory.py
gcloud storage cp data/yuki_memory.db "gs://${BUCKET}/yuki_memory.db"
```

---

## 5. Despliegue

```bash
gcloud builds submit --config cloudbuild.yaml \
  --substitutions=_REGION="$REGION",_BUCKET="$BUCKET"
```

El pipeline ejecuta los tests, construye la imagen, la publica, despliega el
Salón y crea/actualiza los Cloud Run Jobs. Si los tests fallan, no se despliega.

Comprobación:

```bash
export URL=$(gcloud run services describe yuki-salon --region="$REGION" --format='value(status.url)')
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" "${URL}/health"
# {"status": "ok", "service": "yuki-salon", "agent_loaded": false}
```

El servicio se despliega con `--no-allow-unauthenticated`: el Salón no queda
abierto a internet. Para abrirlo al público conscientemente:

```bash
gcloud run services add-iam-policy-binding yuki-salon \
  --region="$REGION" --member="allUsers" --role="roles/run.invoker"
```

---

## 6. Ritmo circadiano (Cloud Scheduler)

Los horarios de `config.yaml` se replican aquí. Cloud Scheduler acepta la zona
horaria directamente, así que los horarios de Yuki se respetan sin conversión:

```bash
schedule_job() {
  local NAME=$1 CRON=$2 JOB=$3
  gcloud scheduler jobs create http "$NAME" \
    --location="$REGION" \
    --schedule="$CRON" \
    --time-zone="Europe/Madrid" \
    --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB}:run" \
    --http-method=POST \
    --oauth-service-account-email="$SCHED_SA"
}

schedule_job yuki-reflexion-nocturna "0 3 * * *"    yuki-nocturnal-trend-reflection
schedule_job yuki-arte-matutino      "30 7 * * *"   yuki-morning-inspiration-drop
schedule_job yuki-sintesis-diaria    "30 23 * * *"  yuki-daily-memory-synthesis
schedule_job yuki-ritual-eco         "30 6 * * *"   yuki-echo-ritual
```

Disparo manual para probar:

```bash
gcloud run jobs execute yuki-morning-inspiration-drop --region="$REGION"
gcloud run jobs executions list --region="$REGION"
```

---

## 7. Observación y coste

```bash
# Logs del Salón
gcloud run services logs read yuki-salon --region="$REGION" --limit=50

# Última ejecución de una tarea
gcloud run jobs executions list --job=yuki-morning-inspiration-drop --region="$REGION"
```

Pon un tope de gasto antes de dejarlo solo:
**Facturación → Presupuestos y alertas → Crear presupuesto** (p. ej. 10 €/mes
con aviso al 50 %, 90 % y 100 %). El gasto real de este despliegue debería ser
de céntimos; lo que puede dispararse son las llamadas al LLM, que se facturan
aparte en OpenRouter (y en Nous Portal cuando se implemente la generación de
medios).

---

## Anexo: alternativa en Compute Engine

Si prefieres el modelo del VPS original —un proceso siempre vivo, disco de
verdad, sin la limitación de SQLite sobre GCS— una `e2-micro` con disco
persistente es más fiel al diseño y entra en el nivel gratuito de GCP:

```bash
gcloud compute instances create yuki-vps \
  --machine-type=e2-micro \
  --zone="${REGION}-a" \
  --boot-disk-size=20GB \
  --image-family=debian-12 \
  --image-project=debian-cloud
```

Dentro de la máquina se usa el `docker-compose.yml` del repositorio, que ya
levanta el Salón y el daemon autónomo como dos servicios.
