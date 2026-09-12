# Ejecución real del DM de producción

El nombre Hermes y `active_role=producer` no otorgan capacidades por sí mismos.
El adaptador comprueba ID y pairing persistente antes de habilitar `producer_tools`.
Los canales públicos no reciben herramientas. El modelo actual es configurado en Vertex.

`ProducerHarness` usa llamadas nativas `tools`/`tool_calls` de la pasarela OpenAI-compatible,
devuelve resultados con el mismo `tool_call_id` y repite hasta una respuesta final
(máximo ocho rondas y dieciséis operaciones totales). Si el presupuesto se agota,
ejecuta un cierre sin herramientas a partir de la evidencia ya obtenida: no expone un
aviso técnico ni deja trabajo en segundo plano. No hay shell ni autoedición general.
El contexto reciente del usuario se recupera de SQLite, con límites; las promesas
anteriores no son prueba de ejecución. Cada respuesta lleva recibos deterministas.
Un fallo o límite devuelve resultado parcial; no se promete trabajo futuro inexistente.
Model Armor inspecciona el prompt, argumentos y respuesta. La inferencia sale del event loop.

Herramientas: `library_inventory`, `library_list`, `library_save_text`, `library_read`,
`library_set_status`, `terminal_run`, `runtime_config_get`, `runtime_config_set`,
`runtime_config_rollback`, `ritual_list`, `ritual_adopt`, `ritual_move`, `ritual_retire`
y `ritual_activate`. Las de ritmos existen porque le pidieron «apúntate tareas y crons» y
el turno terminó con cero herramientas ejecutadas y un «no puedo» falso: no había ninguna
que llamar. Cuando las hubo sólo podía **proponer**, y tenía que explicar que la
aprobación pasaba «fuera de esta ventana de conversación» — cierto, y ése era el problema.
Ahora **adopta**: un ritmo queda activo al crearlo, porque decidir a qué hora escribe no
es concederse un permiso. Lo que la acota no es el clic de nadie, sino la lista cerrada de
acciones, el techo de disparos, el techo de ritmos, el freno y el techo diario de actos
propios. El canon es tipo/estado: sonora, visual, palabra, audiovisual;
semilla, en-desarrollo, terminado. Los originales no se borran. Imports idempotentes
por hash, límite 100 MB por archivo, sin enlaces fuera de output. Simulaciones conocidas
se omiten. JSON de producción permanece en origen; no se etiqueta como obra.

`output/Biblioteca/CANON.md`, `INDEX.md` e `index.json` viven en el volumen persistente
de output. El estado inicial es en-desarrollo: ni la publicación ni un éxito de API
certifican que una obra esté terminada. Guardar otro texto crea una versión por hash.

El flujo específico del Salón archiva presentación y letra y avisa al DM al terminar.
Qué obra produce sale de la petición: `crea el canal "<servidor>" "<canal>" "<obra>"` —el
tercer entrecomillado nombra la obra y gobierna la letra, el título y el imaginario de la
partitura, los tres conceptos visuales y el prompt del vídeo—. Sin él se produce la de
siempre, que es el comportamiento anterior; antes todo eso estaba escrito a mano sobre un
título concreto, así que abrir un Salón para otra cosa producía igualmente aquélla. El
acuse dice qué obra y a cuánto sale —una pista, tres imágenes y 6 s de vídeo— con el
presupuesto de hoy, porque este camino gastaba sin mencionar ninguna de las dos cosas.

Las órdenes del Productor emparejado que solicitan crear y entregar música, audio o vídeo
se interceptan **antes** del `ProducerHarness`: no dependen de que el LLM decida invocar
herramientas. El adaptador confirma el inicio, recupera los recursos de Biblioteca,
genera la pista y los clips, los concatena cuando procede y adjunta únicamente ficheros
verificados al DM. El arnés textual continúa reservado para Biblioteca, terminal y
configuración.

El reconocimiento tolera órdenes naturales breves como “procede con la canción y el
vídeo”; no exige que el Productor repita “pásamelos”. El log del daemon registra la ruta
elegida (`canal_produccion` y `media_entrega`) sin registrar contenido ni secretos. Un
fallo de un proveedor multimedia se comunica como fallo real de ese trabajo, no como una
afirmación de que Yuki carece de herramientas. Los trabajos multimedia son durables: cada
paso facturable —canción, cada clip, montaje y entrega— se persiste en `data/media_jobs/`
antes de gastar y se marca al tener fichero verificado, así que un reinicio reanuda desde
el último paso y no vuelve a pagar lo hecho. Un paso cuyo fichero desapareció deja de
contar como hecho; uno que falló tres veces cierra el trabajo nombrando el fallo, y un
trabajo con pasos pendientes no se cierra como terminado. `!status` informa de los
trabajos reanudables. El gasto de medios se reserva contra el presupuesto diario antes
de llamar al proveedor: un tope alcanzado aplaza el paso con la cifra concreta, sin gastar
intento ni cerrar el encargo. Si Lyria no sirve la pista, el respaldo local entrega una
maqueta instrumental declarada como tal: la entrega nunca llama canción a lo que no canta.

