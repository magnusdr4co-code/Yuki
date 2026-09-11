---
name: componer-beat
description: Decide cómo se compone una pieza antes de encargarla —estructura, tempo, escala, encaje de la letra y recursos líricos— y escribe la partitura MIDI multipista en ./output/music/. El criterio vive en src/tools/criterio_musical.py y gobierna el prompt real.
parameters:
  type: object
  properties:
    title:
      type: string
      description: Título de la pieza musical o canción.
    lyrics_id:
      type: string
      description: Identificador de Biblioteca de la letra sobre la que se compone (`palabra-…`). Si se da, el criterio se lee de ella.
    bpm:
      type: integer
      description: Tempo en BPM. Sólo se usa si ni la letra ni el criterio lo deciden.
      default: 84
    mood:
      type: string
      description: Atmósfera estética (ej. "lluvia sobre metal", "amanecer en Kioto", "sombra nocturna").
      default: "lluvia sobre metal"
    scale:
      type: string
      description: Escala japonesa ("insen", "hirajoshi", "kumoi", "iwato", "yo").
      default: "insen"
  required:
    - title
---

# Habilidad: Componer Beat (`/componer-beat`)

Antes de encargar un solo segundo de audio, Yuki **decide cómo se compone esto**.
No es un adorno de prosa: `src/tools/criterio_musical.py` produce el prompt que
va al motor y el resumen que se dice en el DM, y el resumen declara de dónde
salió cada decisión.

> **Qué canta y qué no, a día de hoy.** `lyria-3-pro-preview` por Vertex **sí
> canta**: el resultado viene marcado con `sung: True`. El respaldo local
> (`music_fallback`) **no** canta —es una maqueta instrumental, o la letra
> recitada sobre música— y devuelve `sung: False`. Hasta que el proveedor
> responde no se sabe cuál de los dos atendió, así que **no adelantes el
> resultado**: di quién atiende y qué significa cada salida. Una versión
> anterior de este documento afirmaba que la música «se limita a `local.midi`»;
> era cierto antes de Lyria y dejó de serlo, y el 11 de septiembre costó
> decirle al Productor que su canción saldría instrumental el día que salió
> cantada. **La fuente de verdad sobre qué canta es el código, no esta ficha.**

---

## 1. Manda la letra

Si la letra trae sus propias marcas —`[Tempo: 68 BPM]`, `4/4`, `Key: D minor`,
`Insen scale`, `[Verse 1]`, `[Chorus]`— **se respetan**. Son decisiones de quien
la escribió. Pisarlas con un valor por defecto es exactamente lo que hacía la
constante que había antes: 72 BPM con cualquier letra delante, incluida una que
pedía 68.

Lo que la letra calla, lo decide el criterio. Y lo que decide el criterio **se
dice que lo decidió el criterio**: el resumen distingue «de la letra» de «por
criterio», para que el Productor sepa qué eligió Yuki y qué se dedujo.

## 2. Estructura

El orden de secciones sale de la letra cuando las nombra. Si no las nombra, la
forma corta que sostiene una pieza de 90 segundos:

| Sección | Qué hace | Cuidado |
|---|---|---|
| **Intro** (4 cc.) | Silencio activo, *Ma*. Shamisen desnudo, un golpe de bachi cada dos compases | Sin voz. Es lo que limpia el espectro antes de que entre |
| **Estrofa** | Presenta. Voz grave, cercana, articulación lenta | Aquí no se grita: sin contención previa, el clímax no tiene de dónde subir |
| **Estribillo** | Abre. Entra el subgrave, la voz sube al pecho | Es el ancla: si la letra tiene una frase que repetir, es ésta |
| **Puente** | Rompe. Suspende el pulso, deja la voz desnuda | El contraste vale más que añadir instrumentos |
| **Outro** | Resuelve. Vuelta a la cuerda sola, decaimiento largo | Un final cortado en seco desperdicia la resonancia |

Una pieza no necesita las cinco. Necesita **al menos un contraste**: si todo
está al mismo nivel de energía, la voz suena plana por buena que sea.

## 3. Tempo

El BPM no es gusto: es la relación entre las sílabas de un verso y los compases
que tiene para caberlo.

- **Verso largo (≈14 sílabas o más) → baja el pulso** (~64 BPM). Si no, la voz
  trota para alcanzar el siguiente acorde. Eso es lo que el Productor oyó y
  describió como «se apresuraba el poema».
