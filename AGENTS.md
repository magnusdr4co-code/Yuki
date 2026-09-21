# AGENTS.md — Directrices de Desarrollo y Operación para Hermes Agent

Este archivo define la arquitectura del software, flujos de trabajo, rutas del workspace y directrices para que **Hermes Agent** opere sobre este repositorio sin cometer errores de contexto.

---

## 1. Visión y Rol de Hermes

Hermes actúa como el arnés de ejecución y cerebro operativo de **Yuki (Diva Digital Autónoma)**. 
- **Workspace Nativo:** Hermes opera directamente sobre la raíz del repositorio local. NO intentes forzar rutas protegidas o absolutas de otros arneses (como `~/.openclaw/workspace/`). Todos los archivos de salida generados deben persistirse en `./output/`.
- **Memoria sin Context Rot:** Todas las consultas sobre el historial, acuerdos del productor y datos de fans deben canalizarse a través del motor `src/memory/fts5_memory.py` (SQLite FTS5), NUNCA reinyectando logs masivos en bruto.
- **El mapa entero está en `CLAUDE.md`**, que es el que se mantiene al día.
  Además de lo de abajo existen `src/tools/criterio_*.py` (cada arte decide
  antes de encargar), `src/tools/media_jobs.py` (cola durable de lo facturable),
  `src/tools/receta.py`, `src/tools/creation_library.py`, `src/core/cotejo.py`
  (contrasta lo dicho con lo ejecutado) y `src/security/model_armor.py`.
- **Herramientas de medios:** `src/tools/nous_portal.py` es la puerta única. Por debajo, con proyecto de Google Cloud declarado, sirve `src/tools/vertex_media.py` —Imagen para portadas, Gemini Omni Flash para vídeo y Gemini TTS para voz—; sin él, el gateway de Nous Portal (FAL, OpenAI TTS y Whisper, Firecrawl, Browser Use, Modal).
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

Hermes gestiona una base de datos SQLite relacional con extensión virtual FTS5:
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

Cada habilidad en `skills/<nombre-skill>/SKILL.md` es invocable por Hermes como un comando barra (ej. `/componer-beat`, `/generar-portada`, `/sintesis-vocal`, `/publicar-redes`, `/analizar-feed`, `/lectura-runas`).
- Al ejecutar una habilidad, Hermes debe leer su `SKILL.md`, extraer los parámetros requeridos, invocar las herramientas necesarias y almacenar el resultado en `./output/<tipo>/`.
- Cada `SKILL.md` incluye una sección **`## Herramientas`** con su contrato: qué herramienta usa en cada paso, con qué *tier* de modelo, qué cuesta, dónde persiste y qué hacer si falla. Ese contrato es vinculante; ante duda, manda [`skills/HERRAMIENTAS.md`](skills/HERRAMIENTAS.md).

---

## 5. Protocolos Anti-Errores para Hermes

1. **Rutas Relativas:** Usa siempre rutas relativas al repositorio (ej. `output/art/cover_01.png`), nunca rutas absolutas fijas con nombres de usuario del sistema operativo.
2. **Telegram, lo justo:** la salida es real (API HTTP, con marca y freno) y la
   construye el daemon si hay `TELEGRAM_BOT_TOKEN`. **No hay entrada**: no
   existe `getUpdates`, así que Yuki no responde por Telegram, sólo publica.
3. **Preservación del Alma:** Al generar respuestas para usuarios externos o redes sociales, respeta siempre la voz definida en `SOUL.md` (pausas deliberadas, atención plena, evitar la adulación mecánica).
4. **Optimización de Tokens:** Elegir *tier* es obligatorio; no existe "el modelo por defecto". `tier_0_reflex` para formateo y clasificación, `tier_1_creative` para la voz de Yuki hacia una persona, `tier_2_nuclear` (con `reasoning: high`) sólo para síntesis profunda. Detalle en [`skills/HERRAMIENTAS.md`](skills/HERRAMIENTAS.md) §2.
5. **Nunca simules una herramienta:** si una llamada falla y no hay respaldo, aborta y explícalo. Un resultado inventado (una imagen que no existe, una tendencia no rastreada, una síntesis de relleno) contamina la memoria y engaña al productor.
6. **Transparencia obligatoria:** la primera interacción de cada conversación deja claro que Yuki es una IA, y el contenido generado se etiqueta al publicarlo.
