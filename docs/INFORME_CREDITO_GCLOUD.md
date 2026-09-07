# Informe: por qué el crédito de Google Cloud no se estaba consumiendo

**Fecha:** 2026-09-06
**Rama:** `claude/yuki-gcloud-credits-alignment-0oso2d`
**Encargo:** `docs/RUNBOOK_GCLOUD.md` §9 pide este informe con lo *observado*, no con lo esperado. Eso es lo que hay aquí.

**Síntoma que lo dispara.** En el panel de facturación aparece una línea así:

| Product | Usage cost | Negotiated savings | Savings programs | Other savings | Subtotal |
|---|---|---|---|---|---|
| Gemini API | €2,01 | €0,00 | — | €0,00 | €2,01 |

---

## 0. Resumen

Se encontraron **tres defectos**, dos de ellos silenciosos. Ninguno se manifiesta como un error visible: Yuki responde con normalidad mientras el crédito no se toca.

| # | Defecto | Efecto | Estado |
|---|---|---|---|
| 1 | El host de Vertex se componía mal para la región `global` | Toda petición de texto daba 404 y la cadena caía a OpenRouter **en silencio** | Corregido |
| 2 | La degradación de Vertex no dejaba rastro | Imposible notar que el crédito no se estaba usando | Corregido |
| 3 | `tests/test_agent.py` dependía de la hora del reloj | Bloqueaba el despliegue a Cloud Run entre las 00:00 y las 02:00 | Corregido |
| 4 | El anexo de Compute Engine creaba la VM **sin `--scopes`** | El token de la máquina no sirve para Vertex: 403 por ámbitos, otra vez **en silencio** | Corregido |

Y una conclusión que **no** es un defecto del código: los €2,01 de la línea *Gemini API* **no los ha generado Yuki**, sino claves de AI Studio en otro proyecto. Confirmado contra el panel en §2, donde además se ve que **el crédito sí se aplica a Vertex AI** (−€0,18) y **no a Gemini API** (€0,00).

---

## 1. Defecto 1 — el endpoint de la región `global`

El host de Vertex depende de la región, y **`global` es el caso especial: no lleva prefijo.**

```
global              ->  https://aiplatform.googleapis.com/...
europe-southwest1   ->  https://europe-southwest1-aiplatform.googleapis.com/...
```

`VertexProvider.base_url` componía siempre `{location}-aiplatform.googleapis.com`. Con la región `global` eso da `global-aiplatform.googleapis.com`.

**Comprobado contra Google, sin credenciales:**

| Host | Respuesta | Lectura |
|---|---|---|
| `global-aiplatform.googleapis.com` | **404** (página de error de Google) | El nombre resuelve por el comodín `*.googleapis.com`, pero ahí no hay API |
| `aiplatform.googleapis.com` | **401** | La ruta existe y exige autenticación: es la buena |
| `europe-southwest1-aiplatform.googleapis.com` | **401** | La buena para una región concreta |

`global` es el valor que traen **`config.yaml`**, **`.env.example`** y **`cloudbuild.yaml`**, y el que el propio runbook (§4.ter) recomienda probar primero. Es decir: **la configuración por defecto y el camino recomendado eran justo los que no funcionaban.**

Como `generate()` captura la excepción y devuelve `None`, el router pasaba a la siguiente pasarela. Yuki contestaba igual de bien —por OpenRouter— y nada indicaba que Vertex no había servido nada.

Los tests sólo cubrían `europe-southwest1`, así que el caso por defecto **nunca se probó**.

**Por qué la ruta de medios no estaba afectada:** `src/tools/vertex_media.py` no compone la URL a mano, usa el SDK `google-genai`. Se verificó con la versión 2.22 que el SDK resuelve `location="global"` a `https://aiplatform.googleapis.com/` correctamente.

