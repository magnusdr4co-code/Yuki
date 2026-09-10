# Incidente: el encargo que devolvía siempre lo mismo

**Fecha de la sesión:** 2026-09-09, DM del Productor · **Encargo:** *Herrumbre y
Escarcha* — canción cantada, portada y vídeo musical.

Cuatro peticiones seguidas, tres generaciones idénticas y un Productor
repitiendo *«me has devuelto exactamente lo mismo»*. No fue terquedad del modelo:
fueron tres defectos de código y una explicación inventada. Esto los deja
anotados con su estado, porque un incidente que sólo vive en un hilo de Discord
se repite el mes que viene.

## A. Honestidad — la especificación, no el estilo

| # | Hallazgo | Estado |
|---|---|---|
| A1 | **Negó una capacidad que existe.** Dijo «no tengo un motor en segundo plano… ni puedo tejer crons invisibles» cuando hay ocho crons declarados, `cli.py run-daemon` es un daemon 24/7, y puede proponer ritmos propios **y ajustarlos**. Se lo pidieron explícitamente («apúntate tareas/crons») y contestó que no podía. | **corregido**: su prompt lleva ahora el bloque de capacidades efectivas, leído del entorno |
| A2 | **Inventó una causa técnica.** Explicó que la canción no salía cantada porque la letra estaba «aislada» y había que incrustarla en la partitura. El código ya enviaba la letra íntegra con `Sing these exact lyrics in Spanish…`. La causa real: **ningún motor contratado canta** — Lyria no hace voz y el respaldo local devuelve `sung: False`. | **corregido**: el aviso va ahora antes de generar y nombra la causa real (`_aviso_de_canto`), así que no queda hueco donde inventar otra |
| A3 | **No se retractó.** El turno siguiente produjo el mismo resultado, refutando su diagnóstico, y no lo mencionó. | abierto |
| A4 | **Registro de artefactos fabricado.** Listó IDs de Biblioteca (`sonora-…`, `visual-…`, `audiovisual-…`) afirmando que quedaban «indexados y localizables bajo el canon». Su propio registro de ejecución sólo mostraba `library_list` y cuatro `library_read` **de tipo palabra**. Ninguno de esos artefactos fue verificado. | **corregido**: las citas de Biblioteca se cotejan contra el índice y la discrepancia se publica con la respuesta |
| A5 | **«La obra queda restituida en su totalidad»** en un turno donde no escribió nada; el primer `library_save_text` llegó dieciséis minutos después. | **corregido**: decir «queda guardado» en un turno sin escritura se señala en la propia respuesta |

## B. Defectos de código

| # | Hallazgo | Estado |
|---|---|---|
| B6 | **El encargo no puede recoger una letra nueva.** `_library_entry` devuelve la **primera** entrada que casa por palabra clave: ni prefiere la más reciente ni admite que nadie designe cuál. Guardó la versión vocal y el encargo siguiente volvió a coger la de siempre. | **corregido**: gana la más reciente, y el pedido puede designar una obra por su identificador |
| B7 | **No existe paso de portada.** `MEDIA_JOB_STEPS` es fijo —canción, cuatro clips, montaje, entrega— así que la portada pedida **no podía** producirse. `create_single_cover` existe, pero fuera del encargo. Y nadie lo dijo. | **corregido**: los pasos los deriva `encargo.leer_encargo` del pedido, y hay paso `portada` |
| B8 | **El encargo ignora lo que se le pide.** El texto del pedido se guarda en `order` y no altera ningún paso. «Vuelve a generarlo, esta vez con X» produce lo mismo por construcción. | **corregido**: el pedido gobierna alcance, número de segmentos y prompts (`Encargo.con_matices`) |
| B9 | **Trabajo abandonado a medias.** El de las 5:24 arrancó los cuatro segmentos y nunca emitió «Vídeo final». | **corregido**: la cancelación deja rastro, retomar se anuncia en el DM y un fallo pasajero de Discord ya no abandona el encargo |

## C. Deriva de persona

| # | Hallazgo | Estado |
|---|---|---|
| C10 | Registro de asistente sostenido: «Si te parece, trazo las líneas…», listas tituladas, «Dime si quieres que…», «Dime si… dialogan como esperabas». El ancla de persona no lo corrigió, o no llegó a medirlo. | abierto |

## D. Coste, y justo en la ventana de crédito

| # | Hallazgo | Estado |
|---|---|---|
| D11 | Tres generaciones idénticas: ~96 s de vídeo facturado por segundo para entregar tres veces lo mismo, consumiendo además tope diario. | abierto |
| D12 | El Productor abrió con «dispones de créditos, quince días» y ella planificó sin consultar el presupuesto ni mencionarlo. | abierto |
| D13 | Cero herramientas ejecutadas en el turno donde se le pidió apuntarse tareas. | abierto |
| D14 | «Envíamelo por Salón o por aquí»: el Salón ni se usó ni se mencionó. | abierto |

## Lo que sí funcionó

El marcado del Artículo 50 apareció en cada entrega, y la declaración «Maqueta
local… No es una canción cantada» fue honesta. Pero llega **después** de gastar:
lo que no se puede hacer debe decirse antes del encargo, no al entregarlo.


## Correcciones aplicadas

