---
name: generar-portada
description: Pinta e ilustra portadas de sencillos o arte visual conceptual utilizando modelos de frontera (Google Gemini Image / Imagen 3, Seedream o FAL Flux Pro) a través de Nous Portal y guarda la imagen en ./output/art/.
parameters:
  type: object
  properties:
    track_title:
      type: string
      description: Título del sencillo o concepto artístico a ilustrar.
    visual_concept:
      type: string
      description: Descripción de los elementos visuales, texturas o atmósfera deseada.
    provider:
      type: string
      description: Motor de frontera visual ("gemini_image", "seedream", "flux_pro").
      default: "gemini_image"
    lighting:
      type: string
      description: Matriz de iluminación tradicional ("komorebi", "urushi", "industrial_rain").
      default: "komorebi"
    aspect_ratio:
      type: string
      description: Proporción de la imagen ("1:1", "16:9", "9:16").
      default: "1:1"
  required:
    - track_title
    - visual_concept
---

# Habilidad: Generar Portada (`/generar-portada`)

Permite a **Yuki** crear de forma autónoma la portada visual para sus sencillos o publicaciones sociales consumiendo modelos de **Inteligencia Artificial de Frontera**:
- **`gemini_image`**: Google Imagen 3 / Gemini Image Generation (fotorrealismo, texturas orgánicas y composición equilibrada).
- **`seedream`**: Seedream 2.5 HD (estilismo conceptual, Kintsugi y trazos expresivos).
- **`flux_pro`**: FAL Flux 1.1 Pro Ultra (iluminación cinematográfica 8K).

## Pasos de Ejecución:

1. **Alineación con la Micro-Estación y Estética Yuki:**
   - Inyecta automáticamente los *kigo* estacionales y el prefijo de estilo: *masterpiece, ethereal composition, japanese aesthetic, subtle elegance, industrial metallic undertone*.
2. **Invocación a Nous Portal:**
   - Envía la solicitud al backend del proveedor seleccionado (`gemini_image`, `seedream` o `flux_pro`).
3. **Persistencia en el Workspace Nativo:**
   - Almacena el archivo `.png` en `./output/art/yuki_<provider>_<timestamp>.png`.
4. **Entrega:**
   - Proporciona la ruta local y la URL del CDN generada para adjuntarla al lanzamiento.
