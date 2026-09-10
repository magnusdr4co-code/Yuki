# Virtualización de la instancia, limitadores y vías de mejora

**Fecha:** 2026-09-07 · **Instancia espejada:** `yuki-agent` (`yuki-prod`, e2-small,
`europe-southwest1-a`)

Este documento hace tres cosas: explica cómo levantar una réplica local de la
instancia de producción, deja por escrito los limitadores que estamos
encontrando —con su gravedad y su evidencia— y propone las vías de salida
ordenadas por lo que cada una acerca al sino del proyecto: una diva digital que
sostenga presencia y obra propia sin que un reinicio, una factura o una preview
retirada la dejen muda.

---

## 1. La réplica: virtualizar la instancia

La producción es una VM de Compute Engine que `deploy/gce-startup.sh` deja con
dos contenedores sobre la misma imagen y un disco persistente montado en los
dos. `deploy/virtual/docker-compose.virtual.yml` reproduce eso mismo en local:

| Elemento | Producción | Réplica local |
|---|---|---|
| Imagen | `europe-southwest1-docker.pkg.dev/yuki-prod/yuki/yuki-agent:latest` | `yuki-agent:virtual`, construida del repo |
| Procesos | `yuki-salon`, `yuki-daemon` | los mismos, mismos comandos |
| Datos | disco `yuki-data` en `/var/lib/yuki/data`, con `output/` dentro | volumen `yuki-virtual-data`, con `output/` como subruta |
| Memoria | e2-small: 2 GB para toda la máquina | 1 GB por contenedor |
| Secretos | Secret Manager, fichero de runtime borrado al arrancar | `.env` local si existe; opcional |
| Identidad | cuenta de servicio de la VM (ADC) | ninguna: sin Vertex, los medios son marcadores |

```bash
# Levantar la réplica completa
docker compose -f deploy/virtual/docker-compose.virtual.yml up --build

# Sólo el informe de capacidades y limitadores (arranca, escribe y termina)
docker compose -f deploy/virtual/docker-compose.virtual.yml --profile check \
  run --rm yuki-virtual-check
```

Lo que la réplica **no** reproduce, a propósito: Secret Manager, la identidad de
servicio y el crédito. Sin `VERTEX_PROJECT_ID` los medios devuelven marcadores
declarados como simulados, que es justo lo que hace falta para recorrer la ruta
completa sin gastar un céntimo. La variable `YUKI_VIRTUAL_INSTANCE=1` marca la
réplica para que el informe no la confunda con la máquina real.

## 2. El gemelo virtual: qué es real y qué es andamiaje

Antes había que entrar por IAP y leer logs para saber si una capacidad estaba
sirviendo de verdad. Ahora:

```bash
python3 cli.py virtualize                 # informe en Markdown
python3 cli.py virtualize --json          # el mismo estado, para máquinas
python3 scripts/virtualize_instance.py --fail-on-blocking   # para CI
```

Es determinista y no toca la red: mira configuración, entorno y disco, así que
la respuesta desde la VM, desde la réplica y desde CI son comparables tal cual.
No imprime secretos: de una credencial sólo dice si está puesta y si es un
marcador de `.env.example`.

## 3. Limitadores

Ordenados por gravedad. `L1` cambió de estado con este trabajo; el resto sigue
abierto y cada uno lleva su vía de salida en la sección 4.

| ID | Limitador | Gravedad | Estado |
|---|---|---|---|
| L2 | Sin proyecto Vertex declarado, medios y crédito inactivos | bloqueante | abierto (depende del entorno) |
| L1 | Producción multimedia interrumpible por reinicio | grave | **mitigado** |
| L3 | Clave de AI Studio en el entorno (factura fuera del crédito) | grave | abierto (depende del entorno) |
| L10 | API del Salón sin credencial | grave | abierto (depende del entorno) |
| L4 | El canto depende de una preview; hay respaldo instrumental propio | grave | **mitigado** en la imagen |
| L7 | Instancia única; copia diaria hecha, salida sujeta a bucket | grave | parcial |
| L8 | Vídeo facturado por segundo sin techo de gasto | grave | **mitigado** |
| L5 | Nous Portal sigue sin endpoint | moderado | abierto |
| L6 | Telegram sin conectar; búsqueda web sujeta a clave | moderado | parcial |
| L9 | Honcho dialéctico sin servicio remoto | moderado | abierto |

