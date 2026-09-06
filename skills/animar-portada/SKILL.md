---
name: animar-portada
description: Anima una portada ya pintada o genera un teaser breve con audio nativo usando Gemini Omni Flash sobre Vertex AI, guardando el vídeo en ./output/video/. Herramienta cara, facturada por segundo de vídeo.
parameters:
  type: object
  properties:
    motion_concept:
      type: string
      description: Qué debe ocurrir en el plano; el movimiento, no la escena estática.
    image_path:
      type: string
      description: Ruta de la portada de partida (./output/art/...). Si se omite, el vídeo se genera desde el texto.
    duration_seconds:
      type: integer
      description: Duración en segundos. Entero de 3 a 10.
      default: 6
    aspect_ratio:
      type: string
      description: Proporción del vídeo ("16:9", "9:16", "1:1").
      default: "9:16"
  required:
    - motion_concept
---

# Habilidad: Animar Portada (`/animar-portada`)

Da movimiento a la obra visual de Yuki: anima una portada ya pintada o genera un teaser breve para el lanzamiento de un sencillo.

> **Antes de nada, el coste.** Esta es la herramienta más cara del catálogo: **≈0,10 USD por segundo de vídeo**. Un teaser de 10 segundos cuesta alrededor de 1 USD, más que miles de respuestas de texto de Yuki. No se invoca por iniciativa propia.

## Pasos de Ejecución:

1. **Confirmar que hay petición explícita:**
   - Esta habilidad **sólo** se ejecuta si el productor la ha pedido. Nunca desde una tarea del cron, nunca "para enseñar lo que se puede hacer".
2. **Preferir una portada existente:**
   - Si hay un `image_path`, se usa `image_to_video`. Es el flujo natural —primero el arte, después el movimiento— y permite revisar el fotograma de partida antes de gastar.
   - Sin imagen, `text_to_video` desde el concepto, con el prefijo estético de `SOUL.md`.
3. **Describir el movimiento, no la escena:**
   - El modelo ya ve la imagen. El *prompt* dice qué se mueve, cómo y en qué orden: "la niebla avanza de izquierda a derecha mientras el pan de oro capta la luz".
4. **Acotar la duración:**
   - Entero de 3 a 10 segundos. Por defecto 6. Fuera de rango se rechaza antes de llamar al modelo.
5. **Registrar el gasto:**
   - El resultado trae `estimated_cost_usd`. Anótalo junto a la habilidad que lo consumió y comunícaselo al productor.

## Herramientas

> Contrato de herramientas según [`skills/HERRAMIENTAS.md`](../HERRAMIENTAS.md). Si una herramienta no está listada ahí, no existe.

| Paso | Herramienta | Detalle |
|---|---|---|
| Pintar el fotograma de partida | `vertex.image` | Vía `/generar-portada`. Opcional pero recomendado: revisar antes de animar sale más barato que repetir |
| Redactar el concepto de movimiento | `portal.chat` → `tier_1_creative` | Sólo si el productor no lo ha dado ya |
| Animar | `vertex.video` | `gemini-omni-flash-preview`. **≈0,10 USD/s.** De 3 a 10 s. Una toma por petición |
| Guardar | — | `./output/video/yuki_omni_<timestamp>.mp4`, ruta relativa |

**No confundas Omni con un modelo de texto.** Genera vídeo y se factura por segundo. El cerebro de Yuki lo sirve `vertex.chat`/`portal.chat` (§2 del catálogo).

**Si falla:** **no hay respaldo.** Un reintento y, si no responde, aborta y explícalo. Nunca describas un vídeo que no existe ni devuelvas la ruta de un marcador como si fuera metraje.

**Antes de publicarlo:** el vídeo lleva marca SynthID de Google. Consérvala, etiqueta el contenido como generado y archiva la publicación en `./output/posts/` (§8 del catálogo).