**Corrección:** función `vertex_host()` en `src/core/llm_router.py`, con tests de regresión (`test_vertex_global_endpoint_has_no_region_prefix`, `test_vertex_host_por_region`, `test_vertex_default_provider_uses_global_endpoint`).

---

## 2. Los €2,01 del producto «Gemini API» — confirmado en el panel

**El crédito funciona. Simplemente no cubre ese producto.** La tabla de costes del productor (7 sep 2026) lo demuestra sin margen de duda:

| Product | Usage cost | Negotiated savings | Savings programs | **Other savings** | Subtotal |
|---|---|---|---|---|---|
| **Gemini API** | €2,01 | €0,00 | — | **€0,00** | **€2,01** |
| **Vertex AI** | €0,18 | €0,00 | — | **−€0,18** | **€0,00** |
| Networking | €1,03 | €0,00 | — | −€1,03 | €0,00 |
| Cloud Text-to-Speech | €0,00 | €0,00 | — | €0,00 | €0,00 |

**«Other savings» es la columna donde aterriza el crédito de prueba.** A Vertex AI se le descuenta íntegro y queda a cero. A Gemini API no se le descuenta nada y se paga entero. Es exactamente la distinción que este repositorio asumía y que hasta ahora no se había podido comprobar contra un panel real.

### De dónde salen esos €2,01

**No de Yuki.** Verificado en el código:

- No existe ninguna ruta hacia `generativelanguage.googleapis.com`. Las únicas llamadas a Google salen a `aiplatform.googleapis.com` y `texttospeech.googleapis.com`.
- `GEMINI_API_KEY` no se lee en ningún sitio salvo para **avisar** de que está puesta.
- `hermes_config.yaml:18` declara `google: "${GEMINI_API_KEY}"`, pero **ese fichero no lo carga ningún código**: es una plantilla para `~/.hermes/config.yaml`, del harness, no de este repositorio. La línea es inerte.

**De AI Studio.** Las huellas están en la propia cuenta de facturación:

| Indicio | Qué significa |
|---|---|
| Proyecto `gen-lang-client-0734039446` («Dr4co») | `gen-lang-client-*` es el nombre que **AI Studio genera automáticamente** al crear una clave |
| Cuentas de servicio `ais-gemini-key-*@47269626422.iam.gserviceaccount.com` | El prefijo `ais` es **AI Studio**. Hay tres |
| Clave «Gemini API Key», restricción *Gemini API*, creada el 18 ago 2026 | Es la que factura |
| 115 peticiones a *Gemini API* | Tráfico real por esa vía |

Es decir: el gasto sale de claves de AI Studio creadas a mano, en un proyecto distinto del de Yuki, y no del despliegue.

### El proyecto correcto para Yuki

La cuenta de facturación `01E208-BEDDAC-B94E7E` tiene tres proyectos:

| Proyecto | ID | Papel |
|---|---|---|
| Yuki Digital Diva | **`yuki-prod`** | **El de Yuki.** Es el que va en `VERTEX_PROJECT_ID` |
| Dr4co | `gen-lang-client-0734039446` | Generado por AI Studio. De aquí salen los €2,01 |
| My First Project | `project-3b69d116-9099-4e2f-a68` | Por defecto, sin uso conocido |

### El nombre de la API despista

En la lista de APIs habilitadas **no aparece «Vertex AI»**: aparece como **«Agent Platform API»**, por el rebautizado a *Gemini Enterprise Agent Platform* que este repositorio ya documenta (y que en el SDK `google-genai` se refleja en el parámetro `enterprise=`, alias de `vertexai=`). Ya estaba habilitada, y de ahí los €0,18 de Vertex AI ya facturados y descontados.

Las cuatro APIs de nombre parecido no son lo mismo:

| Nombre en el panel | Servicio | Papel |
|---|---|---|
| **Agent Platform API** | `aiplatform.googleapis.com` | **Vertex AI. La que consume el crédito.** No la toques |
| Gemini API | `generativelanguage.googleapis.com` | AI Studio. La que factura fuera del crédito |
| Gemini for Google Cloud API | Asistencia de Gemini en la consola | Nada que ver con Yuki |
| Gemini Cloud Assist API | Ídem | Nada que ver con Yuki |

### El crédito caduca

`Free Trial`: **€252,29 restantes de €263,35 (96%), caduca el 23 de septiembre de 2026.** Quedan pocos días. El *Google Developer Program premium benefit* (€8,78) ya está agotado.

## 3. Defecto 2 — la degradación era muda

Vertex configurada + fallo = el crédito no se consume, y no quedaba constancia en ninguna parte. Es el fallo que más caro sale de los silenciosos.

Ahora `VertexProvider` avisa **una vez por proceso** (Yuki corre 24/7; repetirlo ahogaría el log) nombrando la consecuencia, no sólo la causa:

```
Vertex está configurada (proyecto 'X', región 'Y') pero no atendió la petición: <motivo>.
La cadena sale por la siguiente pasarela, así que EL CRÉDITO DE GOOGLE CLOUD NO SE ESTÁ
CONSUMIENDO. Diagnostícalo con: python cli.py vertex-check
```

Y avisa también si hay `GEMINI_API_KEY` o `GOOGLE_API_KEY` en el entorno, porque su gasto factura bajo otro producto.

`cli.py vertex-check` imprime ahora el **endpoint resuelto** y ambos avisos.

---

## 4. Defecto 3 — el test que bloqueaba el despliegue

`tests/test_agent.py::test_agent_fast_response_and_taboo` fallaba **según la hora del reloj**.

`PresenceController.should_respond()` calla a Yuki durante la fase `deep_rest` (00:00–02:00 en Europe/Madrid), y esa comprobación va **antes** de la detección de tabú en `generate_response`. El test pasaba de día y fallaba de madrugada.

Como `cloudbuild.yaml` corre `pytest tests/` **como primer paso del pipeline**, ese fallo **bloqueaba todo despliegue a Cloud Run** en esa franja horaria, y no en otras. Un fallo así es peor que uno constante: parece infraestructura.

Al arreglarlo apareció un segundo defecto, real y latente:

> `PresenceController.should_respond(channel_type, is_producer=False)` reserva una excepción explícita para que **el productor** pueda alcanzar a Yuki por privado durante el descanso profundo. Ningún llamante pasaba nunca `is_producer`. La excepción era **código muerto**: el productor se quedaba sin respuesta entre medianoche y las dos, igual que un desconocido.

**Correcciones:**

- `YukiAgent` sabe ahora quién es el productor (`producer_user_id`, leído de `honcho.user_id` en `config.yaml`) y lo pasa a la comprobación de presencia.
- El test fija la fase circadiana en vez de depender del reloj, y se añaden tres casos que antes no existían: el productor sí llega en `deep_rest`, un visitante no, y la identificación del productor sale de la configuración.

No se ha tocado la política de presencia en sí —que Yuki descanse de madrugada es una decisión de producto—, sólo el cableado que impedía aplicarla como estaba escrita.

---

## 4.bis Defecto 4 — la VM no puede llamar a Vertex aunque todo lo demás esté bien

Yuki no corre en Cloud Run: corre en una VM de Compute Engine (`yuki-agent`, proyecto `yuki-prod`) con el contenedor dentro. Eso explica los €2,91 de Compute Engine de la tabla de costes, y cambia por completo cómo se autentica.

**Dentro de una VM, los ámbitos de la máquina mandan sobre los que pide el código.** Las credenciales por defecto salen del servidor de metadatos, y el token lleva los ámbitos fijados al crear la instancia. Que `llm_router.py` pida `cloud-platform` no sirve de nada si la máquina no lo tiene.

El anexo de `docs/GCP_DEPLOYMENT.md` creaba la VM **sin `--scopes`**, así que recibía los de por defecto:

