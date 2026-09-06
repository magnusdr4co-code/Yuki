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

Y una conclusión que **no** es un defecto del código: los €2,01 de la línea *Gemini API* **no los ha generado Yuki**. Ver §2.

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

## 2. Los €2,01 del producto «Gemini API»

**La columna que resuelve la duda es `Product`, no las de ahorros.**

| Product en el panel | API real | ¿Consume el crédito? |
|---|---|---|
| **Vertex AI** | `aiplatform.googleapis.com` | Sí |
| **Gemini API** | `generativelanguage.googleapis.com` (AI Studio) | No |

**Yuki no llama nunca a `generativelanguage.googleapis.com`.** No hay una sola ruta en el código que use `GEMINI_API_KEY`: la pasarela de texto se autentica con ADC y la de medios con el SDK apuntado a Vertex. Ese gasto viene de otro proceso.

Se descartó además una sospecha razonable: que el SDK `google-genai` se fuera a AI Studio al encontrar la clave en el entorno. **No ocurre.** Con `GEMINI_API_KEY` puesta y `enterprise=True` + proyecto + región, el cliente sigue apuntando a `aiplatform.googleapis.com` e ignora la clave. Con el proyecto vacío no cae a AI Studio: falla con `DefaultCredentialsError`.

**Matiz importante sobre el «€0,00» de las columnas de ahorro.** No prueba nada por sí solo: los créditos de prueba **no se restan ahí**. Aparecen en la fila de promociones y créditos del informe de costes. Lo que sí prueba algo es el producto.

**Dónde buscar el origen:** en el `.env` local, en el servicio de Cloud Run, en los Cloud Run Jobs, en `hermes_config.yaml:18` (declara `google: "${GEMINI_API_KEY}"` como ruta de emergencia del agregador) y en cualquier herramienta externa apuntada al mismo proyecto (Gemini CLI, AI Studio, un cuaderno).

---

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

1. **`VERTEX_PROJECT_ID` está vacío** en `config.yaml`, `.env.example` y `cloudbuild.yaml` (`_VERTEX_PROJECT_ID: ""`). Es así por diseño —vacío significa «Vertex inactiva»— pero implica que, incluso con el endpoint corregido, **el crédito no se toca hasta declarar el proyecto**.
2. **Rastrear los €2,01** del producto *Gemini API* (§2).
3. **Verificar los cinco modelos** con `python3 cli.py vertex-check` una vez haya proyecto (§5).
4. **Presupuesto y alertas**, runbook §8. Sin poner.

Los pasos concretos del panel están en `docs/RUNBOOK_GCLOUD.md` §§2, 3 y 8.