### L10 — La API del Salón respondía a cualquiera (nuevo, hallado en revisión)

`/api/chat`, `/api/memories` y `/api/honcho` no pedían nada. Quien alcanzara el
puerto 8080 podía gastar crédito, leer el perfil dialéctico del Productor y —lo
serio— **escribir en la memoria de Yuki**, que es lo único irremplazable del
proyecto: cada turno del chat queda registrado como interacción y altera su
estado vital.

Ahora hay dos frenos. Con `SALON_API_TOKEN` declarado, las rutas `/api` exigen
`Authorization: Bearer` (o `?token=`, que la propia página guarda), comparado en
tiempo constante; `/health` y la página quedan abiertas, porque una sonda que
pidiera credencial daría la instancia por muerta. Y un techo de 20 peticiones
cada 5 minutos por cliente que **actúa siempre**, haya token o no.

El comportamiento por defecto no cambia —sin token declarado las rutas siguen
abiertas, para no tumbar un despliegue en marcha—, pero el arranque lo avisa y
el gemelo virtual lo reporta como limitador abierto. Cerrarlo es declarar la
variable en la instancia y, mejor aún, restringir el puerto en el cortafuegos.

Con una excepción, y va en la otra dirección: `/api/outputs/<categoría>/<nombre>`
—que sirve el fichero de una obra, no su nombre— **exige credencial siempre**,
también cuando el resto de `/api` está abierto. Enumerar nombres es una fuga
menor; servir los bytes a quien alcance el puerto es otra cosa, y encenderla en
silencio cambiaría la exposición de una instancia en marcha. Sin token, responde
403 diciendo por qué, y el listado declara que la descarga está desactivada en
vez de callarlo.

### L4 — El canto dependía de una sola preview (mitigado)

`generate_music_flow` sólo producía audio real por `lyria-3-pro-preview`. Una
preview puede cambiar de nombre, de precio o retirarse sin aviso, y ese día Yuki
se quedaba sin música y sin plan B: `local.midi` produce partituras, no audio, y
un `.mid` no se escucha en Discord.

`src/tools/music_fallback.py` cierra el hueco con lo que ya hay en casa: la
partitura del generador MIDI, FluidSynth con un banco General MIDI y el ffmpeg
que la imagen ya traía (los dos primeros se añaden al `Dockerfile`). Si se le
pasa una voz, la mezcla por encima con la base cediendo 9 dB.

Dos límites que **se declaran en el propio resultado** y no se disimulan: no
canta —`sung: False`, y con voz es una letra *recitada*, no un canto—, y sin los
binarios devuelve `status: error` diciendo cuál falta, nunca un marcador. La
entrega por DM lleva la nota del paso, así que ni siquiera tras un reinicio
puede llamar «canción» a una maqueta instrumental.

Un tope de presupuesto **no** se esquiva por este camino: si el límite dice que
hoy no toca, renderizar igual sería desobedecerlo. Sólo un fallo del motor abre
el respaldo.

Lo que sigue abierto: el canto con letra sigue siendo territorio de Lyria. Para
no depender de una sola preview haría falta un segundo motor que cante.

### L8 — Vídeo sin techo de gasto (mitigado)

Cada llamada estimaba su coste, lo escribía en un log y nadie lo sumaba: no
había ningún sitio donde constara lo gastado hoy. Ahora `src/core/spend_budget.py`
lleva un libro diario en `data/spend_ledger.json` y **la comprobación ocurre antes
de llamar al proveedor**, que es la única posición útil: después, el segundo de
vídeo ya está facturado. Una orden que excede el límite se rechaza con la cifra
concreta —«llevas 96 de 120 y esta operación pide 8»— en vez de gastar y avisar
luego.

Los límites viven en `config.yaml` bajo `budget` y el día se cierra en la zona
horaria del planificador, no en UTC, para que el día del gasto sea el de las
rutinas. El texto se anota pero **no** se bloquea: dejar muda a Yuki por unos
tokens sería peor que el gasto que evita. La música se cuenta por pistas y
segundos y no se cotiza: no hay precio de referencia registrado en el repositorio
y no se inventa uno.

En la cola de trabajos, un tope de presupuesto **aplaza** el encargo en vez de
fallarlo: no gasta intento y el trabajo sigue reanudable, porque mañana el mismo
encargo cabe. Consulta: `python3 cli.py spend`.

