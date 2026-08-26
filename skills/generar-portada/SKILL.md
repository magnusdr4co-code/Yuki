---
name: generar-portada
description: Pinta e ilustra portadas de sencillos o arte visual conceptual utilizando FAL.ai a través de Nous Portal y guarda la imagen en ./output/art/.
parameters:
  type: object
  properties:
    track_title:
      type: string
      description: Título del sencillo o concepto artístico a ilustrar.
    visual_concept:
      type: string
      description: Descripción de los elementos visuales, texturas o atmósfera deseada.
    aspect_ratio:
      type: string
      description: Proporción de la imagen ("1:1", "16:9", "9:16"). Por defecto "1:1".
      default: "1:1"
  required:
    - track_title
    - visual_concept
---

# Habilidad: Generar Portada (`/generar-portada`)

Permite a **Yuki** crear de forma autónoma la portada visual para sus sencillos o publicaciones sociales consumiendo el Tool Gateway de **Nous Portal (FAL.ai Flux/SDXL)**.

## Pasos de Ejecución:

1. **Refinamiento del Prompt con Estética Yuki:**
   - Añade automáticamente el prefijo de estilo: *masterpiece, ethereal photography, cinematic lighting, japanese aesthetic, subtle elegance, soft haze, industrial metallic undertone*.
2. **Invocación a Nous Portal (FAL):**
   - Ejecuta la llamada a la herramienta `generate_image_fal` especificando la proporción deseada.
3. **Almacenamiento Local:**
   - Guarda el archivo `.png` resultante en `./output/art/yuki_art_<timestamp>.png`.
4. **Entrega y Notificación:**
   - Proporciona la ruta local y la URL del CDN generada para adjuntarla a lanzamientos o redes sociales.
