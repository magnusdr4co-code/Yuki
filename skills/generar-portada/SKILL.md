---
name: generar-portada
description: Pinta e ilustra portadas de sencillos o arte visual conceptual con Imagen sobre Vertex AI (o los modelos de FAL del Tool Gateway como respaldo) y guarda la imagen en ./output/art/.
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

Antes de pedir un solo píxel, Yuki **decide qué imagen es ésta**.
`src/tools/criterio_visual.py` produce el prompt que va al proveedor y el
resumen que se dice antes de gastar, y el resumen declara de dónde salió cada
decisión. No es prosa: si no se aplicara, esto sería una ficha bonita sobre una
constante.

## 1. Manda el concepto

Lo que el encargo nombre —encuadre, luz, materia— se respeta. Lo que calle, lo
decide el criterio, **y se dice que lo decidió el criterio**. El concepto
visual estaba escrito a mano en el adaptador («agua, hierro e invierno») con la
luz clavada en `urushi`, así que la portada de cualquier obra era la misma.

## 2. Encuadre

No es un ajuste técnico: es qué clase de imagen se está haciendo.

| Relación | Para qué | Lo nombra |
|---|---|---|
| `1:1` | Portada de sencillo, carátula, avatar | portada, carátula, single, cover |
| `4:5` | Cartel, publicación de feed, retrato | cartel, póster, feed, retrato |
| `16:9` | Escena, paisaje, cabecera, fondo | escena, paisaje, plano, panorámica |
| `9:16` | Vertical, historia | story, historia, vertical, reel |

Por defecto `1:1`, que es lo que una portada pide. Estaba clavado ahí para
todo, así que un cartel salía cuadrado.

## 3. Luz

Cada luz implica una hora y un material, no un filtro:

- **`industrial_rain`** — lluvia, neón sobre asfalto, puerto, metal, herrumbre,
  niebla, invierno. Reflejo frío sobre superficie mojada.
- **`urushi`** — laca negra, pan de oro, interior, vela, seda, penumbra. Luz
  cálida que se apoya en el material y no lo aplana.
- **`komorebi`** — bosque, bambú, sol de mañana, hoja, jardín. Luz filtrada,
  sombra moteada.

Gana **la que más presencia tenga en el texto**, no la primera que aparezca:
decidir por orden de diccionario sería decidir por azar del alfabeto.

## 4. Carga del encuadre

Lo que el criterio mide. Un concepto que enumera nueve elementos no produce una
imagen rica: produce una imagen llena, donde el punto focal se pierde y la
paleta minimalista deja de sostenerse. Por encima de **seis elementos** avisa,
antes de gastar.

Regla: **un punto focal claro, y el resto sirviéndolo**. Si dos elementos
compiten por la mirada, sobra uno.

## 5. Aire (*Ma*)

El vacío es material. El prompt lo pide explícitamente —*generous negative
space*— porque un proveedor que llene el encuadre por defecto se lleva por
delante lo que distingue esta obra de un montaje de existencias. Y prohíbe
rótulos: el texto sobre la imagen es cosa del montaje, no del generador.

## Herramientas

> Contrato según [`skills/HERRAMIENTAS.md`](../HERRAMIENTAS.md). Cuando esa
> tabla y el código se contradigan, **manda el código**.

| Paso | Herramienta | Detalle |
|---|---|---|
| Criterio visual | `src/tools/criterio_visual.py` | Local, sin red, determinista sobre el mismo concepto |
| Imagen | `portal.image` → `create_single_cover` | Reserva presupuesto antes de llamar. Encuadre y luz vienen del criterio |
| Marca de origen | `MediaMarker` | Artículo 50: se marca **antes** de entregar |
| Receta | `<fichero>.receta.json` | Prompt íntegro y parámetros, archivados con la obra |
