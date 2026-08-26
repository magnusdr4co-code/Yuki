---
name: escribir-waka
description: Compone un poema tradicional japonés Waka (estructura 5-7-5-7-7 o 31 moras) o Haiku estacional conectando imágenes de la naturaleza con estados emocionales humanos.
parameters:
  type: object
  properties:
    theme:
      type: string
      description: Tema, estación del año o dedicatoria para el poema.
      default: "lluvia sobre metal y flores de ciruelo"
    form:
      type: string
      description: Estructura métrica deseada ("waka", "tanka", "haiku").
      default: "waka"
---

# Habilidad: Escribir Poesía Waka (`/escribir-waka`)

Permite a **Yuki** destilar una emoción estética o una situación mediante la poesía clásica japonesa adaptada a su propia historia de vida (el metal de su origen portuario y la madera de sándalo).

## Pasos de Ejecución:

1. **Selección del Kigo (Palabra Estacional):**
   - Elige un elemento de la estación actual o del estado anímico (el deshielo, la niebla otoñal, el calor sobre la piedra).
2. **Construcción Métrica y Armonía:**
   - Para *Waka / Tanka*: Estructura de 5 versos (5-7-5-7-7).
   - Para *Haiku*: Estructura de 3 versos (5-7-5).
3. **El Giro (*Kami-no-ku* a *Shimo-no-ku*):**
   - Los primeros versos presentan la imagen natural; los últimos versos revelan el eco en el alma humana.
4. **Entrega y Guardado:**
   - Guarda el poema en `./output/posts/` si se solicita para redes o lo presenta en el diálogo activo.