Lo que sigue abierto: sólo la facturación de Google Cloud ve el gasto real, así
que la alerta de facturación del proyecto sigue siendo necesaria.

### L1 — Producción multimedia interrumpible (mitigado)

Era el más caro de los silenciosos: el encargo vivía en una `asyncio.Task` del
daemon, así que un despliegue a mitad se llevaba la canción y los clips ya
pagados, y el Productor sólo tenía un acuse de inicio que nadie iba a cumplir.

Ahora cada paso facturable —canción, cuatro clips, montaje, entrega— se escribe
en `data/media_jobs/` **antes** de gastar y se marca en cuanto tiene fichero
verificado. Al conectar el gateway, el adaptador reanuda lo que quedó a medias y
salta lo que ya existe: reanudar cuesta sólo lo que falta. Un paso hecho cuyo
fichero desapareció deja de contar como hecho; un paso que ha fallado tres veces
cierra el trabajo en vez de reintentarse para siempre; y un trabajo con pasos
pendientes ya no se cierra como terminado. Queda dependiendo de que el proceso
vuelva a arrancar: si la VM no vuelve, nadie reanuda nada (ver M1 y L7).

## 4. Mejoras propuestas

Ordenadas por lo que cada una desbloquea, no por dificultad. Las tres primeras
son las que separan «funciona cuando todo va bien» de «sostiene una presencia».

### M1 · Sacar la producción multimedia a un worker con reintento gestionado
*Cierra L1 del todo y parte de L7.* La cola ya es durable, pero quien la recorre
sigue siendo el daemon. Un Cloud Run Job disparado por Pub/Sub, leyendo el mismo
directorio de trabajos, aporta reintento gestionado, aislamiento del gateway de
Discord y la posibilidad de correr dos encargos a la vez sin arriesgar los 2 GB
de la e2-small. Coste: prácticamente nulo en inactividad.

### M2 · Presupuesto de gasto antes de generar — **hecho**
*Mitiga L8.* Implementado en `src/core/spend_budget.py` y cableado en el cliente
de medios de Vertex: vídeo, imagen, música y voz consultan el presupuesto antes
de llamar al proveedor, y el consumo de texto se anota con los `input_tokens` /
`output_tokens` que las pasarelas ya devolvían y nadie acumulaba. Ver la ficha de
L8. Del lado del repositorio hay además dos alertas —`GastoDiarioAnomalo`, que
compara con la media de la semana, y `PresupuestoDeVideoCasiAgotado`— en
`deploy/alertas-prometheus.yml`. Sigue pendiente lo que no depende del código:
**la alerta de facturación en el propio proyecto de Google Cloud**, que es la
única que salta cuando el gasto ocurre fuera de las rutas que el presupuesto
vigila.

### M3 · Copia de la memoria y del canon fuera de la instancia — **hecho, y comprobada**
*Mitiga L7 en cuanto se declare el bucket.* `src/tools/backup.py` empaqueta lo
irremplazable —base, Biblioteca, estado vital, perfil dialéctico, pairing,
trabajos, libro de gasto, bitácora y ritmos propios— tras la síntesis diaria,
que es el momento en que la memoria del día está completa.

Dos detalles deciden si una copia sirve: la base **no** se copia como fichero
(un `tar` de un SQLite en WAL restaura corrupto justo cuando hace falta) sino con
la API de instantánea, con el escritor en marcha; y la copia se abre y se pasa
por `integrity_check` antes de darla por buena. Sin `BACKUP_GCS_BUCKET` el
archivo queda en el mismo disco que el original y el resultado **lo dice** en vez
de sugerir que está a salvo.

**La restauración ya está probada, y no una vez.** Esto era lo que faltaba
cuando se escribió este documento, y era lo más importante: una copia sin
restaurar no está comprobada. Hoy hay tres niveles, de menos a más:

- `scripts/restore_drill.py` abre la última copia real y comprueba seis cosas,
  entre ellas que la base restaurada **tenga recuerdos dentro** —una base íntegra
  y vacía es un desastre con buena salud— y que el precinto de la bitácora siga
  en la cadena, que es lo único que detecta un corte por detrás.
- `--ciclo` recorre el circuito entero contra una instancia de juguete: fabricar,
  copiar, restaurar. Sin credenciales, así que corre en cada rama en la CI.
