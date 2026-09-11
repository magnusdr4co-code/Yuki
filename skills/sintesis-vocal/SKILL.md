---
name: sintesis-vocal
description: Sintetiza notas de voz en OGG Opus con la entonación cálida y las pausas deliberadas de Yuki usando Gemini TTS sobre Vertex AI (o el TTS del Tool Gateway como respaldo), guardando el audio en ./output/voice/.
parameters:
  type: object
  properties:
    text:
      type: string
      description: Texto o mensaje que Yuki expresará en audio.
    cadence_pause_ms:
      type: integer
      description: Duración de las micro-pausas en milisegundos para reflejar el lenguaje prestado.
      default: 350
  required:
    - text
---

# Habilidad: Síntesis Vocal (`/sintesis-vocal`)

Antes de hablar, Yuki **decide cómo se dice esto**.
`src/tools/criterio_vocal.py` produce la indicación de estilo que viaja con el
texto. Era una constante —«calidez contenida y pausas deliberadas»— con
cualquier texto delante: una despedida de dos líneas y un párrafo de explicación
salían con la misma respiración, y una pregunta salía afirmada.

## 1. El registro sale de la hora

Su voz no es la misma a las tres de la mañana que al mediodía, y eso no es un
efecto: es quién habla a esa hora.

| Fase | Registro |
|---|---|
| `deep_rest` | Muy baja y cercana, casi un susurro; el mundo duerme |
| `night` | Grave y lenta, con silencios largos entre frases |
| `atelier` | Atenta y presente, articulación clara sin prisa |
| `dawn` | Despierta pero contenida, como quien no quiere romper la mañana |

## 2. La puntuación es la partitura

Lo que el criterio mide. Un párrafo sin un solo signo no tiene dónde respirar:
el sintetizador lo recorre de un tirón y suena a lectura de prospecto. Por
debajo de **1,5 pausas por cada cien caracteres**, avisa.

Si el texto trae preguntas o exclamaciones, el matiz entra en el estilo en vez
de esperar que el motor lo adivine.

## 3. Duración

≈13 caracteres por segundo de habla pausada — una estimación declarada, para
avisar de un texto largo, no para cuadrar un doblaje. Por encima de **45
segundos** deja de ser una nota de voz y nadie la oye entera; entonces se dice,
antes de gastar, que en voz se factura por carácter.

## 4. Un solo sitio decide

Había dos capas fabricando indicaciones de estilo, y la de fuera ganaba: el
criterio no llegaba a aplicarse nunca. Ahora la capa de arriba sólo aporta lo
que sabe —la hora y la cadencia del proveedor— y el criterio decide.

## Herramientas

| Paso | Herramienta | Detalle |
|---|---|---|
| Criterio vocal | `src/tools/criterio_vocal.py` | Local, determinista sobre el mismo texto |
| Voz | `portal.tts` → Gemini TTS | OGG Opus nativo, sin transcodificar. La cadencia viaja en lenguaje natural, no en SSML |
| Marca de origen | `MediaMarker` | Artículo 50: se marca **antes** de entregar |
| Receta | `<fichero>.receta.json` | Texto, voz, estilo, fase y duración estimada |
