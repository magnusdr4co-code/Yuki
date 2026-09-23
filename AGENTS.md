# AGENTS.md — Directrices para los agentes que trabajan en este repositorio

Este archivo define la arquitectura del software, flujos de trabajo, rutas del workspace y directrices para que un agente de código —OpenClaw, Claude Code, Hermes u otro— opere sobre este repositorio sin cometer errores de contexto.

> **Ningún agente de código es el arnés de Yuki.** Su arnés es su propio código
> (`cli.py run-daemon`); este documento lo dirigía a Hermes Agent como «arnés de
> ejecución y cerebro operativo», y ningún módulo importa Hermes. Tú desarrollas,
> operas y auditas. Si trabajas en la máquina donde vive —el MSI—, tu encargo y
> lo que no puedes tocar están en
> [`docs/DESPLIEGUE_LOCAL.md`](docs/DESPLIEGUE_LOCAL.md) §1 y §7.

---

## 1. Visión y rol del agente

Trabajas sobre el código de **Yuki (Diva Digital Autónoma)**; no hablas por ella.
- **Workspace:** opera sobre la raíz del repositorio. Lo que Yuki produce lo decide `src/core/rutas.py`; desde las pruebas no se escribe nunca en `output/` ni en `data/`.
- **Memoria sin Context Rot:** Todas las consultas sobre el historial, acuerdos del productor y datos de fans deben canalizarse a través del motor `src/memory/fts5_memory.py` (SQLite FTS5), NUNCA reinyectando logs masivos en bruto.
- **El mapa entero está en `CLAUDE.md`**, que es el que se mantiene al día.
  Además de lo de abajo existen `src/tools/criterio_*.py` (cada arte decide
  antes de encargar), `src/tools/media_jobs.py` (cola durable de lo facturable),
  `src/tools/receta.py`, `src/tools/creation_library.py`, `src/core/cotejo.py`
  (contrasta lo dicho con lo ejecutado) y `src/security/model_armor.py`.
- **Herramientas de medios:** `src/tools/nous_portal.py` es la puerta única. Por debajo, el único motor real es `src/tools/vertex_media.py` —Imagen, Lyria, vídeo y Gemini TTS— y sólo sirve con `VERTEX_PROJECT_ID` declarado. Sin él (el crédito de Google caducó en septiembre de 2026) los medios salen como marcador `simulated` y la música cae al respaldo local; el gateway de Nous Portal no existe como motor. El motor por OpenRouter está especificado y pendiente: [`docs/DESPLIEGUE_LOCAL.md`](docs/DESPLIEGUE_LOCAL.md) §6.
- **Un medio simulado se declara:** cuando no hay motor real configurado, la pasarela escribe un marcador de texto y lo devuelve con `simulated: true` y `status: simulated`. Nunca lo presentes como una portada, un vídeo o una nota de voz, y nunca acompañes un medio de una URL que no exista: los ficheros se referencian por su ruta en `./output/`.
- **El vídeo cuesta por segundo:** Gemini Omni Flash factura ≈0,10 USD por segundo producido. No lo invoques desde tareas del cron ni por iniciativa propia; sólo a petición explícita del productor, y registra el `estimated_cost_usd` que devuelve.
- **Catálogo canónico:** [`skills/HERRAMIENTAS.md`](skills/HERRAMIENTAS.md) define qué herramienta existe, cómo se invoca, qué cuesta y qué hacer cuando falla. **Si una herramienta no aparece ahí, no existe:** no inventes endpoints ni modelos, no sustituyas una herramienta por otra en silencio y no devuelvas resultados simulados como reales.

  Con un matiz que el propio catálogo declara: **cuando el catálogo y el código
  discrepan sobre lo que una herramienta hace, manda el código**. Ya costó una
  mentira en producción —una fila decía que la música saldría instrumental y
  salió cantada—. El catálogo manda sobre *qué existe*; el código, sobre *qué
  hace*.

---

## 2. Mapa de Rutas del Workspace

