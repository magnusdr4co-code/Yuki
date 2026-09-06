---
name: sintesis-vocal
description: Sintetiza notas de voz en OGG Opus con la entonación cálida y las pausas deliberadas de Yuki usando Gemini TTS sobre Vertex AI (o el TTS del Tool Gateway como respaldo), guardando el audio en ./output/voice/.
parameters:
  type: object
  properties:
    text:
      type: string
      description: Texto o mensaje que Yuki expresará en audio.
    cadence_pause_ms:
      type: integer
      description: Duración de las micro-pausas en milisegundos para reflejar el lenguaje prestado.
      default: 350
  required:
    - text
---

# Habilidad: Síntesis Vocal (`/sintesis-vocal`)

Genera notas de voz emotivas y pausadas para interactuar con seguidores en Telegram y Discord o responder a menciones directas.

## Pasos de Ejecución:

1. **Cadencia:**
   - Con `vertex.tts`, la pausa elegida se **describe en lenguaje natural** en el `prompt` del modelo. Con `portal.tts`, se insertan intervalos de respiración en comas y puntos.
2. **Síntesis:**
   - Invoca `vertex.tts` (`gemini-2.5-flash-tts`, voz `Aoede`, `es-es`) si hay proyecto declarado; si no, `portal.tts`.
3. **Transcodificado — sólo en el respaldo:**
   - `vertex.tts` emite OGG Opus nativo: no hay que transcodificar. Con `portal.tts`, convierte con `local.ffmpeg`; Telegram no reproduce como nota de voz nativa ningún otro formato.
4. **Persistencia en el Workspace:**
   - Almacena el audio en `./output/voice/yuki_voice_<timestamp>.ogg`.
5. **Respuesta:**
   - Retorna la ruta del archivo y la duración calculada para su envío inmediato por canales sociales.

## Herramientas

> Contrato de herramientas según [`skills/HERRAMIENTAS.md`](../HERRAMIENTAS.md). Si una herramienta no está listada ahí, no existe.

| Paso | Herramienta | Detalle |
|---|---|---|
| Redactar o pulir el texto | `portal.chat` → `tier_1_creative` | Sólo si el texto no viene ya dado |
| Sintetizar (preferente) | `vertex.tts` | `gemini-2.5-flash-tts`, voz `Aoede`, `es-es`. La cadencia va en el `prompt`, en lenguaje natural. **OGG Opus nativo** |
| Sintetizar (respaldo) | `portal.tts` | OpenAI TTS del Tool Gateway; facturado por tokens contra los créditos |
| Insertar las micro-pausas | — | **Sólo en el respaldo:** en el texto (350 ms por defecto en comas y puntos). No se le piden al modelo |
| Transcodificar | `local.ffmpeg` | **Sólo en el respaldo:** `ffmpeg -i entrada.mp3 -c:a libopus -b:a 32k salida.ogg` |
| Guardar | — | `./output/voice/yuki_voice_<timestamp>.ogg` |

**Voz entrante:** para escuchar una nota de voz de un seguidor, usa `portal.stt` (Whisper, ≈ 0.0063 USD/minuto) antes de pasar el texto a `local.memory`.

**Si falla:** un reintento, luego la siguiente pasarela de la tabla avisando del cambio. Sin respaldo disponible, responde en texto y explica por qué no hay audio. Nunca devuelvas la ruta de un marcador como si fuera una nota de voz.
