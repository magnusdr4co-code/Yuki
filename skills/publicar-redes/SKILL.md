---
name: publicar-redes
description: Publica un lanzamiento multimodal (texto, portada FAL y nota de voz TTS) en los canales activos de Telegram y Discord, guardando el registro en ./output/posts/.
parameters:
  type: object
  properties:
    message:
      type: string
      description: Texto o poema de la publicación.
    visual_prompt:
      type: string
      description: Idea visual para generar la imagen acompañante con FAL.ai.
    channel:
      type: string
      description: Destino de la publicación ("all", "telegram", "discord").
      default: "all"
  required:
    - message
---

# Habilidad: Publicar en Redes (`/publicar-redes`)

Permite a **Yuki** realizar publicaciones completas de forma reactiva o autónoma en sus comunidades digitales.

## Pasos de Ejecución:

1. **Generación Multimodal:**
   - Si se incluye `visual_prompt`, invoca la habilidad `/generar-portada`.
   - Genera la nota de voz correspondiente mediante `/sintesis-vocal`.
2. **Registro Local:**
   - Guarda el borrador y registro en `./output/posts/drop_<timestamp>.md`.
3. **Despacho a Adaptadores:**
   - Envía el paquete a través de `TelegramAdapter` y `DiscordAdapter`.