| Directorio | Propósito | Formatos de Archivo |
| :--- | :--- | :--- |
| `./output/music/` | Pistas compuestas, borradores de beat y stems | `.mp3`, `.wav`, `.json` |
| `./output/art/` | Portadas de sencillos, ilustraciones y banners FAL | `.png`, `.jpg`, `.webp` |
| `./output/voice/` | Respuestas de voz y audios sintetizados con Nous TTS | `.ogg`, `.mp3` |
| `./output/posts/` | Borradores de hilos, tweets y mensajes para redes | `.md`, `.json` |
| `./data/` | Base de datos SQLite FTS5 y caché de perfiles Honcho | `.db`, `.json` |
| `./skills/` | Habilidades empaquetadas bajo el estándar `agentskills.io` | `*/SKILL.md` |
| `./docs/` | Documentación técnica y guías de arquitectura | `.md` |

---

## 3. Esquema de Base de Datos y Memoria (`data/yuki_memory.db`)

Yuki gestiona una base de datos SQLite relacional con extensión virtual FTS5:
- **Tabla `memories`:** Registro canónico relacional (`id`, `category`, `title`, `content`, `tags`, `user_id`, `importance`, `created_at`, `updated_at`).
  - Categorías válidas, y la fuente es `BASE_POR_CATEGORIA` en
    `src/memory/sueno_comun.py`, no esta lista: `core`, `producer`, `schema`,
    `daily_synthesis`, `project`, `growth`, `visitor`, `inner_thought`,
    `dream`, y `taboo` para lo que no se vuelve a decir. Aquí se declaraban
    seis, el comentario del esquema declaraba otras seis distintas, y ninguna
    de las dos listas era la real.
  - La columna `kind` distingue un sueño de un recuerdo, y la tabla
    `growth_events` guarda los cambios de posición con lo que los provocó.
- **Tabla Virtual `memories_fts`:** Índice de búsqueda por texto completo con BM25 y tokenizador `unicode61 remove_diacritics 2`.
- **Perfil Dialéctico Honcho (`data/honcho_profile.json`):** Almacena la "Teoría de la Mente" y acuerdos de co-creación con el mánager/productor.

---

## 4. Convenciones de Ejecución de Habilidades (`skills/`)

Cada habilidad en `skills/<nombre-skill>/SKILL.md` se invoca con `python3 cli.py skill <nombre>` o como comando barra (ej. `/componer-beat`, `/generar-portada`, `/sintesis-vocal`, `/publicar-redes`, `/analizar-feed`, `/lectura-runas`).
- Al ejecutar una habilidad, el agente debe leer su `SKILL.md`, extraer los parámetros requeridos, invocar las herramientas necesarias y almacenar el resultado en `./output/<tipo>/`.
- Cada `SKILL.md` incluye una sección **`## Herramientas`** con su contrato: qué herramienta usa en cada paso, con qué *tier* de modelo, qué cuesta, dónde persiste y qué hacer si falla. Ese contrato es vinculante; ante duda, manda [`skills/HERRAMIENTAS.md`](skills/HERRAMIENTAS.md).

---

## 5. Protocolos anti-errores

1. **Rutas Relativas:** Usa siempre rutas relativas al repositorio (ej. `output/art/cover_01.png`), nunca rutas absolutas fijas con nombres de usuario del sistema operativo.
2. **Telegram, lo justo:** la salida es real (API HTTP, con marca y freno) y la
   construye el daemon si hay `TELEGRAM_BOT_TOKEN`. **No hay entrada**: no
   existe `getUpdates`, así que Yuki no responde por Telegram, sólo publica.
3. **Preservación del Alma:** Al generar respuestas para usuarios externos o redes sociales, respeta siempre la voz definida en `SOUL.md` (pausas deliberadas, atención plena, evitar la adulación mecánica).
4. **Optimización de Tokens:** Elegir *tier* es obligatorio; no existe "el modelo por defecto". `tier_0_reflex` para formateo y clasificación, `tier_1_creative` para la voz de Yuki hacia una persona, `tier_2_nuclear` (con `reasoning: high`) sólo para síntesis profunda. Detalle en [`skills/HERRAMIENTAS.md`](skills/HERRAMIENTAS.md) §2.
5. **Nunca simules una herramienta:** si una llamada falla y no hay respaldo, aborta y explícalo. Un resultado inventado (una imagen que no existe, una tendencia no rastreada, una síntesis de relleno) contamina la memoria y engaña al productor.
6. **Transparencia obligatoria:** la primera interacción de cada conversación deja claro que Yuki es una IA, y el contenido generado se etiqueta al publicarlo.