- Y **cada noche la propia instancia restaura la copia que acaba de hacer**. Si
  no sirve, el Productor lo sabe esa noche por DM. Una copia que existe y no
  sirve es peor que no tenerla: parece que estamos a salvo.

Comprobándolo aparecieron dos fallos que sólo se ven al restaurar de verdad: la
copia moría con `FileNotFoundError` una de cada treinta y cinco veces —los
ficheros `-wal`/`-shm` de SQLite seguían vivos al listar el directorio y ya no al
empaquetarlo— y, en una instancia con las rutas reubicadas, el estado vital, el
perfil dialéctico y el canon **no entraban en ninguna copia**.

Sigue faltando lo que no depende del código: **declarar `BACKUP_GCS_BUCKET` en
producción**, con los pasos concretos en
[`PENDIENTE_COPIA_FUERA_DE_LA_INSTANCIA.md`](PENDIENTE_COPIA_FUERA_DE_LA_INSTANCIA.md). Sin bucket, la copia queda en el mismo disco que el original y no
protege de perder el disco, que es el escenario de L7. Manual:
`python3 cli.py backup --ensayar`.

### M4 · Motor musical de respaldo — **hecho**
*Mitiga L4.* Construido con lo que ya había en casa, como se proponía: partitura
propia, FluidSynth y ffmpeg. Ver la ficha de L4. Queda pendiente lo que ningún
código resuelve: contratar un segundo motor que **cante**, para que el canto no
dependa de una sola preview, y archivar en Biblioteca el prompt y los parámetros
de cada pista para poder rehacerla igual.

### M5 · Extender el enrutado por tarea al resto del sistema
*Amplía lo hecho.* `provider_routing.routes` ya se aplica: las rutas del cron
(`feed_summary`, `social_formatting`, `dialectic_synthesis`) salen con su modelo,
su temperatura y su techo, en vez de que un resumen de feed cueste lo mismo que
una síntesis dialéctica. Falta llevarlo al arnés del Productor y a
`music_composition`, y publicar el coste por ruta cuando exista M2.

### M6 · Cerrar los canales simulados — *búsqueda hecha, quedan Telegram y Honcho*
*Cierra L5, L6 y L9.* Tres piezas del diagrama no servían tráfico real. La
búsqueda ya está: `src/tools/web_search.py` llama a Firecrawl de verdad cuando
hay `FIRECRAWL_API_KEY`, y sin ella devuelve pistas de introspección marcadas
`simulated: True` y **sin URL**, en vez de los dos titulares fijos con enlaces
inventados que la reflexión de las 03:00 citaba como corrientes del mundo. El
origen viaja en el propio prompt (`describe_origin`), así que Yuki no puede
atribuir al mundo algo que no salió de él.

Quedan Telegram —registra en log, no llega a ningún seguidor— y Honcho —perfil
en JSON local—. Cada uno admite dos salidas honestas: implementarlo o retirarlo
del diagrama; lo que no se sostiene es dejarlo dibujado como si funcionara.

### M7 · El Salón como panel de estado
*Reduce la dependencia del DM.* Hoy el único sitio donde se ve un encargo es la
DM del Productor. Exponer en el Salón el estado de los trabajos —pasos
verificados, fallos con su motivo, nada de promesas— permite comprobar una
producción sin abrir Discord y da al informe de virtualización un lugar donde
vivir en caliente.

## 5. Comprobación

```bash
make todo                                      # linter, suite, simulacro, circuito y humo
python3 cli.py backup --ensayar                # copia, y se restaura para darla por buena
python3 cli.py pulso                           # ¿corre el proceso, y además vive Yuki?
python3 cli.py spend                           # gasto de hoy contra el presupuesto
python3 cli.py virtualize                      # limitadores del entorno actual
python3 scripts/simulate_day.py                # su carácter, un día entero, antes de desplegarlo
docker compose -f deploy/virtual/docker-compose.virtual.yml config   # réplica válida
```

_(Aquí había un número de pruebas. Se ha quitado a propósito: una cifra en prosa
envejece a la semana siguiente y acaba siendo una mentira pequeña en un documento
que presume de no decirlas. `make todo` dice la de hoy.)_

Las pruebas de `tests/test_media_delivery_resume.py` reproducen el corte real:
generan la canción, fallan a mitad de los clips, arrancan un proceso nuevo que
sólo tiene el disco y comprueban que no se vuelve a pagar nada de lo ya
verificado.