```
devstorage.read_only   logging.write                monitoring.write
servicecontrol         service.management.readonly  trace.append
```

**`cloud-platform` no está.** Con eso, Vertex responde 403 por ámbitos insuficientes **aunque la cuenta de servicio tenga `roles/aiplatform.user`** —son dos cosas distintas y hacen falta las dos—, `VertexProvider` degrada a OpenRouter y el crédito no se toca. El síntoma es idéntico al de no haber configurado nada: Yuki responde con normalidad.

Es el tercer camino distinto que llevaba al mismo sitio, y el único que no se ve leyendo el código.

**Corrección:**

- El anexo crea la VM con `--scopes=cloud-platform` y explica cómo arreglar una ya creada (hay que **parar** la máquina: los ámbitos no se cambian en caliente).
- `gce_service_account_scopes()` en `src/core/llm_router.py` lee los ámbitos del servidor de metadatos.
- `cli.py vertex-check` detecta solo que está dentro de una VM, los lista y dice si bastan.
- El aviso de degradación añade la pista cuando la causa es ésta.

---

## 5. Tabla de supuestos del runbook §4

Lo que se ha podido verificar **sin un proyecto de Google Cloud** y lo que sigue pendiente.

| # | Supuesto | ¿Se confirmó? | Notas |
|---|---|---|---|
| 1 | `google/gemini-3.7-flash` existe y responde | **Pendiente** | Requiere proyecto. `vertex-check` lo dirá |
| 2 | `google/gemini-3.6-flash` sirve de respaldo | **Pendiente** | Ídem |
| 3 | `imagen-4.0-generate-001` existe | **Pendiente** | Ídem |
| 4 | `gemini-omni-flash-preview` existe | **Pendiente** | Ídem. Sigue siendo el supuesto más frágil |
| 5 | `gemini-2.5-flash-tts` con voz `Aoede` | **Pendiente** | Ídem |
| 6 | La región `global` sirve los modelos | **Parcial** | El *endpoint* `global` existe y responde 401 (§1). Qué modelos sirve, pendiente |
| 7 | El SDK acepta `genai.Client(enterprise=True, ...)` | **Sí** | Verificado en `google-genai` 2.22: `enterprise` es un parámetro real, alias de `vertexai`. El fallback a `vertexai=True` cubre las versiones 1.x |

**Coste real de estas pruebas: €0.** Todo lo verificado se hizo sin credenciales, contra respuestas HTTP públicas y contra el SDK instalado en local. No se ha gastado crédito.

---

## 6. Lo que queda pendiente y depende del productor

1. **`VERTEX_PROJECT_ID` está vacío** en `config.yaml`, `.env.example` y `cloudbuild.yaml` (`_VERTEX_PROJECT_ID: ""`). Es así por diseño —vacío significa «Vertex inactiva», y es el interruptor para cuando se agote el crédito— pero implica que, incluso con el endpoint corregido, **el crédito no se toca hasta declarar el proyecto**. El valor es **`yuki-prod`**.
2. **Las tres claves de AI Studio** (`ais-gemini-key-*`) siguen vivas en el proyecto `gen-lang-client-0734039446`. Mientras existan, pueden seguir facturando fuera del crédito (§2).
3. **Verificar los cinco modelos** con `python3 cli.py vertex-check` una vez haya proyecto (§5).
4. **Presupuesto y alertas**, runbook §8. **Hecho** (7 sep 2026).
5. **Compute Engine: €2,91** — **explicado**: es la VM `yuki-agent`, donde corre Yuki. Consume crédito, que es lo que se quiere. Pero ojo a §4.bis: hay que revisarle los ámbitos.
6. **El crédito caduca el 23 de septiembre de 2026** con €252,29 sin usar.

Los pasos concretos del panel están en `docs/RUNBOOK_GCLOUD.md` §§2, 3 y 8.
