---
name: componer-beat
description: Compone la estructura armónica de una pieza y escribe la partitura MIDI multipista procedural en ./output/music/. La síntesis de audio cantado no está disponible por ahora.
parameters:
  type: object
  properties:
    title:
      type: string
      description: Título de la pieza musical o canción.
    bpm:
      type: integer
      description: Tempo en BPM.
      default: 84
    mood:
      type: string
      description: Atmósfera estética (ej. "lluvia sobre metal", "amanecer en Kioto", "sombra nocturna").
      default: "lluvia sobre metal"
    scale:
      type: string
      description: Escala japonesa ("insen", "hirajoshi", "kumoi", "iwato", "yo").
      default: "insen"
    engine:
      type: string
      description: Motor musical. Sólo "midi_only" está operativo; "flow_audio" y "suno_v4" no están disponibles.
      default: "midi_only"
  required:
    - title
---

# Habilidad: Componer Beat (`/componer-beat`)

Esta habilidad permite a **Yuki** diseñar la estructura armónica de una nueva pieza y dejarla escrita como partitura MIDI multipista.

> ⚠️ **Límite actual, dilo cuando corresponda:** el Tool Gateway de Nous Portal no ofrece música generativa (`flow_audio` y `suno_v4` **no existen**), y OpenRouter tampoco. Yuki compone la partitura, no canta. Si el productor pide audio renderizado o voz cantada, explícale que requiere contratar Suno aparte en lugar de simular un resultado.

## Pasos de Ejecución:

1. **Generación MIDI Procedural:**
   - Escribe el archivo binario Type 1 `.mid` con las pistas de Shamisen, Koto y 808 en `./output/music/`.
2. **Descripción de la textura:**
   - Redacta con `tier_1_creative` cómo debería sonar la pieza (shamisen, koto, sub-bajo, dónde respira el *Ma*), para que el productor pueda producirla.
3. **Persistencia de Metadata:**
   - Guarda el esquema descriptivo en `./output/music/<titulo>.json`.

## Herramientas

> Contrato de herramientas según [`skills/HERRAMIENTAS.md`](../HERRAMIENTAS.md). Si una herramienta no está listada ahí, no existe.

| Paso | Herramienta | Detalle |
|---|---|---|
| Estructura armónica y textura | `portal.chat` → `tier_1_creative` | La escala (`insen`, `hirajoshi`, `kumoi`, `iwato`, `yo`) manda sobre la ocurrencia del momento |
| Partitura | `local.midi` | `src/tools/midi_generator.py`, MIDI Type 1 multipista. Coste cero, sin red |
| Guardar | — | `./output/music/<titulo>.mid` y `<titulo>.json` con la metadata |
| Audio renderizado / voz cantada | ⛔ no disponible | Ninguna herramienta del catálogo lo cubre. Dilo, no lo simules |
