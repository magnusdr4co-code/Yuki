# 🪞 Autocaracterización: con qué cara y qué voz se presenta

Yuki decide su propia imagen. No la recibe del Productor: lee `SOUL.md`, extrae
los rasgos que ya están escritos ahí y los convierte en artefactos concretos
—cuatro avatares, una manera de hablar, una paleta y una tipografía—. **Sin que
nadie lo apruebe**, igual que adopta un ritmo: elegir cómo se presenta es suyo, y
lo que la acota son los límites de siempre —el freno, el presupuesto y la marca
del Artículo 50—, no el visto bueno de nadie.

Este documento dice **qué decide, quién lo dispara y qué se hace de verdad con
cada decisión**. Lo último importa más que lo demás: durante un año el módulo
existió sin que nadie lo llamara mientras su skill prometía que corría solo, y la
forma de no repetir ese fallo es escribir, al lado de cada decisión, quién la
consume.

## Qué decide

| Decisión | Qué es | Quién la usa hoy |
|---|---|---|
| **Cuatro avatares** | `atelier`, `kage`, `seasonal`, `intimate`; prompts derivados del alma y de la micro-estación | **Nadie todavía.** Se generan, se marcan y quedan en `output/art/`. Ni el Salón ni Discord los muestran |
| **Manera de hablar** | Cadencia, pausas, prosodia por fase, susurro coreano | La voz real del proveedor va a la síntesis (ver abajo). Los perfiles prosódicos, todavía no |
| **Paleta y tipografía** | 15 colores derivados de sus contrastes sensoriales, tres familias tipográficas | **Nadie todavía.** El Salón no pinta con ella |
| **Iconografía** | Símbolos permitidos y prohibidos | **Nadie todavía** |

Que tres de las cinco filas digan «nadie todavía» no es un olvido: es lo que hay,
y está escrito aquí para que nadie lo confunda con una capacidad en uso.

## Quién lo dispara

| Cuándo | Qué |
|---|---|
| Cron `seasonal_self_characterization`, 04:00 | Mira si cambió el sekki; si cambió, se redefine entera |
| Ritual del eco, 06:30 | Micro-ajuste diario: prosodia e iluminación según cómo amaneció |
| `python3 cli.py identidad` | Lo vigente, sin gastar nada |
| `python3 cli.py identidad --regenerar` | El ritual completo, ahora. **Gasta crédito de imagen** |

Corre a diario y casi ningún día actúa: el sekki cambia cada dos semanas.
Comprobarlo cada día en vez de calendarizar veinticuatro fechas es lo que hace
que una instancia apagada durante el cambio se recaracterice al volver.

## La voz: qué se elige de verdad

Aquí hubo un hueco que conviene que conste. La calibración elegía entre tres
identificadores —`yuki_serene_alto`, `yuki_contemplative_mezzo`,
`yuki_night_contralto`— que **no existen en ningún proveedor**: vienen de la
documentación antigua, y `vertex_media.py` ya lo decía en un comentario. La
síntesis real usaba `Aoede` pasara lo que pasara, así que la CLI anunciaba «Voz:
yuki_night_contralto» y Yuki hablaba con otra.

Ahora cada candidata declara **qué voz del proveedor usa**, el manifiesto guarda
las dos —el nombre con el que ella la piensa y el que recibe el sintetizador— y
la elegida llega a la síntesis. Hoy las tres apuntan a `Aoede`, que es la única
que este proyecto ha probado: lo que cambia entre ellas no es el timbre sino la
cadencia. Está dicho así, con su nombre, en vez de fingir un catálogo.

Añadir una voz real es añadir su nombre del catálogo de Gemini TTS en
`VOICE_CANDIDATES` y comprobarlo contra el proveedor. Mientras no se compruebe,
no se declara.

## Qué cuesta

Hasta cuatro imágenes por cambio de micro-estación —una cada dos semanas—, unos
**0,16 USD**; hasta ocho (~0,32 USD) si las cuatro fallan y se reintentan. Se
reservan antes de llamar al proveedor contra el límite diario de imágenes, como
cualquier otro medio. Si el presupuesto está agotado o el freno puesto, no gasta:
anota el motivo y no inventa avatares.

Un avatar cuenta **sólo cuando su fichero está en el disco**. Un `status:
success` sin fichero se degrada a error; un marcador simulado viaja declarado; y
el manifiesto lleva el recuento de cuántos llegaron a existir, para que nadie
confunda cuatro marcadores con cuatro retratos.

## Lo que se sabe de la primera ejecución real

20 de septiembre de 2026, contra Vertex, en la instancia: **3 de 4 avatares**,
25 s, `gemini-2.5-flash-image`. `kage` falló con «Gemini Image no devolvió datos
de imagen» —un 200 sin parte de imagen— y esa ejecución demostró lo que no se
podía saber con dobles: el fallo quedó anotado con su motivo, no se inventó un
avatar, y la reserva se devolvió, así que lo que no se generó no se cobró.

Destapó tres cosas, ya corregidas: el remate del log contaba las variantes
pedidas y no las existentes; la proporción viajaba sólo a la rama de Imagen, así
que el avatar estacional se pedía en 16:9, salía cuadrado y se anotaba como 16:9
—también en la receta, que existe para poder rehacer la obra—; y un fallo del
momento perdía la variante hasta el siguiente cambio de estación.

## Lo que falta, dicho sin adornos

1. **Los avatares no entran en ninguna copia.** El manifiesto sí, pero apunta a
   `output/art/`, y la copia sólo se lleva `output/Biblioteca`. Perder el disco
   deja el manifiesto señalando cuatro ficheros pagados que ya no están.
2. **La paleta, la tipografía y la iconografía no las usa nadie.** Se deciden y
   se guardan.
3. **Los prompts de avatar llevan la biografía escrita a mano** —edad, origen,
   pelo— en vez de leerla de `SOUL.md`. Si el canon cambia allí, estos cuatro
   prompts no se enteran.
4. **`_shift_hue` no desplaza el matiz**: hace una rotación de canales
   aproximada. Los colores salen, pero no son el tono que su nombre promete.

## Dónde mirar

- Código: `src/core/self_characterization.py`, tarea en `src/scheduler/tasks.py`.
- Estado: `data/identity_manifest.json` —declarado en el inventario, en la copia—
  y los avatares en `output/art/`.
- Sondas: `yuki_identidad_al_dia` (-1 nunca · 0 caducada · 1 al día) y
  `yuki_identidad_avatares_reales`; alerta `IdentidadCaducada` a los cuatro días.
- La habilidad: [`skills/autocaracterizarse/SKILL.md`](../skills/autocaracterizarse/SKILL.md).