Y cuando una entrega repite lo anterior, lo dice en el propio adjunto: si el
fichero es byte a byte el ya entregado en un trabajo previo, o si el paso vuelve
con la misma nota de limitación, el pie lo nombra. Es la mitad comprobable de un
fallo que no lo es entero —Yuki explicó una vez por qué la canción no salía
cantada, el turno siguiente salió igual y no lo mencionó—: el sistema puede
señalar que el resultado no ha cambiado; retractarse de la explicación sigue
siendo suyo.

El acuse inicial dice el coste previsto —segundos de vídeo, pista, imagen— y el
presupuesto de hoy, y avisa si el encargo no cabe: descubrir el tope a mitad
cuesta lo ya generado. Y un pedido idéntico palabra por palabra al de un trabajo
terminado hace menos de noventa minutos, con sus ficheros todavía vivos, no se
ejecuta: se responde con lo que ya existe y con qué haría falta para que saliera
distinto. Cualquier cambio del texto libera la guarda, porque el pedido pasa a
ser otro.

Qué pasos tiene el encargo lo decide el pedido, no una constante. `src/adapters/encargo.py`
lee el texto y arma el plan: si nombra piezas —canción, portada, vídeo— se producen sólo
ésas, y si no nombra ninguna sale el encargo completo de siempre; «sin vídeo» no encarga
vídeo; «dos segmentos» paga dos y no cuatro; y las indicaciones literales del pedido viajan
al final de cada prompt, que es lo que faltaba para que «esta vez con más percusión»
pudiera sonar distinto. La portada tiene paso propio y una que el proveedor devuelva como
`simulated` no se entrega como obra. El acuse inicial dice qué se va a producir, antes de
gastar, para que lo que no vaya a salir se sepa entonces y no por su ausencia al final. El
plan es determinista sobre el mismo texto, y al reanudar el texto es el del trabajo
guardado: los identificadores de paso salen idénticos y un reinicio sigue costando sólo lo
que falta.

Y la respuesta se coteja con lo ejecutado antes de salir. Si el texto cita un
identificador de Biblioteca que no está en el índice, o dice que algo «queda
guardado» en un turno donde no se llamó a ninguna herramienta de escritura, la
discrepancia se publica junto a la respuesta, encima del registro de ejecución:
los recibos ya eran honestos, pero lo que lee el Productor es la prosa. La
resolución de identificadores es por prefijo y sobre el índice completo, no
sobre las cien entradas que devuelve `library_list`; un cotejo con falsos
positivos deja de leerse a los tres avisos. La política del turno lo advierte
antes, para que el caso normal sea no tener nada que corregir.

## Ritmos y libre albedrío

`!albedrio` muestra el carácter de la iniciativa —espontaneidad, audacia,
constancia—, el umbral efectivo con el aburrimiento acumulado, los actos del día
frente a su techo y qué tipo de acto le está obteniendo respuesta. `!albedrio
<clave> <valor>` ajusta espontaneidad, audacia, constancia, umbral, energía
mínima y acciones por día; pasa por el mismo overlay atómico que el resto y tiene
efecto en el siguiente ciclo. La evolución autónoma no puede tocar nada de esto:
nadie debería poder concederse más iniciativa a sí mismo.

`!ritmos` lista los cron del proyecto y los ritmos propios que Yuki adoptó. Los
adopta ella tras la síntesis diaria, fundando el horario en su diario de agencia,
y avisa por DM con el ritmo ya sonando. Al Productor le queda **el veto**: `!ritmo
retirar <id> [motivo]` lo quita y `!ritmo mover <id> "<cron>"` lo cambia de hora.
`!ritmo aprobar|rechazar` sobrevive sólo para las propuestas que se quedaron
esperando de cuando hacía falta aprobar; sin eso quedarían atrapadas en un trámite
retirado. Un ritmo sólo puede escribir, contemplar, explorar o monologar —componer
y pintar gastan crédito y siguen exigiendo orden explícita—, y al cumplirse pasa
por el freno y por el techo diario de actos: adoptar ritmos decide cuándo actúa,
nunca cuántas veces. Detalle completo en `docs/LIBRE_ALBEDRIO.md`.

## Terminal y configuración

`terminal_run` sólo acepta argv sin shell: `pwd`, `git status|diff|log`, `pytest` y
`python -m pytest`, además de lectura limitada (`ls`, `find`, `rg`, `sed`) bajo las rutas
de código y Biblioteca. Tiene 30 segundos, 12 KB de salida y redacción de patrones de
secreto. Niega `data/`, `.git`, `deploy/`, archivos `.env`, red, escritura, instalación,
procesos persistentes y cualquier sintaxis de shell.

La configuración vive como overlay atómico en `data/runtime_overrides.json`; no reescribe
`config.yaml`. Por DM emparejado sólo permite temperatura, `max_tokens` y los modelos
Gemini 3.6/3.7/3.8 Flash definidos en la allowlist. Cada cambio registra actor, motivo y
marca temporal; `runtime_config_rollback` vuelve al valor base. No permite modificar
secretos, permisos/IAM, pairing, Discord, código, red ni infraestructura.

La evolución autónoma se revisa tras la síntesis diaria. Sólo puede ajustar temperatura,
con crecimiento ya registrado (confianza ≥0.80), al menos cinco interacciones y un salto
máximo de 0.15. No recibe terminal ni las herramientas del Productor.
