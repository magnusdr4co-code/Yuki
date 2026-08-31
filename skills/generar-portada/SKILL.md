---
name: generar-portada
description: Pinta e ilustra portadas de sencillos o arte visual conceptual con los modelos de imagen de FAL a través del Tool Gateway de Nous Portal y guarda la imagen en ./output/art/.
parameters:
  type: object
  properties:
    track_title:
      type: string
      description: Título del sencillo o concepto artístico a ilustrar.
    visual_concept:
      type: string
      description: Descripción de los elementos visuales, texturas o atmósfera deseada.
    model:
      type: string
      description: Modelo de imagen del Tool Gateway ("fal/flux-2-pro", "fal/nano-banana-pro", "fal/ideogram-v3", "fal/recraft-v4").
      default: "fal/flux-2-pro"
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

Permite a **Yuki** crear de forma autónoma la portada visual para sus sencillos o publicaciones sociales usando `portal.image`.

## Pasos de Ejecución:

1. **Alineación con la Micro-Estación y Estética Yuki:**
   - Inyecta automáticamente los *kigo* estacionales y el prefijo de estilo: *masterpiece, ethereal composition, japanese aesthetic, subtle elegance, industrial metallic undertone*.
2. **Invocación al Tool Gateway:**
   - Envía la solicitud a `portal.image` con el modelo seleccionado (`fal/flux-2-pro` por defecto).
3. **Persistencia en el Workspace Nativo:**
   - Almacena el archivo `.png` en `./output/art/yuki_<modelo>_<timestamp>.png`.
4. **Entrega:**
   - Proporciona la ruta local y la URL del CDN generada para adjuntarla al lanzamiento.

## Herramientas

> Contrato de herramientas según [`skills/HERRAMIENTAS.md`](../HERRAMIENTAS.md). Si una herramienta no está listada ahí, no existe.

| Paso | Herramienta | Detalle |
|---|---|---|
| Elegir modelo | `portal.image` | `fal/flux-2-pro` por defecto · `fal/nano-banana-pro` si la imagen lleva texto legible · `fal/ideogram-v3` para tipografía y carteles · `fal/recraft-v4` para vectorial |
| Enriquecer el *prompt* | `local.memory` | Recupera el `kigo` de la micro-estación y el prefijo estético de `SOUL.md`. Máximo 5 fragmentos |
| Generar | `portal.image` | **Una sola imagen por petición.** ≈ 0.005–0.26 USD contra los créditos del Portal |
| Guardar | — | `./output/art/yuki_<modelo>_<timestamp>.png`, ruta relativa |

**Si `portal.image` falla:** un reintento; luego cae a la Image API de OpenRouter y **dilo en la respuesta**. Si tampoco responde, aborta: no describas una imagen que no existe ni devuelvas una URL inventada.

**Antes de publicarla:** conserva los metadatos de origen del proveedor (marcado de contenido sintético). No re-codifiques la imagen de forma que se pierdan.