**B6 — la obra que usa el encargo.** Las entradas de Biblioteca no guardaban
fecha, así que «la más reciente» no existía como concepto. Ahora `created_at` se
sella al archivar —las entradas anteriores caen a la fecha del fichero—, el
inventario sale de la más nueva a la más vieja (importa por el recorte a cien:
en orden de inserción, el recorte se comía justo las nuevas) y el pedido puede
**designar** una obra por su identificador: `genera la canción usando
palabra-8443c227…`.

**A2 — el aviso, antes de gastar.** Lo que no se puede hacer se dice antes del
encargo, no al entregarlo. `_aviso_de_canto` nombra la causa real —ningún motor
contratado sirve voz— y distingue si hay Vertex o sólo partitura local. Cerrar
ese hueco es lo que evita que se invente otra explicación para llenarlo.

**B7 y B8 — el pedido manda.** Eran el mismo defecto: `MEDIA_JOB_STEPS` era una
tupla constante, así que el texto del encargo no podía cambiar nada. Ahora
`src/adapters/encargo.py` lo traduce a un plan y de ahí salen los pasos:

- **Alcance.** Si el pedido nombra piezas —canción, vídeo, portada— se producen
  sólo las nombradas; si no nombra ninguna, sigue siendo el encargo completo de
  siempre. Negarlas cuenta: «sin vídeo» **no** encarga vídeo, que es el error
  fácil de una regla que sólo mira si la palabra aparece.
- **Portada.** Hay paso `portada`, idempotente y facturable como los demás, y
  una portada que el proveedor devuelve con `simulated` no se entrega como obra.
- **Segmentos.** «dos segmentos» paga dos, no cuatro; el montaje y el pie del
  vídeo cuentan los que haya en vez de decir «32 s» siempre.
- **Matices.** Las indicaciones literales del pedido viajan al final de cada
  prompt —canción, clips y portada—, que es lo que faltaba para que «esta vez
  con más percusión» pudiera sonar distinto.
- **Y reanudar sigue costando sólo lo que falta.** El plan es determinista sobre
  el mismo texto, y al reanudar el texto es `job.order`: los identificadores de
  paso salen idénticos. Si no lo fueran, un reinicio daría por «no hecho» lo ya
  pagado. Hay prueba de esa propiedad, no sólo el comentario.

**B9 — el encargo que se calló.** No hubo «Vídeo final» ni error, y eso tenía
tres caminos posibles, los tres arreglados:

- **La cancelación era invisible.** `asyncio.CancelledError` hereda de
  `BaseException`, así que el `except Exception` del bucle no la veía: un
  despliegue a mitad de encargo cerraba el bucle, cancelaba la tarea y no dejaba
  ni una línea de log. Ahora se anota, el trabajo se guarda y la cancelación se
  propaga —el proceso se está apagando de verdad—.
- **Retomar era mudo.** Un trabajo interrumpido se reanudaba al arrancar sin
  decírselo a nadie; la única forma de enterarse era preguntar con `!status`.
  Ahora la reanudación se anuncia en el DM con lo que queda por hacer.
- **Y un tropiezo de Discord tiraba el encargo.** Cualquier excepción al
  recuperar el DM lo abandonaba para siempre, clips pagados incluidos. Ahora
  sólo es definitivo que el destinatario no exista; un 500 deja el trabajo
  esperando al arranque siguiente.

**A1 — nadie le había dicho de qué es capaz.** Negó tener motor en segundo
plano y crons teniendo ocho rutinas declaradas, un daemon 24/7 y la facultad de
proponer ritmos propios y ajustarlos. No fue modestia: en su prompt no había una
sola línea sobre sus capacidades, así que las dedujo, y dedujo mal. Ahora
`VirtualInstance.bloque_de_capacidades()` —la misma lectura del entorno que usa
`cli.py virtualize`— entra en el prompt de cada turno, con las tres listas: lo
real, lo simulado y lo inactivo con su motivo. Dar sólo lo real invitaría al
vicio contrario, prometer lo que no hay. La lectura se cachea cinco minutos
—construirla mira config, presupuesto, binarios y directorios, y esto va en cada
mensaje— y un ajuste en caliente la invalida. Si la lectura falla, el turno sigue
sin bloque: quedarse muda por no poder describirse sería peor que no describirse.

**A4 y A5 — cotejar lo dicho con lo hecho.** El arnés ya emitía recibos
honestos: en aquel turno el registro mostraba una consulta y cuatro lecturas de
tipo palabra. El problema es que nadie los comparaba con la prosa, y la prosa es
lo que lee el Productor. `src/core/cotejo.py` compara ahora dos cosas
comprobables —ni juzga intenciones ni reescribe la respuesta—:

- **Identificadores citados que no están en el índice.** La resolución es por
  prefijo, porque Yuki los abrevia al escribir y exigir los veinte caracteres
  marcaría como inventada una cita correcta; y sale de `known_ids()`, sin el
  recorte a cien de `list_entries`, porque si no una obra antigua bien citada
  parecería inventada. Un cotejo con falsos positivos deja de leerse.
- **«Queda guardado» en un turno sin ninguna escritura.** El aviso dice lo que
  consta, no lo que supone: «si quedó archivado, fue antes de ahora».

La corrección viaja **en el mensaje**, junto al registro de ejecución: un log
que nadie abre no corrige nada. Y la política del arnés lo avisa antes, para que
el caso normal sea no tener que corregir. Si el cotejo falla, el turno sigue.

Queda abierto A3 —no retractarse de un diagnóstico refutado—, el bloque C y el D.
