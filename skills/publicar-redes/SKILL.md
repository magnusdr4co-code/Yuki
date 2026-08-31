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
      description: Idea visual para generar la imagen acompañante con portal.image.
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
   - Envía el paquete a través de `adapter.telegram` y `adapter.discord`.

## Herramientas

> Contrato de herramientas según [`skills/HERRAMIENTAS.md`](../HERRAMIENTAS.md). Si una herramienta no está listada ahí, no existe.

| Paso | Herramienta | Detalle |
|---|---|---|
| Imagen acompañante | `/generar-portada` → `portal.image` | Sólo si hay `visual_prompt` |
| Nota de voz | `/sintesis-vocal` → `portal.tts` + `local.ffmpeg` | OGG Opus o Telegram no la reproduce como voz |
| Formateo por canal | `portal.chat` → `tier_0_reflex` | Longitudes y menciones difieren entre Telegram y Discord |
| Envío | `adapter.telegram`, `adapter.discord` | Telegram en *long polling*, Discord por WebSocket saliente |
| Archivo | — | `./output/posts/drop_<timestamp>.md` con fecha, canal y herramientas usadas |

### Obligatorio antes de cada publicación

1. **Aviso de IA** en la primera interacción de cada conversación y en las biografías de las cuentas. No es negociable y no "rompe el personaje": es obligación legal en vigor.
2. **Etiqueta de contenido generado** en la plataforma que la soporte, además de conservar la marca técnica de la imagen o el audio.
3. **Un canal fallido no cancela el resto:** publica en los que respondan y di con claridad cuál falló.
4. **Instagram (fase 3, `adapter.instagram`):** publicación en dos pasos (contenedor de media → `media_publish`) y **ninguna publicación automática sin revisión del productor** durante las primeras semanas.