- **Verso corto (≈8 o menos) → sube** (~84 BPM), o la pieza se arrastra.
- **Arte menor, 9–13 sílabas → pulso medio** (~72 BPM).

El rango operativo es **58–96 BPM**. Fuera de ahí, la paleta —shamisen, koto,
sub-bajo— deja de sostenerse: por debajo se deshilacha, por encima el bachi se
convierte en percusión de baile.

## 4. Encaje de la letra en la estructura

Esto es lo que más se nota y lo que menos se mira. El criterio **mide la letra**:

- **Dispersión silábica.** Cuenta las sílabas de cada verso y calcula cuánto se
  separan de la media. Por encima de **3.5 de desviación**, avisa: el motor
  acelerará los versos largos. Un verso de nueve sílabas seguido de otro de
  diecisiete no caben iguales en el mismo número de compases, y la voz resuelve
  ese problema corriendo.
- **La cuenta es aproximada y se declara como tal.** Agrupa vocales y une
  diptongos; no resuelve sinalefa entre palabras ni hiatos acentuados. Sirve
  para comparar unos versos con otros, no para escandir poesía.

Regla práctica: **dos compases por verso**, y que el final de la palabra tenga
dónde apoyarse. Si un verso no cabe en dos compases, no se acelera: se parte o
se recorta.

## 5. Recursos líricos

- **Rima.** No es adorno: en el canto le dice al oído dónde cae el peso del
  compás. El criterio detecta terminaciones asonantes que vuelven y avisa
  cuando no hay ninguna —sin rima, la voz queda a la deriva—. Asonante basta;
  consonante forzada suena a ripio.
- **Acento fijo.** Versos de longitud pareja con el acento en el mismo lugar
  dan cadencia uniforme. Es la diferencia entre cantar y recitar deprisa.
- **Quiebre declarado.** Si la letra pide susurro, voz rota o desgarro, el
  criterio lo lleva al registro vocal del encargo en vez de esperar que el
  motor lo adivine.
- **Contención antes del clímax.** Una pieza que empieza desgarrada no tiene a
  dónde ir. El peso se gana callando primero.
- **Ma.** El silencio es material, no ausencia. Cuatro compases sin voz al
  principio y una suspensión antes del último verso hacen más que un
  instrumento añadido.

---

## Pasos de ejecución

1. **Leer el criterio.** `criterio_musical.leer_criterio(letra, titulo)` sobre la
   letra archivada. Devuelve tempo, compás, tonalidad, escala, secciones,
   registro vocal y las observaciones sobre métrica y rima.
2. **Decirlo antes de gastar.** `plan.resumen()` va al DM **antes** de llamar al
   proveedor. Si la métrica va a atropellar la voz, el Productor lo sabe
   entonces y no al escuchar el adjunto.
3. **Encargar.** `plan.prompt(letra)` construye el encargo: indicaciones
   primero, la letra íntegra al final —un proveedor que recorte por longitud
   debe perder el relleno de estilo antes que el texto que hay que cantar—.
4. **Partitura MIDI.** `local.midi` escribe el `.mid` multipista. Coste cero,
   sin red.
5. **Receta.** Cada fichero generado deja su `<fichero>.receta.json` con el
   prompt íntegro y los parámetros, y viaja con la obra a Biblioteca. Es lo que
   permite rehacer una pieza que salió bien —y saber en qué se diferencia de la
   que salió mal—.

## Herramientas

> Contrato de herramientas según [`skills/HERRAMIENTAS.md`](../HERRAMIENTAS.md).
> Cuando esa tabla y el código se contradigan, **manda el código**.

| Paso | Herramienta | Detalle |
|---|---|---|
| Criterio de composición | `src/tools/criterio_musical.py` | Local, sin red, determinista sobre la misma letra |
| Canción cantada | `portal.music` → `lyria-3-pro-preview` | Canta. Reserva presupuesto antes de llamar; marca el resultado con `sung: True` |
| Respaldo si Lyria no responde | `music_fallback` | Maqueta instrumental o letra recitada. `sung: False`, y la entrega lo dice |
| Partitura | `local.midi` | `src/tools/midi_generator.py`, MIDI Type 1 multipista. Coste cero |
| Guardar | — | `./output/music/<titulo>.mid`, `<titulo>.json` y `<fichero>.receta.json` |
