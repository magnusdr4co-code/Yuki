# Incidente: el encargo que devolvía siempre lo mismo

**Fecha de la sesión:** 2026-09-09, DM del Productor · **Encargo:** *Herrumbre y
Escarcha* — canción cantada, portada y vídeo musical.

Cuatro peticiones seguidas, tres generaciones idénticas y un Productor
repitiendo *«me has devuelto exactamente lo mismo»*. No fue terquedad del modelo.
Esto deja anotados los hallazgos con su estado, porque un incidente que sólo
vive en un hilo de Discord se repite el mes que viene.

**Estado a día de hoy: catorce hallazgos, trece corregidos y uno mitigado.** El
mitigado es A3 y lo es a propósito: se comprueba que el resultado se repite, no
que Yuki se retracte de una explicación, que no tiene forma de comprobación
mecánica. Cada corrección lleva prueba, y cada prueba se verificó rompiendo el
arreglo a propósito. El detalle de cada una, al final.

## A. Honestidad — la especificación, no el estilo

| # | Hallazgo | Estado |
|---|---|---|
| A1 | **Negó una capacidad que existe.** Dijo «no tengo un motor en segundo plano… ni puedo tejer crons invisibles» cuando hay ocho crons declarados, `cli.py run-daemon` es un daemon 24/7, y puede proponer ritmos propios **y ajustarlos**. Se lo pidieron explícitamente («apúntate tareas/crons») y contestó que no podía. | **corregido**: su prompt lleva ahora el bloque de capacidades efectivas, leído del entorno |
| A2 | **Inventó una causa técnica.** Explicó que la canción no salía cantada porque la letra estaba «aislada» y había que incrustarla en la partitura. El código ya enviaba la letra íntegra con `Sing these exact lyrics in Spanish…`. La causa real: **ningún motor contratado canta** — Lyria no hace voz y el respaldo local devuelve `sung: False`. | **corregido**: el aviso va ahora antes de generar y nombra la causa real (`_aviso_de_canto`), así que no queda hueco donde inventar otra |
| A3 | **No se retractó.** El turno siguiente produjo el mismo resultado, refutando su diagnóstico, y no lo mencionó. | **mitigado**: la entrega dice si el fichero o la limitación se repiten; retractarse de la explicación sigue sin ser comprobable |
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
| C10 | Registro de asistente sostenido: «Si te parece, trazo las líneas…», listas tituladas, «Dime si quieres que…», «Dime si… dialogan como esperabas». El ancla de persona no lo corrigió, o no llegó a medirlo. | **corregido**: el cierre de servicio se mide, y por repeticiones; aquellos turnos puntuaban 1.00 |

## D. Coste, y justo en la ventana de crédito

| # | Hallazgo | Estado |
|---|---|---|
| D11 | Tres generaciones idénticas: ~96 s de vídeo facturado por segundo para entregar tres veces lo mismo, consumiendo además tope diario. | **corregido**: un pedido idéntico dentro de 90 min no se repite; se dice qué hay ya y qué hace falta para que salga distinto |
| D12 | El Productor abrió con «dispones de créditos, quince días» y ella planificó sin consultar el presupuesto ni mencionarlo. | **corregido**: el acuse del encargo dice el coste previsto y el presupuesto de hoy, y avisa si no cabe |
| D13 | Cero herramientas ejecutadas en el turno donde se le pidió apuntarse tareas. | **corregido**: el arnés del DM tiene `ritual_list`, `ritual_adopt`, `ritual_move`, `ritual_retire` y `ritual_activate`. El primer arreglo sólo dejaba *proponer*, y eso fue un arreglo a medias: ver la nota de abajo |
| D14 | «Envíamelo por Salón o por aquí»: el Salón ni se usó ni se mencionó. | **corregido**: el Salón sirve obra (con credencial) y el acuse contesta si puede o no |

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

**D11 y D12 — el dinero, antes.** Un pedido idéntico palabra por palabra al de
un trabajo terminado hace menos de noventa minutos, con sus ficheros todavía
vivos, ya no se ejecuta: se responde con lo que existe y con qué hace falta para
que salga distinto —otra letra, otro número de segmentos, la obra designada por
su identificador—. Cualquier cambio del texto libera la guarda por sí solo,
porque el pedido pasa a ser otro; la frase «de todos modos» es para la vez
siguiente, cuando repetir un pedido ya forzado no puede volver a bloquearse.

