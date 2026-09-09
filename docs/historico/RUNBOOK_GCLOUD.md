# 🛰️ Runbook: aterrizar Yuki en un proyecto real de Google Cloud

> **Histórico.** Este encargo se ejecutó y su respuesta está en
> [`INFORME_CREDITO_GCLOUD.md`](INFORME_CREDITO_GCLOUD.md). El procedimiento
> vigente para desplegar es [`../GCP_DEPLOYMENT.md`](../GCP_DEPLOYMENT.md):
> seguir los pasos de aquí al pie de la letra ya no lleva a ninguna parte.

*Encargo para un agente con acceso a `gcloud`. Autocontenido: no presupone conocimiento de este repositorio ni del arnés Hermes.*

---

## 0. Qué es esto y por qué existe

El código que conecta Yuki con Vertex AI **ya está escrito, probado y fusionado en `main`**. Lo que falta es lo único que no se puede hacer sin credenciales: **contrastarlo contra un proyecto de Google Cloud de verdad**.

Tu tarea **no es implementar**. Es **verificar supuestos y corregir configuración**. Si terminas escribiendo un módulo nuevo, casi seguro te has salido del encargo: para y consulta.

El trabajo previo se hizo en un contenedor sin `gcloud` (SDK bloqueado por el proxy de salida, sin servidor de metadatos, sin posibilidad de completar un OAuth de navegador). Por eso hay una lista concreta de cosas que se dieron por buenas sobre documentación y ejemplos oficiales, pero que **nadie ha visto responder**. Esa lista es la sección 4, y es el corazón de este documento.

### Contexto mínimo del proyecto

**Yuki** es una artista digital autónoma. Su ejecución tiene dos mitades:

- **El cerebro** (texto): `src/core/llm_router.py`. Una cadena de pasarelas que se recorren en orden y caen a la siguiente cuando una no está disponible: `nous_portal → vertex_ai → openrouter → voz_local`.
- **Los medios** (imagen, vídeo, voz): `src/tools/vertex_media.py`, con `src/tools/nous_portal.py` como puerta de entrada.

Ambas mitades comparten un solo interruptor: **la variable `VERTEX_PROJECT_ID`**. Sin ella, todo el repositorio se comporta como si Vertex no existiera. Con ella, el consumo se carga al crédito de Google Cloud.

### Lee sólo esto

No recorras el repositorio entero. Cinco ficheros bastan, y en este orden:

| Fichero | Para qué |
|---|---|
| `config.yaml`, sección `vertex_ai` | Todo lo que vas a tocar está aquí |
| `src/core/llm_router.py`, clase `VertexProvider` | Cómo se autentica y llama al texto |
| `src/tools/vertex_media.py` | Los tres motores de medios |
| `docs/GCP_DEPLOYMENT.md`, sección *Servir los modelos desde el crédito* | El porqué de la ruta elegida |
| `AGENTS.md` | Las reglas que no puedes romper (ver §7) |
| `docs/INFORME_CREDITO_GCLOUD.md` | Qué se ha verificado ya, y los tres defectos que impedían que el crédito se consumiera |

---

## 1. El matiz que decide si el crédito se gasta

Hay dos formas de llamar a Gemini y **sólo una consume el crédito de prueba**:

| Ruta | Autenticación | ¿Consume el crédito? |
|---|---|---|
| Gemini API de AI Studio | `GEMINI_API_KEY` | **No.** Excluido desde marzo de 2026 |
| Vertex AI | Credenciales del proyecto (ADC) | **Sí** |

Por eso el código **no** se autentica con una clave. Si en algún momento te tienta rellenar `GEMINI_API_KEY` para "que funcione antes", estarás facturando fuera del crédito. No lo hagas.

### 1.bis Cómo se lee el panel de facturación

Dos columnas de la tabla de costes: **Product** dice por qué API salió el gasto, y **Other savings** dice si el crédito lo cubrió.

| Lo que ves en *Product* | Qué API es | ¿Toca el crédito? |
|---|---|---|
| **Vertex AI** (aparece como *Agent Platform API* en la lista de APIs) | `aiplatform.googleapis.com` | **Sí** |
| **Gemini API** | `generativelanguage.googleapis.com` (AI Studio) | **No** |

