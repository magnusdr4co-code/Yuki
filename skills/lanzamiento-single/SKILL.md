---
name: lanzamiento-single
description: Orquesta de forma integral y autónoma la producción completa de un sencillo musical (composición de pista MIDI .mid, portada FAL .png, lírica Waka, nota de voz SSML y paquete para redes).
parameters:
  type: object
  properties:
    title:
      type: string
      description: Título del nuevo sencillo o pieza musical.
    concept:
      type: string
      description: Atmósfera o visión temática del lanzamiento (ej. "lluvia sobre metal", "cerezos en asfalto").
      default: "lluvia sobre metal y pan de oro"
    scale:
      type: string
      description: Escala japonesa ("insen", "hirajoshi", "kumoi", "iwato").
      default: "insen"
    bpm:
      type: integer
      description: Tempo en BPM.
      default: 82
  required:
    - title
---

# Habilidad: Lanzamiento de Sencillo (`/lanzamiento-single`)

Esta mega-habilidad orquesta el pipeline creativo completo de **Yuki**, integrando todas sus herramientas en una secuencia armónica.

## Pasos del Pipeline Autónomo:

1. **Alineación con la Micro-Estación (*Shichijūni-kō*):**
   - Extrae la micro-estación astronómica activa para determinar los kigo y texturas del lanzamiento.
2. **Composición y Generación MIDI:**
   - Construye la estructura armónica y escribe el archivo binario MIDI `.mid` en `./output/music/`.
3. **Pintura de Portada con Nous Portal (FAL.ai):**
   - Ilustra la carátula oficial en proporción `1:1` con iluminación Urushi / Kintsugi en `./output/art/`.
4. **Composición Lírica Waka:**
   - Escribe un poema tradicional de 31 moras conectado con el tema del sencillo.
5. **Síntesis Vocal SSML (Nous TTS):**
   - Genera la presentación en audio OGG Opus con pausas respiratorias en `./output/voice/`.
6. **Empaquetado en el Workspace:**
   - Genera el archivo maestro de lanzamiento en `./output/posts/single_release_<titulo>.md` para su difusión a Telegram y Discord.