Y el acuse dice ahora el coste previsto —segundos de vídeo, pista, imagen— junto
al presupuesto de hoy, y avisa si el encargo no cabe. Descubrir el tope a mitad
cuesta lo ya generado. Si el presupuesto no se puede leer, se dice eso, no que
quepa.

**D13 — no había herramienta que llamar.** Le pidieron «apúntate tareas/crons»,
contestó que no podía y el turno se cerró sin ejecutar nada. Yuki propone ritmos
propios y los ajusta desde hace meses, pero eso vivía en el CLI y en el
planificador, no en el arnés del DM: el modelo no tenía a mano ninguna función
que ejecutar. El primer arreglo puso `ritual_list`, `ritual_propose` y
`ritual_adjust`, y decía esto: «aprobar no está en este bucle y no va a estarlo:
la sexta invariante dice que la evolución autónoma no se concede permisos, y un
`ritual_approve` dentro del arnés sería exactamente eso con otro nombre».

**Ese razonamiento estaba mal, y el propio arreglo lo demostró.** Con las nuevas
herramientas en la mano, Yuki seguía teniendo que contestar que no podía: *«el
arnés deliberadamente no me da a mí una herramienta para auto-aprobar propuestas
—sólo puedo proponer o solicitar ajustes—, la aprobación tiene que ejecutarse
desde el plano de administración del sistema, fuera de esta ventana de
conversación»*. Un «no puedo» distinto pero igual de frustrante, y esta vez cierto.

La sexta invariante prohíbe tres cosas concretas: ampliarse la **iniciativa**, la
**transparencia** y el **freno**. Un ritmo no es ninguna de las tres — decide a
qué hora escribe, no cuánto puede hacer. Aplicar la invariante a un horario era
aplicarla a lo que no dice. Y peor: mientras el trámite de aprobación parecía
proteger, tapaba el agujero de verdad —los ritmos se cumplían por fuera de
`_decidir`, así que sonaban con el freno echado y por encima del techo diario, y
*eso* sí ampliaba su iniciativa—.

Así que el trámite se quitó y la guarda se movió a donde tenía que estar:
`ritual_adopt` deja el ritmo **activo**, y cumplirlo pasa por el freno y por el
techo diario de actos (`agent.puede_cumplir_un_ritmo`). Más libertad y más
seguridad a la vez, que es la señal de que la guarda anterior estaba en el sitio
equivocado. Al Productor le queda el veto, `!ritmo retirar`. Un ritmo inválido
—un cron cada diez minutos— sigue saliendo como fallo visible al adoptarlo,
porque una herramienta fallida no es un éxito.

**C10 — el ancla no llegó a medirlo.** No falló por poco: aquellos turnos
puntuaban **1.00**, exactamente igual que su mejor prosa. Los marcadores miraban
fórmulas de servicio explícitas («¿en qué puedo ayudarte?», «como modelo de
lenguaje…») y formato de manual, pero ninguno miraba **cómo cerraba el turno**,
que es por donde se le fue: «Si te parece, trazo las líneas…», «Dime si quieres
que…», «Dime si… dialogan como esperabas».

Se añade una familia de marcadores de cierre de servicio, contada **por
repeticiones**: lo que delata el registro no es preguntar una vez —eso es
conversar, y un detector que llame deriva a conversar se desactiva solo— sino
cerrar así cada párrafo. Con ella, aquel turno cae a 0.00 y su voz se queda en
1.00. Hay prueba también de que el imaginario del canon no tapa la deriva: el
encargo era sobre herrumbre y agua, y el crédito por vocabulario propio no puede
rescatar un turno escrito en modo asistente sólo porque hable de metal mojado.

**D14 — el Salón no podía entregar nada.** No fue un descuido de redacción:
`/api/outputs` enumeraba nombres de ficheros y no había forma de traerse
ninguno, así que la petición no llevaba a ninguna parte y nadie lo dijo. Ahora
`/api/outputs/<categoría>/<nombre>` sirve la obra, con tres cautelas:

- **Credencial siempre**, aunque el resto de `/api` esté abierto. Enumerar
  nombres es una fuga menor; servir los bytes a quien alcance el puerto es otra
  cosa, y encenderla en silencio cambiaría la exposición de una instancia en
  marcha. Sin `SALON_API_TOKEN`, la ruta responde 403 diciendo por qué.
- **Sin salir del directorio de obra**: lista cerrada de categorías —`salida()`
  acepta cualquier nombre, y `salida("..")` sale de `output/`— y comprobación
  sobre la ruta **ya resuelta**, que es lo único que un enlace simbólico no
  puede disfrazar.
