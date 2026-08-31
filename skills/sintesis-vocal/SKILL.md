---
name: sintesis-vocal
description: Sintetiza notas de voz en OGG Opus con la entonación cálida y las pausas deliberadas de Yuki usando el TTS del Tool Gateway de Nous Portal, guardando el audio en ./output/voice/.
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

1. **Inyección de Pausas:**
   - Procesa el texto de entrada insertando intervalos de respiración (*cadence pauses*) en comas y puntos.
2. **Síntesis:**
   - Invoca `portal.tts` con la voz configurada en `config.yaml`.
3. **Transcodificado obligatorio:**
   - Convierte la salida a OGG Opus con `local.ffmpeg`; Telegram no reproduce como nota de voz nativa ningún otro formato.
4. **Persistencia en el Workspace:**
   - Almacena el audio en `./output/voice/yuki_voice_<timestamp>.ogg`.
5. **Respuesta:**
   - Retorna la ruta del archivo y la duración calculada para su envío inmediato por canales sociales.

## Herramientas

> Contrato de herramientas según [`skills/HERRAMIENTAS.md`](../HERRAMIENTAS.md). Si una herramienta no está listada ahí, no existe.

| Paso | Herramienta | Detalle |
|---|---|---|
| Redactar o pulir el texto | `portal.chat` → `tier_1_creative` | Sólo si el texto no viene ya dado |
| Insertar las micro-pausas | — | Se insertan **en el texto** (350 ms por defecto en comas y puntos). No se le piden al modelo |
| Sintetizar | `portal.tts` | OpenAI TTS del Tool Gateway; facturado por tokens contra los créditos |
| Transcodificar | `local.ffmpeg` | `ffmpeg -i entrada.mp3 -c:a libopus -b:a 32k salida.ogg` — **paso obligatorio** |
| Guardar | — | `./output/voice/yuki_voice_<timestamp>.ogg` |

**Voz entrante:** para escuchar una nota de voz de un seguidor, usa `portal.stt` (Whisper, ≈ 0.0063 USD/minuto) antes de pasar el texto a `local.memory`.

**Si falla:** un reintento, luego TTS de OpenRouter avisando del cambio. Sin respaldo disponible, responde en texto y explica por qué no hay audio.
