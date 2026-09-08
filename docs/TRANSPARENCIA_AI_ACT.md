# Transparencia: el Artículo 50 aplicado a Yuki

**Estado:** implementado · **Norma:** Reglamento (UE) de Inteligencia Artificial,
artículo 50 · **Aplicable desde:** 2 de agosto de 2026 · **Periodo transitorio
para el marcado de sistemas anteriores:** hasta el 2 de diciembre de 2026

Yuki no es un caso dudoso: es un sistema que interactúa directamente con
personas físicas en Discord y que genera texto, imagen, audio y vídeo
sintéticos, operado desde `europe-southwest1`. Hasta esta revisión no declaraba
su naturaleza ante nadie ni marcaba un solo fichero. Las sanciones del
incumplimiento llegan a 15 M€ o el 3 % del volumen de negocio mundial.

## Las dos obligaciones, y cómo se cumplen

### 1. Informar a quien habla con ella

> Quien interactúa con el sistema debe saber que interactúa con una IA, **antes
> o al principio** de la interacción.

`src/core/transparency.py` lo resuelve con un registro persistente de a quién se
le ha dicho y cuándo (`data/transparency.json`), y la declaración se **antepone**
a la respuesta —no va en un pie de página que nadie lee—. Se repite cada
`reminder_days` (30 por defecto): decirlo una vez en la vida no cumple con quien
vuelve seis meses después. Cada canal cuenta por separado, y ante un registro
ilegible se vuelve a declarar: declarar de más no hace daño, declarar de menos
incumple.

**Sobre la excepción de «resulta obvio».** La norma exime cuando la condición de
IA es evidente para una persona razonablemente informada y atenta. Yuki es un
personaje construido para ser creíble; su credibilidad es justamente lo que
anula esa excepción, así que aquí no se invoca.

Los canales internos —cron, su propia voluntad— no reciben declaración: no hay
persona a la que informar.

### 2. Marcar lo que genera, de forma legible por máquina

Dos capas, porque ninguna basta sola: los metadatos incrustados viajan con el
fichero pero se pierden al recomprimir; el manifiesto lateral sobrevive a eso
pero se separa al compartir.

| Formato | Capa incrustada | Cómo |
|---|---|---|
| PNG | chunk `tEXt` tras IHDR | Python puro, sin dependencias |
| MP3 / MP4 / OGG / M4A / WAV | etiquetas de contenedor | `ffmpeg -c copy`, sin recodificar: no se degrada la obra |
| Todos | manifiesto lateral `<fichero>.c2pa.json` | siempre |

El manifiesto tiene la forma de C2PA 2.4: acción `c2pa.created` con
`digitalSourceType` = `…/digitalsourcetype/trainedAlgorithmicMedia` —el término
IPTC para «creado por una IA»— y una aserción `stds.schema-org.CreativeWork` con
creador, modelo y prompt.

**Honestidad sobre el alcance:** el manifiesto **no va firmado**. C2PA de verdad
exige una cadena de certificados que este proyecto no tiene, así que esto es una
declaración verificable, no una prueba criptográfica; el propio manifiesto lo
dice (`"signed": false`). Aparentar una garantía que no se da sería exactamente
el vicio que este proyecto lleva corrigiendo desde el principio.

### Dónde se aplica

El marcado ocurre **al escribir el fichero**, no al entregarlo: en
`vertex_media.py` (imagen, música, vídeo, voz) y en el respaldo musical local.
Y hay una segunda puerta en la entrega por Discord, que marca lo que llegue sin
marca y añade la nota visible «🤖 Contenido generado por IA» al adjunto. Esa
redundancia es deliberada: un camino de salida nuevo, o una obra archivada antes
de que existiera el marcado, no puede escaparse.

## Comprobación

```bash
python3 cli.py transparency          # qué se ha declarado y qué está marcado
python3 cli.py transparency --marcar # marca retroactivamente lo pendiente
python3 cli.py transparency --json
python3 cli.py virtualize            # L11 aparece si algo queda sin marcar
```

## Lo que deliberadamente no se puede hacer

`transparency` **no** está en la lista de ajustes que el Productor cambia por DM
ni al alcance de la evolución autónoma. Puede editarse en `config.yaml`, como
cualquier decisión de despliegue, pero no es un dial de carácter: un personaje no
debería poder decidir dejar de decir lo que es, y desactivarlo aparece como
limitador **bloqueante** en el gemelo virtual.

## Lo que queda fuera del alcance actual

- **Firma criptográfica C2PA.** Requiere certificado y cadena de confianza. El
  camino está preparado: el manifiesto ya tiene la forma correcta.
- **Marca de agua imperceptible** (tipo SynthID) en imagen y audio. Los
  metadatos se pierden con una recompresión; una marca en la señal no.
- **Marcado del texto** publicado en canales. La norma lo exige para texto
  destinado a informar al público sobre asuntos de interés general; la obra
  lírica de Yuki no encaja ahí, pero la declaración de la sección 1 la cubre.
