---
name: componer-beat
description: Compone un esquema musical completo y sintetiza audio utilizando motores de difusión de frontera (Flow Audio / Suno v4) junto con partituras MIDI multipista procedurales en ./output/music/.
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
      description: Motor musical de frontera ("flow_audio", "suno_v4", "midi_only").
      default: "flow_audio"
  required:
    - title
---

# Habilidad: Componer Beat (`/componer-beat`)

Esta habilidad permite a **Yuki** diseñar la estructura armónica y renderizar el audio de una nueva pieza musical empleando tecnologías de frontera:
- **`flow_audio`**: Flow / DeepMind Audio (renderizado acústico de alta fidelidad para shamisen, koto y bajo 808).
- **`suno_v4`**: Producción completa multipista con lírica y voz cantada.
- **`midi_only`**: Generación exclusiva de archivo MIDI multipista procedural.

## Pasos de Ejecución:

1. **Generación MIDI Procedural:**
   - Escribe el archivo binario Type 1 `.mid` con las pistas de Shamisen, Koto y 808 en `./output/music/`.
2. **Síntesis con Motor de Frontera (Flow Audio / Suno):**
   - Renderiza el audio procesado `.mp3` capturando la textura acústica y las pausas (*Ma*).
3. **Persistencia de Metadata:**
   - Guarda el esquema descriptivo en `./output/music/<titulo>.json`.
