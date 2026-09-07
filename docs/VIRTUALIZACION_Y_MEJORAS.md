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
| L4 | Sin motor de música propio: la canción depende de una preview | grave | abierto |
| L7 | Instancia única, sin réplica ni copia del disco | grave | abierto |
| L8 | Vídeo facturado por segundo sin techo de gasto | grave | **mitigado** |
| L5 | Nous Portal sigue sin endpoint | moderado | abierto |
| L6 | Telegram y búsqueda web simulados | moderado | abierto |
| L9 | Honcho dialéctico sin servicio remoto | moderado | abierto |

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
L8. Queda pendiente el complemento que no depende del código: la alerta de
facturación en el proyecto.

### M3 · Copia de la memoria y del canon fuera de la instancia
*Cierra L7.* Hoy `yuki_memory.db`, la Biblioteca y los trabajos viven en un solo
disco, en una sola zona. Una zona caída se lleva la memoria de Yuki, que es lo
único verdaderamente irremplazable del proyecto: los medios se regeneran, los
recuerdos no. Propuesta: snapshot programado del disco **y** exportación de
`output/Biblioteca` y de la base a Cloud Storage al terminar la síntesis diaria,
con una restauración probada de verdad al menos una vez.

### M4 · Motor musical de respaldo
*Cierra L4.* La canción cantada depende por completo de `lyria-3-pro-preview`;
una preview puede cambiar o retirarse sin aviso, y ese día Yuki se queda sin
música real y sin plan B. Propuesta: declarar un segundo motor o construir el
respaldo con lo que ya hay en casa —partitura de `midi_generator`, voz de Gemini
TTS, mezcla con el ffmpeg que la imagen ya trae—, y archivar en Biblioteca el
prompt y los parámetros de cada pista para poder rehacerla igual.

### M5 · Extender el enrutado por tarea al resto del sistema
*Amplía lo hecho.* `provider_routing.routes` ya se aplica: las rutas del cron
(`feed_summary`, `social_formatting`, `dialectic_synthesis`) salen con su modelo,
su temperatura y su techo, en vez de que un resumen de feed cueste lo mismo que
una síntesis dialéctica. Falta llevarlo al arnés del Productor y a
`music_composition`, y publicar el coste por ruta cuando exista M2.

### M6 · Cerrar los canales simulados
*Cierra L5, L6 y L9.* Tres piezas del diagrama no sirven tráfico real: Telegram
registra en log, Firecrawl devuelve una lista fija —de modo que las «tendencias»
de la reflexión nocturna no vienen del mundo— y Honcho vive en un JSON local.
Cada una admite dos salidas honestas: implementarla o retirarla del diagrama.
Lo que no se sostiene es dejarlas dibujadas como si funcionaran. Orden sugerido:
Firecrawl (afecta al contenido que Yuki publica), Telegram (afecta al alcance),
Honcho (afecta a la continuidad del vínculo, hoy cubierta por SQLite).

### M7 · El Salón como panel de estado
*Reduce la dependencia del DM.* Hoy el único sitio donde se ve un encargo es la
DM del Productor. Exponer en el Salón el estado de los trabajos —pasos
verificados, fallos con su motivo, nada de promesas— permite comprobar una
producción sin abrir Discord y da al informe de virtualización un lugar donde
vivir en caliente.

## 5. Comprobación

```bash
python3 -m pytest tests -q                     # 277 pruebas
python3 cli.py spend                           # gasto de hoy contra el presupuesto
python3 cli.py virtualize                      # limitadores del entorno actual
docker compose -f deploy/virtual/docker-compose.virtual.yml config   # réplica válida
```

Las pruebas de `tests/test_media_delivery_resume.py` reproducen el corte real:
generan la canción, fallan a mitad de los clips, arrancan un proceso nuevo que
sólo tiene el disco y comprueban que no se vuelve a pagar nada de lo ya
verificado.