Verificado contra el panel del productor el 7 de septiembre de 2026: Vertex AI llevaba €0,18 de uso y −€0,18 en *Other savings* (subtotal €0), mientras que Gemini API llevaba €2,01 y €0,00 de descuento. **El crédito funciona; lo que no cubre es AI Studio.**

Una línea con el producto **Gemini API** significa que el gasto salió por AI Studio, y **Yuki no llama nunca a esa API**: viene de otro proceso, de otra herramienta o de una clave suelta.

Si aparece gasto bajo *Gemini API*:

1. `python3 cli.py vertex-check` — avisa si hay `GEMINI_API_KEY`/`GOOGLE_API_KEY` en el entorno.
2. Quita esa variable del `.env`, del despliegue de Cloud Run y de los Jobs.
3. En `Billing → Cost table`, **agrupa por proyecto**. Las claves de AI Studio viven en un proyecto propio, con el nombre autogenerado `gen-lang-client-*`, y sus cuentas de servicio llevan el prefijo `ais-gemini-key-*`. Ese gasto no es de Yuki.
4. `hermes_config.yaml` declara `google: "${GEMINI_API_KEY}"`, pero **ese fichero no lo carga ningún código de este repositorio**: es la plantilla de `~/.hermes/config.yaml`, del harness. Descartado como origen.

### 1.quater Cuidado con los cuatro nombres parecidos

En la lista de APIs habilitadas **no busques «Vertex AI»**: hoy aparece como **«Agent Platform API»**, por el rebautizado a *Gemini Enterprise Agent Platform*.

| Nombre en el panel | Servicio | Papel |
|---|---|---|
| **Agent Platform API** | `aiplatform.googleapis.com` | **Vertex AI. La que consume el crédito.** No la desactives |
| Gemini API | `generativelanguage.googleapis.com` | AI Studio. La que factura fuera del crédito |
| Gemini for Google Cloud API | Asistencia de Gemini en la consola | Nada que ver con Yuki |
| Gemini Cloud Assist API | Ídem | Nada que ver con Yuki |

Antes de desactivar ninguna, confirma el nombre del servicio pinchando en ella: los rótulos cambian, los `*.googleapis.com` no.

### 1.ter El endpoint: dónde se rompía la alineación

El host de Vertex depende de la región, y **`global` es el caso especial: no lleva prefijo.**

```
global              -> https://aiplatform.googleapis.com/...
europe-southwest1   -> https://europe-southwest1-aiplatform.googleapis.com/...
```

Hasta esta corrección, `VertexProvider` componía siempre `{location}-aiplatform.googleapis.com`, de modo que con la región `global` —la que traen `config.yaml`, `.env.example` y `cloudbuild.yaml`, y la que este runbook recomienda probar primero— llamaba a `global-aiplatform.googleapis.com`. Ese nombre **resuelve** (comodín `*.googleapis.com`) pero devuelve un **404** de Google. `generate` se tragaba el fallo, devolvía `None` y la cadena caía a OpenRouter sin decir nada: Yuki respondía con normalidad y el crédito de Google Cloud no se tocaba jamás.

Ya está corregido, con test de regresión (`test_vertex_global_endpoint_has_no_region_prefix`), y `vertex-check` imprime ahora el endpoint resuelto. Si Vertex está configurada y aun así falla, el log lo dice en voz alta en vez de degradarse en silencio.

---

## 2. Cuenta y proyecto

El productor tiene **dos cuentas de Google**. La que debe quedar activa es **`magnus.dr4co@gmail.com`**. Confírmalo antes de gastar un céntimo: un error aquí carga el gasto al proyecto de la otra cuenta.

La cuenta de facturación es **`01E208-BEDDAC-B94E7E`** y tiene tres proyectos. El de Yuki es **`yuki-prod`** («Yuki Digital Diva»); ése es el valor de `VERTEX_PROJECT_ID`. Los otros dos (`gen-lang-client-0734039446`, generado por AI Studio, y `project-3b69d116-9099-4e2f-a68`) **no** son el sitio donde debe correr Yuki.

