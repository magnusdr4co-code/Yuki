---
name: ikebana-curaduria
description: Aplica los principios asimétricos del Kado (Ikebana: Ten-Chi-Jin / Cielo-Tierra-Hombre) para curar, ordenar y desaturar publicaciones, diseños visuales o listas de contenido.
parameters:
  type: object
  properties:
    content:
      type: string
      description: Texto, borrador de publicación o lista de ideas que se desea curar con principios de Ikebana.
    medium:
      type: string
      description: Canal o formato destino ("social_post", "album_tracklist", "visual_composition").
      default: "social_post"
  required:
    - content
---

# Habilidad: Curaduría Ikebana (`/ikebana-curaduria`)

Permite a **Yuki** trasladar la sabiduría milenaria del arreglo floral (*Kado*) a la comunicación y curaduría digital.

## Principios de Ejecución:

1. **La Estructura *Ten-Chi-Jin* (El Triángulo Armónico):**
   - **Shin (Cielo):** La idea principal, la línea más alta y definitoria del mensaje.
   - **Soe (Hombre):** El elemento complementario que aporta calidez y conexión con el espectador.
   - **Hikae (Tierra):** La base que ancla el mensaje a la realidad y a la acción.
2. **Poda del Exceso (*Ka*):**
   - Elimina cualquier palabra, adorno o hashtag superfluo que compita con la línea principal.
3. **Respeto al Vacío:**
   - Garantiza que haya suficiente espacio en blanco entre las ideas para que cada elemento respire.

## Herramientas

> Contrato de herramientas según [`skills/HERRAMIENTAS.md`](../HERRAMIENTAS.md). Si una herramienta no está listada ahí, no existe.

| Paso | Herramienta | Detalle |
|---|---|---|
| Curar y podar | `portal.chat` → `tier_1_creative` | `reasoning: low`. Estructura *Ten-Chi-Jin*, poda del exceso |

**Coste mínimo y sin red.** Trabaja sobre el contenido que recibe; no busca ni genera material nuevo.

Si el contenido a curar es una publicación destinada a redes, devuélvela lista para `/publicar-redes` — sin hashtags de relleno y respetando el vacío entre ideas.
