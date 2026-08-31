---
name: lanzamiento-single
description: Orquesta de forma integral y autónoma la producción completa de un sencillo (partitura MIDI .mid, portada .png, lírica Waka, nota de voz OGG y paquete para redes).
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
3. **Pintura de Portada (`portal.image`):**
   - Ilustra la carátula oficial en proporción `1:1` con iluminación Urushi / Kintsugi en `./output/art/`.
4. **Composición Lírica Waka:**
   - Escribe un poema tradicional de 31 moras conectado con el tema del sencillo.
5. **Síntesis Vocal (`portal.tts` + `local.ffmpeg`):**
   - Genera la presentación en audio OGG Opus con pausas respiratorias en `./output/voice/`.
6. **Empaquetado en el Workspace:**
   - Genera el archivo maestro de lanzamiento en `./output/posts/single_release_<titulo>.md` para su difusión a Telegram y Discord.

## Herramientas

> Contrato de herramientas según [`skills/HERRAMIENTAS.md`](../HERRAMIENTAS.md). Si una herramienta no está listada ahí, no existe.

Esta habilidad no llama a ninguna herramienta por su cuenta: **encadena las demás en orden y no continúa si un eslabón obligatorio falla.**

| # | Paso | Habilidad / herramienta | ¿Bloquea el lanzamiento si falla? |
|---|---|---|---|
| 1 | Micro-estación y concepto | `portal.chat` → `tier_2_nuclear` | Sí |
| 2 | Partitura | `/componer-beat` → `local.midi` | Sí |
| 3 | Portada | `/generar-portada` → `portal.image` | Sí |
| 4 | Lírica | `/escribir-waka` → `tier_1_creative` | Sí |
| 5 | Nota de voz | `/sintesis-vocal` → `portal.tts` + `local.ffmpeg` | No: el lanzamiento sale sin audio, dejándolo dicho |
| 6 | Paquete y difusión | `/publicar-redes` → adaptadores | Sí |
| 7 | Registro | `local.memory`, categoría `project` | Sí |

**Coste típico de un lanzamiento completo:** una imagen (≈ 0.04 USD), una nota de voz de ~40 s y tres llamadas de modelo, de las cuales sólo la primera es `tier_2_nuclear`. Cuando el productor pida variantes, genera una y pregunta antes de repetir.

⚠️ **Sin audio cantado.** El paquete entrega partitura, portada, lírica y nota de voz hablada. No hay pista renderizada: ninguna herramienta del catálogo la produce (ver `/componer-beat`).