```bash
gcloud auth login magnus.dr4co@gmail.com
gcloud config set account magnus.dr4co@gmail.com
gcloud auth list          # la cuenta correcta debe llevar el asterisco
```

**El paso que más se olvida.** `gcloud auth login` autentica el **CLI**. Las librerías de Python que usa Yuki no lo usan: usan **ADC**, que se autentica aparte.

```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project "$PROJECT_ID"
```

Sin `set-quota-project` verás errores de cuota que parecen de permisos y te harán perder una hora.

```bash
export PROJECT_ID="<el project id real>"
gcloud config set project "$PROJECT_ID"
gcloud billing projects describe "$PROJECT_ID"   # confirma la cuenta de facturación
```

Si el proyecto aún no existe, `docs/GCP_DEPLOYMENT.md` §1 tiene los comandos de creación.

---

## 3. APIs y permisos

```bash
gcloud services enable \
  aiplatform.googleapis.com \
  texttospeech.googleapis.com
```

`aiplatform` sirve texto, imagen y vídeo. `texttospeech` sirve la voz: es una API distinta y se olvida con facilidad.

Si además vas a desplegar en Cloud Run, el resto de APIs y la identidad `yuki-runtime` (que necesita `roles/aiplatform.user`) están en `docs/GCP_DEPLOYMENT.md` §1 y §2. **Para verificar los modelos no hace falta desplegar nada.**

---

## 4. Los supuestos que debes verificar

Esta es la razón de ser del encargo. Cada fila se fijó sobre documentación o ejemplos oficiales, pero **ninguna se ha visto responder en un proyecto real**.

| # | Supuesto | Clave en `config.yaml` | Confianza | Si falla |
|---|---|---|---|---|
| 1 | `google/gemini-3.7-flash` existe y responde | `vertex_ai.primary_model` | Media | Prueba `gemini-3.8-flash`, `gemini-3.6-flash`, `gemini-3-flash` |
| 2 | `google/gemini-3.6-flash` sirve de respaldo | `vertex_ai.fallback_model` | Media | Cualquier Flash estable que sí responda |
| 3 | `imagen-4.0-generate-001` existe | `vertex_ai.media.image_model` | Media | Prueba `imagen-3.0-generate-002` |
| 4 | `gemini-omni-flash-preview` existe y acepta `interactions` | `vertex_ai.media.video_model` | **Baja — está en *preview*** | Ver §4.bis |
| 5 | `gemini-2.5-flash-tts` existe con voz `Aoede` y `es-es` | `vertex_ai.media.tts_model` | Media-alta | Prueba `gemini-3.1-flash-tts-preview` |
| 6 | La región `global` sirve los cinco modelos | `vertex_ai.location` | **Baja** | Ver §4.ter. El *endpoint* `global` ya está verificado (§1.ter); qué modelos sirve, no |
| 7 | El SDK acepta `genai.Client(enterprise=True, ...)` | — (código) | ✅ **Verificado** | `enterprise` es un parámetro real en `google-genai` 2.22, alias de `vertexai`. El fallback cubre las 1.x |

> Los supuestos 1 a 5 siguen sin verificar: hacen falta credenciales de un proyecto real. Lo que sí se ha comprobado sin gastar un céntimo está en **`docs/INFORME_CREDITO_GCLOUD.md`**.

### Cómo verificar de verdad

**No te fíes de `gcloud ai models list`.** Ese comando lista los modelos *de tu registro*, no siempre el catálogo de modelos fundacionales del publisher. (El comentario que hay ahora en `config.yaml` lo sugiere como pista; si compruebas que induce a error, **corrígelo** como parte de este encargo.)

**La verificación autoritativa es una llamada real.** El repositorio trae la herramienta hecha:

```bash
export VERTEX_PROJECT_ID="$PROJECT_ID"
export VERTEX_LOCATION="global"

pip install -r requirements.txt
python3 cli.py vertex-check
```

`vertex-check` comprueba, en este orden: configuración → credenciales → una petición real → tokens consumidos → coste → proyección del cron sobre 90 días. Cuando algo falla, **te dice el motivo exacto** en vez de fallar en silencio. Ese mensaje es tu diagnóstico; léelo antes de tocar nada.