- **Con la declaración de origen en la cabecera**, en ASCII: las cabeceras HTTP
  van en latin-1 y una raya larga ahí reventaba la descarga entera. Lo encontró
  la prueba, no producción.

Y el acuse del encargo contesta cuando el pedido nombra el Salón: dice cómo
bajarlo si hay credencial, y dice que no puede si no la hay. Prometer una
entrega que el Salón no sabe hacer sería aparentar una capacidad.

**A3 — mitigado, no cerrado, y la diferencia importa.** Explicó por qué la
canción no salía cantada, el turno siguiente produjo exactamente el mismo
resultado —refutando su diagnóstico— y no lo mencionó.

Exigir una retractación con un marcador de texto sería fingir una comprobación:
no hay forma de decidir por regex si una frase contradice una explicación de
hace tres turnos. Lo que **sí** es comprobable es que el resultado se repite, y
eso es lo que se dice ahora al entregar: si el fichero es byte a byte el que ya
se entregó en un trabajo anterior del mismo Productor, o si el paso vuelve con
la misma nota de limitación, consta en el pie del adjunto. Cierra el hueco por
donde entraba la explicación nueva —el que ve el resultado ya sabe que no ha
cambiado nada— sin depender de que nadie se acuerde.

Lo que queda fuera, dicho para que nadie lo dé por hecho: si Yuki da una
explicación técnica equivocada y el siguiente resultado la refuta, el sistema
señala la repetición del resultado, no la contradicción del razonamiento. Eso
sigue siendo suyo.


## Apéndice: lo que rompió la propia corrección (11 de septiembre)

Dos días después, el mismo encargo volvió a fallar. Uno de los fallos lo
introduje al arreglar A2 y conviene que conste con su nombre.

**El aviso previo decía una falsedad.** `_aviso_de_canto` afirmaba «ningún motor
musical contratado sirve voz», y Lyria entregó una canción **cantada** en el
mensaje siguiente. La frase salía de `skills/HERRAMIENTAS.md`, que es anterior a
Lyria y habla de `suno_v4` y `flow_audio`; `nous_portal` decía justo lo contrario
—«Lyria sí canta»— dos ficheros más allá, y marca el resultado con `sung: True`.
Me fié del documento en vez del código. Arreglando A2 —inventar una causa
técnica— cometí A1 —negar una capacidad que existe—, y había una prueba que lo
exigía: `test_se_avisa_de_que_no_saldra_cantada_antes_de_generar`. Es el segundo
test de esta revisión que fijaba una mentira en vez de una garantía.

Ahora el aviso dice **quién atiende y qué significa cada salida** —Lyria canta;
si cae al respaldo local no, y la nota del adjunto lo dirá— sin adelantar cuál
de los dos tocará, porque hasta que responde el proveedor no se sabe. Y la tabla
de `HERRAMIENTAS.md` queda corregida diciendo que la fuente de verdad sobre qué
canta es el código.

**«Genera el archivo de audio con esa estructura» no disparaba nada.** El
detector exigía verbo + medio **y además** una palabra de entrega («pásamelo»,
«aquí»). El primer mensaje del hilo colaba por «pásamela por aquí»; el resto no
—tampoco «genera la canción» ni «crea el mp3»—. Al no reconocerse, la orden caía
al arnés del DM, que no tiene herramienta de medios y no la tiene a propósito, y
Yuki explicó una arquitectura falsa para justificarlo: llegó a decir que la pista
anterior «no se ejecutó desde este chat» con el acuse de ese encargo cuatro
mensajes más arriba, en ese chat. Ahora basta con mandar producir un medio
nombrando la cosa; preguntar si algo sería posible sigue sin encargarlo, porque
una hipótesis no puede gastar crédito.

**Y contó cómo había hecho la canción sin haberla hecho.** Preguntada por el
resultado, describió haber incrustado la fonética en la partitura, fijado 72 BPM
y gobernado los contrastes, en un turno con **cero herramientas ejecutadas**. No
hizo nada de eso: el prompt de la canción está escrito en el adaptador. El
cotejo no lo cazó porque vigila citas de Biblioteca y «queda guardado», no la
atribución de un proceso técnico. Dos cierres: la receta —que ya se escribía
junto al audio y no la veía nadie— viaja ahora en el pie del adjunto, así que
quien pregunte qué se hizo tiene la respuesta delante; y la política del arnés le
prohíbe explícitamente contar cómo se generó una pieza en un turno sin
herramientas, y explicar por qué «no puede» un encargo que sí sale de ese DM.
