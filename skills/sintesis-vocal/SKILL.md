---
name: sintesis-vocal
description: Sintetiza respuestas en notas de voz realistas en formato OGG Opus con la entonación cálida y las pausas deliberadas de Yuki usando Nous TTS, guardando el audio en ./output/voice/.
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
2. **Invocación a Nous TTS:**
   - Emplea el modelo de voz `yuki_serene_alto`.
3. **Persistencia en el Workspace:**
   - Almacena el audio en `./output/voice/yuki_voice_<timestamp>.ogg`.
4. **Respuesta:**
   - Retorna la ruta del archivo y la duración calculada para su envío inmediato por canales sociales.