### 4.bis Si Omni (vídeo) no existe o cambió de forma

Es el supuesto más frágil: `gemini-omni-flash-preview` está en *preview* pública y su superficie es la **Interactions API**, distinta de la de los demás modelos.

**No improvises un endpoint.** Si la llamada falla:

1. Consulta la documentación oficial de Gemini Omni Flash en Google Cloud, y el cuaderno `vision/getting-started/gemini_omni_flash_video_gen.ipynb` del repositorio `GoogleCloudPlatform/generative-ai`. De ahí salió la implementación actual.
2. Si la firma cambió, ajusta **sólo** `VertexMediaClient.generate_video` en `src/tools/vertex_media.py`, y actualiza sus tests en `tests/test_nous_tools.py`.
3. Si el modelo ya no existe, **no lo sustituyas por Veo en silencio**. Deja `enabled` como está, anota el hallazgo y consúltalo. El vídeo no es crítico para que Yuki funcione.

### 4.ter Sobre la región

`global` reparte entre las regiones disponibles y es lo más probable que funcione para texto. **Imagen, Omni y TTS suelen tener disponibilidad regional restringida.**

Orden de prueba sugerido: `global` → `us-central1` (la más amplia) → `europe-southwest1` (Madrid, coincide con la zona horaria de Yuki).

**Anota qué región acaba sirviendo cada motor.** Si el texto va por Madrid y la imagen tiene que ir por EE. UU., eso tiene implicaciones de residencia de datos que el productor debe conocer. Dilo en el informe; no lo decidas tú.

---

## 5. Corregir la configuración

Cuando sepas qué responde de verdad, edita **`config.yaml`, sección `vertex_ai`**. Es el único sitio.

```yaml
vertex_ai:
  enabled: true
  project_id: ""              # déjalo vacío: el proyecto va por VERTEX_PROJECT_ID
  location: "global"          # ← corrige con la región verificada
  primary_model: "google/gemini-3.7-flash"      # ← corrige
  fallback_model: "google/gemini-3.6-flash"     # ← corrige
  media:
    image_model: "imagen-4.0-generate-001"      # ← corrige
    video_model: "gemini-omni-flash-preview"    # ← corrige
    tts_model: "gemini-2.5-flash-tts"           # ← corrige
    voice: "Aoede"
    language_code: "es-es"
```

**Deja `project_id` vacío en el fichero.** El proyecto se declara por entorno (`VERTEX_PROJECT_ID`), que es como llega en despliegue. Un identificador escrito en el repositorio es una fuga de configuración esperando a pasar.

Junto a cada corrección, **actualiza el comentario** si decía algo que resultó falso. Un comentario obsoleto es peor que ninguno.

---

## 6. Pruebas de humo, por orden de coste

Ejecuta en este orden. **No pases al siguiente hasta que el anterior pase.**

```bash
# 1. Texto — céntimos. Es la prueba que valida credenciales y región.
python3 cli.py vertex-check

# 2. Conversación real, para ver la voz de Yuki y no sólo un 200 OK.
python3 cli.py chat

# 3. Imagen — ≈0,04 USD.
python3 cli.py skill generar-portada --concept "niebla sobre asfalto, pan de oro"

# 4. Voz — por caracteres. Debe salir OGG Opus SIN pasar por ffmpeg.
python3 cli.py skill sintesis-vocal --text "El agua siempre encuentra su camino."

# 5. La suite completa, que no debe romperse por tus cambios.
python3 -m pytest tests/ -q      # 186 deben pasar
```

**Cómo leer el resultado.** Cada medio se informa de una de tres formas, y la distinción es deliberada:

- `✅ ... — generado con <modelo>` → real.
- `⚠️ ...: es un marcador de texto, no un medio real` → **Vertex no está activo.** Revisa `VERTEX_PROJECT_ID` y las credenciales; no lo des por bueno.
- `❌ ...: no se pudo generar` → fallo real, con el motivo. Ese motivo es tu diagnóstico.

Comprueba además que los ficheros de `output/art/` y `output/voice/` son **binarios de verdad** (`file output/art/*.png` debe decir `PNG image data`, no `ASCII text`).

