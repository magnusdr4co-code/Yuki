---
name: animar-portada
description: Anima una portada ya pintada o genera un teaser breve con audio nativo usando Gemini Omni Flash sobre Vertex AI, guardando el vídeo en ./output/video/. Herramienta cara, facturada por segundo de vídeo.
parameters:
  type: object
  properties:
    motion_concept:
      type: string
      description: Qué debe ocurrir en el plano; el movimiento, no la escena estática.
    image_path:
      type: string
      description: Ruta de la portada de partida (./output/art/...). Si se omite, el vídeo se genera desde el texto.
    duration_seconds:
      type: integer
      description: Duración en segundos. Entero de 3 a 10.
      default: 6
    aspect_ratio:
      type: string
      description: Proporción del vídeo ("16:9", "9:16", "1:1").
      default: "9:16"
  required:
    - motion_concept
---

# Habilidad: Animar Portada (`/animar-portada`)

Vídeo es lo más caro que hace Yuki: **Veo se factura por segundo**. Por eso el
criterio se dice antes, no después.

`src/tools/criterio_audiovisual.py` arma el guion **leyendo la obra**. Eran
cuatro planos escritos a mano —el muelle, el Salón, la intérprete, la salida— y
se usaban con cualquier obra delante: un encargo sobre otra canción rodaba
igualmente el muelle.

## 1. Los planos salen de la obra

Si la letra o el guion archivado traen secciones —`[Verse 1]`, `[Chorus]`,
`#### [Estrofa I]`—, cada plano toma una, en orden. Las marcas de clave sonora
(`[Tempo: 68 BPM, 4/4…]`) **no** son secciones: describen la pieza entera, y
rodarlas sería rodar un rótulo.

Si la obra no nombra secciones, se usa el guion de casa **y se dice que es el
de casa**. Presentarlo como una lectura de la obra sería atribuirse un trabajo
que no se hizo.

## 2. El número de planos lo manda el pedido

No la obra. De ese número se derivan los identificadores de paso del trabajo
durable, y si cambiaran entre arranques una reanudación daría por «no hecho» lo
que ya está pagado. La obra decide **qué** se rueda; el pedido, **cuánto**.

Cuando hay más secciones que planos, se avisa de lo que queda fuera. Cuando hay
menos, se repiten variando el punto de vista en vez de inventar escenas que la
obra no pide.

## 3. Ritmo de plano

- **8 s por plano**, que es lo que sirve el proveedor. No es una elección de
  montaje: es el material con el que hay que montar.
- **Cámara lenta y continua, sin cortes bruscos.** El montaje une; si cada
  plano se rueda como una pieza suelta, el ensamblado se nota.
- Cada plano sabe **su sitio en la secuencia** (`Shot 2 of 4`). Un plano que no
  sabe dónde va se corta solo.

## 4. Continuidad

La imagen archivada entra como primer fotograma cuando la hay: es lo que ata el
vídeo a la portada en vez de dejar dos obras que sólo comparten título.

## Herramientas

| Paso | Herramienta | Detalle |
|---|---|---|
| Criterio del guion | `src/tools/criterio_audiovisual.py` | Local, determinista sobre la misma obra |
| Vídeo | `portal.video` → Veo | **Facturado por segundo.** Reserva presupuesto antes de llamar |
| Montaje | `ffmpeg concat` | Sólo une clips ya verificados; no acepta rutas externas |
| Receta | `<fichero>.receta.json` | Prompt íntegro y parámetros, archivados con la obra |
