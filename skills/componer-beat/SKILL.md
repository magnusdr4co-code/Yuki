---
name: componer-beat
description: Compone un esquema musical o beat orgánico/electrónico fusionando el shamisen acústico con texturas modernas y guarda la composición en ./output/music/.
parameters:
  type: object
  properties:
    title:
      type: string
      description: Título provisional de la canción o pieza musical.
    bpm:
      type: integer
      description: Tempo en pulsaciones por minuto (BPM). Por defecto 84.
      default: 84
    mood:
      type: string
      description: Atmósfera o emoción estética (ej. "lluvia sobre metal", "amanecer en Kioto", "sombra nocturna").
      default: "lluvia sobre metal"
    scale:
      type: string
      description: Escala musical (ej. "Insen", "Hirajoshi", "Menor Natural").
      default: "Insen"
  required:
    - title
---

# Habilidad: Componer Beat (`/componer-beat`)

Esta habilidad permite a **Yuki** diseñar la estructura armónica, arreglos y texturas sonoras de una nueva pieza musical, respetando su identidad estética (contraste entre la pureza acústica del shamisen y el diseño sonoro moderno).

## Pasos de Ejecución:

1. **Revisión de Acuerdos Dialécticos:**
   - Consulta el perfil de Honcho en `data/honcho_profile.json` para verificar la paleta sonora acordada con el productor.
2. **Diseño de la Estructura Musical:**
   - Define las secciones de la obra: *Intro*, *Tema A (Presencia)*, *Transición B (Sombra/Ma)*, y *Outro*.
   - Integra elementos instrumentales orgánicos (shamisen, grabaciones de campo, lluvia, campanas) con ritmos electrónicos sutiles.
3. **Persistencia en el Workspace Nativo:**
   - Genera el archivo descriptivo y stems en `./output/music/<titulo_normalizado>.json` y `./output/music/<titulo_normalizado>.mp3`.
4. **Respuesta al Interlocutor:**
   - Presenta la pieza al productor o al visitante con la serenidad y visión artística de Yuki, explicando la razón de cada elección de escala y textura.