### El vídeo va aparte

**No ejecutes `/animar-portada` sin autorización explícita del productor, y nunca en bucle.**

Se factura **≈0,10 USD por segundo de vídeo producido**. Diez segundos ≈ 1 USD, más que miles de respuestas de texto. Cuando se autorice:

```bash
python3 cli.py skill animar-portada --duration 3 --image-path output/art/<la portada generada>.png
```

Empieza por **3 segundos**, el mínimo. Si funciona, ya se decidirá si vale la pena alargarlo.

---

## 7. Lo que no debes hacer

Estas reglas vienen de `AGENTS.md` §5 y del catálogo `skills/HERRAMIENTAS.md` §7. No son estilo: son el contrato del proyecto.

1. **Nunca devuelvas un resultado simulado como si fuera real.** Si una llamada falla y no hay respaldo, aborta y explícalo. Una imagen que no existe o una URL inventada contaminan la memoria de Yuki y engañan al productor. El código ya lo hace bien; no lo "arregles" haciendo que un fallo devuelva algo.
2. **No inventes endpoints ni modelos.** Si algo no aparece en la documentación oficial, no existe. Ante la duda, para y pregunta.
3. **No metas vídeo en el cron.** `config.yaml` declara 84 disparos diarios (`agency_loop_tick` cada 20 minutos). Vídeo automático funde el crédito en una tarde.
4. **No cambies el orden de la cadena de pasarelas.** Que Vertex vaya delante de OpenRouter es lo que carga el gasto al crédito; que OpenRouter siga detrás es lo que impide que Yuki enmudezca cuando el crédito se agote.
5. **No subas credenciales.** Ni `~/.config/gcloud/application_default_credentials.json`, ni claves de cuenta de servicio, ni el `project_id` en `config.yaml`. Revisa `git status` antes de cada commit.
6. **No rellenes `GEMINI_API_KEY`** creyendo que gasta el crédito. Ver §1.

---

## 8. Poner un tope antes de irte

El crédito son **300 USD y 90 días**. Lo que se lleva por delante a la gente no es el gasto durante las pruebas: es que **el cron sigue corriendo cuando el crédito caduca**. Si para entonces la cuenta está activada como de pago, factura desde el día 91 sin que nadie lo mire.

```bash
# Facturación → Presupuestos y alertas
# Presupuesto mensual (p. ej. 25 EUR) con avisos al 50 %, 90 % y 100 %.
```

Déjalo puesto aunque las pruebas salgan bien. Es el paso que separa un experimento de un cargo inesperado.

**Para desactivar Vertex** cuando el crédito se agote: quita `VERTEX_PROJECT_ID` o pon `vertex_ai.enabled: false`. La cadena vuelve sola a OpenRouter sin tocar código.

---

## 9. Entrega

**Rama:** trabaja sobre una rama propia (`claude/verificacion-gcloud` o similar). **No empujes a `main` sin autorización explícita del productor.**

**Commit:** sólo `config.yaml` con los modelos y la región verificados, y los comentarios que hayas corregido. Si tocaste `src/tools/vertex_media.py` por §4.bis, incluye sus tests actualizados.

**Informe.** Rellena esta tabla con lo que *observaste*, no con lo que esperabas:

| Supuesto | ¿Se confirmó? | Valor real | Notas |
|---|---|---|---|
| 1. Modelo de texto principal | | | |
| 2. Modelo de texto de respaldo | | | |
| 3. Modelo de imagen | | | |
| 4. Modelo de vídeo (Omni) | | | |
| 5. Modelo de voz (TTS) | | | |
| 6. Región | | | ¿La misma para los cinco? |
| 7. `enterprise=True` en el SDK | | | |

Y añade:

- **Coste real** de las pruebas, del panel de facturación (no del estimado de `vertex-check`).
- **Proyección a 90 días** que dio `vertex-check`, y qué porcentaje del crédito supone.
- **Presupuesto y alertas**: confirmación de que quedaron puestos.
- **Cualquier cosa que no encaje con este documento.** Si algo aquí resultó equivocado, dilo con claridad: este runbook se escribió sin poder verificarlo, y corregirlo es parte del encargo.
