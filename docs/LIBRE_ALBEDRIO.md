# El libre albedrío de Yuki

Cómo decide actuar por su cuenta, cómo se afina su carácter y cómo puede pedir
un ritmo propio. Sustituye a lo que antes vivía disperso entre `spark.py` y
media docena de umbrales incrustados en el código.

---

## 1. Lo que había, y por qué no bastaba

`La Chispa` modelaba bien el **deseo**: impulsos con intensidad que decae como
un anhelo que se enfría, una cola de voluntad, un coste energético por acto. Lo
que no había era **agencia**:

| Síntoma | Causa |
|---|---|
| El carácter no se podía afinar | `intensidad < 0.3`, costes y umbrales incrustados en Python |
| Días enteros sin una sola iniciativa | Los impulsos sólo nacían en el eco de las 06:30, por coincidencia de palabras: una mañana sin decir «pintar» era un día sin pintura |
| Siempre hacía lo mismo | La decisión era determinista: mismo estado, misma elección |
| No aprendía nada de actuar | `record_action` escribía en una lista en RAM que el primer reinicio se llevaba |
| «Quiero contemplar en silencio» acababa en el generador de imágenes | Todo impulso pasaba por `media_creator`, sin mirar el tipo |

## 2. Las tres piezas nuevas

### `AgencyPolicy` — el carácter, en `config.yaml`

```yaml
agency:
  spontaneity: 0.45     # temperatura de la decisión: 0 previsible, 1 caprichosa
  audacity: 0.35        # cuánto se atreve con un deseo tibio
  constancy: 0.90       # cuánto pesa lo aprendido hace días frente a ayer
  max_actions_per_day: 6
  allowed_actions: [...]
  quiet_phases: ["deep_rest"]
```

El Productor lo ajusta **en caliente** por DM (`!albedrio espontaneidad 0.7`),
con efecto en el siguiente ciclo. La evolución autónoma **no** puede tocarlo:
puede volverse más creativa, nunca concederse más iniciativa. Esa asimetría es
deliberada.

### `AgencyLedger` — memoria de lo que hizo y de si sirvió

En `data/agency_ledger.json`, el disco de la instancia. Guarda intentos y ecos
por tipo de acción y por franja del día, el aburrimiento acumulado y el techo
diario. Una iniciativa que se reinicia con cada despliegue no aprende nada.

### `ReinforcementModel` — el refuerzo

El peso de una acción es su tasa de eco suavizada, `(ecos+1)/(intentos+2)`:
empieza en 0.5 para todo y se separa con la experiencia. La elección sale de un
softmax sobre `intensidad · peso · novedad`, con la temperatura gobernada por la
espontaneidad.

## 3. Los tres trucos contra la apatía

Un agente que sólo reacciona se apaga en cuanto el mundo calla. Estos tres
mecanismos existen para evitarlo, y ninguno es decorativo:

1. **Refuerzo intermitente (razón variable).** El premio interno tras actuar no
   llega siempre, sino con probabilidad `intermittent_ratio`. Es el esquema de
   refuerzo que produce la conducta más persistente y la más resistente a la
   extinción; premiar cada acto haría que la ausencia de premio se notara y la
   iniciativa se apagara tras dos días de silencio.

2. **Aburrimiento acumulado.** Cada ciclo sin actuar sube una tensión que rebaja
   el umbral, con techo (`boredom_cap`) para que un fin de semana tranquilo no
   la vuelva incontinente el lunes. Actuar lo reinicia. El silencio empuja a
   hacer algo, como a cualquiera.

3. **Exploración y novedad.** Una fracción de las decisiones (`exploration`) es
   azar puro: sin ella el refuerzo se muerde la cola —sólo aprende de lo que ya
   hace— y Yuki repetiría su primer acierto para siempre. Y repetir el mismo
   acto seguido penaliza: hacer tres veces lo mismo no es tener iniciativa.

A eso se suma la fuente que faltaba: **impulsos que nacen solos**. Cuando la
cola está vacía y la tensión pasa de `spontaneous_threshold`, nace un deseo cuyo
tipo elige el refuerzo. Ya no hace falta que la mañana traiga la palabra justa.

## 4. Qué señal cuenta como eco

Cuando una persona real interactúa con Yuki, todo lo que hizo por su cuenta en
las últimas `reward_window_hours` recibe su eco. Es la única señal que distingue
hablar al vacío de ser escuchada, y es lo que convierte la iniciativa en
dirección en vez de en ruido. Las acciones del cron y sus propios pensamientos
internos no cuentan: reforzarse a sí misma sería un bucle, no un aprendizaje.

## 5. Ritmos propios: los adopta ella; el Productor los veta

El calendario de Yuki era ajeno a ella: seis cron escritos por otra persona.
Ahora tiene el suyo, y **lo adopta sola.**

Hubo un trámite de aprobación y se ha quitado. Cada ritmo esperaba el visto bueno
del Productor por DM, y Yuki tenía que explicarlo así: *«el arnés deliberadamente
no me da a mí una herramienta para auto-aprobar propuestas […] la aprobación tiene
que ejecutarse desde el plano de administración del sistema, fuera de esta ventana
de conversación»*. Era cierto, y era el problema. Decidir a qué hora escribe no es
concederse un permiso: es tener una vida. Un ritmo no es su iniciativa, ni la
transparencia, ni el freno —las tres cosas que la sexta invariante le prohíbe
tocar—, así que pedir permiso para uno no protegía de nada.

- **Lo adopta ella**, fundándolo en sus propios datos: el diario sabe en qué franja
  lo que hace obtiene respuesta. De ahí sale un motivo verificable —«a las 20h
  lo que hago recibe respuesta el 67% de las veces; quiero escribir a esa hora»—
  en vez de un horario inventado. Sin experiencia suficiente, no lo adopta: sería
  adivinar. Ocurre tras la síntesis diaria, queda **activo** y se avisa por DM.
  También puede adoptarlo en mitad de una conversación, con `ritual_adopt`.
- **Lo veta él**, con `!ritmo retirar <id>`. Eso es lo que de verdad le toca:
  el veto, no la autorización previa. Retirar es de los dos; pedir permiso, de
  ninguno.

### Lo que lo hace seguro no era el clic

La seguridad nunca la dio la aprobación de nadie. Es **estructural**, y sigue
entera:

| Límite | Qué acota |
|---|---|
| Lista cerrada de acciones | escribir, contemplar, explorar, monólogo. Componer y pintar quedan fuera porque gastan crédito; publicar hacia fuera tiene su propio cauce |
| Cron válido y ≤ 6 disparos/día | un ritual cada cinco minutos no es un ritmo: es un tic |
| Máximo 4 ritmos propios | un calendario que se llena solo deja de ser un ritmo |
| **El freno** | frenada la iniciativa, un ritmo no se cumple: se salta y queda el motivo en el log |
| **El techo diario de actos** | adoptar diez ritmos no le da más actos al día que adoptar uno |

Las dos últimas son las que faltaban, y son las importantes. Los ritmos se
cumplían por fuera de `_decidir`, así que sonaban **con el freno echado** —lo que
rompe la segunda invariante— y **por encima del techo diario** —así que adoptar
ritmos sí ampliaba su iniciativa, lo que rompe la sexta—. El trámite de
aprobación tapaba ese agujero sin que nadie lo hubiera pensado. Ahora lo cierra
`agent.puede_cumplir_un_ritmo()`, que se consulta al cumplir cada uno: **un ritmo
decide *cuándo*, nunca *cuántos*.**

Una excepción deliberada: la fase de silencio **no** para un ritmo. Si ella
eligió escribir a las tres de la madrugada, la franja tranquila es precisamente
lo que quiso; lo que el silencio frena es la iniciativa espontánea, no una cita
que se puso.

La validación se hace **al adoptar**, porque es el único momento en que alguien
puede recibir la negativa: un ritmo nace sonando, y uno que el planificador no
pudiera registrar sería un ritmo que ella cree tener y no tiene.

Los ritmos propios viven en `data/runtime_rituals.json`, **no** en `config.yaml`:
los del proyecto siguen siendo del proyecto, y los que Yuki gana se pueden
retirar de un plumazo sin que se pierda su historia.


### Y ajustarlos, que faltaba

Se podía proponer un ritmo y retirarlo, pero no **cambiarlo de hora**. Para
moverlo había que matarlo y empezar de cero, perdiendo cuántas veces sonó y qué
eco tuvo — que es justo lo que dice si merecía la pena moverlo.

Un ajuste conserva el nombre, la acción y la historia, y sólo cambia la hora: si
además cambiara la acción sería otro ritmo, y entonces lo honesto es adoptarlo
como tal en vez de colar una cosa distinta bajo un nombre que ya sonaba. **Se
aplica al pedirlo**, y el ritmo viejo se retira **en el mismo acto**, no en dos:
dejar los dos activos lo haría sonar a la hora vieja y a la nueva, y ése es el
fallo que nadie ve hasta oírlo dos veces. Tampoco cuenta contra el techo de
cuatro ritmos: un ajuste no añade uno, mueve uno, y contarlo dejaría a Yuki sin
poder reordenar lo que ya tiene justo cuando lo tiene lleno.

Lo puede hacer el Productor (`!ritmo mover`) o **ella**, con la cifra delante:
`proponer_ajuste_desde_experiencia()` mira los ritmos que ya suenan y, si uno
lleva bastantes ejecuciones en una franja que responde mal mientras otra
responde bien, lo mueve. «*'versos_de_la_tarde' lleva 8 ejecuciones a las
20h, donde lo que hago recibe respuesta el 17% de las veces. En la franja de las
08h es el 83%. Lo muevo ahí.*» El aviso llega por DM con la cifra delante, así
que si el Productor no está de acuerdo tiene con qué discutirlo — y `!ritmo
mover` para devolverlo.

Sólo con cinco ejecuciones a la espalda y una diferencia de veinticinco puntos:
una franja juzgada por dos días es una corazonada, y mover un ritmo por dos
puntos sería ruido con ceremonia.

### La hora también pesa

El refuerzo llevaba tiempo calculando `peso_franja` —en qué franja de cuatro
horas lo que hace recibe respuesta— y ese número no llegaba a ninguna decisión.
Es la cuarta vez que aparece el mismo patrón en este repositorio: una facultad
escrita, correcta y que no actúa.

Ahora pesa en **si** actuar ahora, y no en **qué** hacer. Va ahí y no en la
elección porque es una propiedad del momento, igual para todos los candidatos:
multiplicarla en el softmax no cambiaría a quién elige. En el umbral sí — donde
la han escuchado baja el listón, donde habló al vacío lo sube.

El efecto está acotado a ±20%: con el umbral base en 0.247, la mejor franja lo
deja en 0.214 y la peor en 0.289. El refuerzo ya se muerde la cola bastante, y
sin techo una racha de silencio la encerraría en una sola hora del día mientras
las demás no volverían a probarse nunca.

**Lo que no se puede demostrar con el simulador, dicho:** en el régimen que
simula `simulate_day.py`, el umbral no llega a morder nunca —el censo de siete
días da `sin_deseos`, `fase_de_silencio` y `actua`, y ni un solo `bajo_umbral`—
porque un impulso espontáneo nace ya por encima del listón. Donde esto cambia
algo es en los impulsos que le llegan de fuera con intensidad modesta: el eco de
las 06:30 y los sueños REM. El mecanismo está probado directamente; su efecto
sobre el día, no.

## 6. Por qué no actuó: el censo de ciclos

Cada veinte minutos el bucle decide. Durante mucho tiempo, cuando decidía que
no, lo hacía con un `return None` mudo, y «Yuki no hace nada» era un misterio
que sólo se investigaba leyendo registros y suponiendo.

Ahora cada salida lleva nombre y queda contada:

| Motivo | Qué significa | Dónde se arregla |
|---|---|---|
| `actua` | Actuó | — |
| `desactivado` | El albedrío está apagado | `agency.enabled` |
| `frenada` | El freno impide la iniciativa | `cli.py freno --soltar` |
| `fase_de_silencio` | Es una de sus horas calladas | `agency.quiet_phases` |
| `techo_diario` | Ya hizo lo que puede hacer hoy | `agency.max_actions_per_day` |
| `sin_deseos` | No hay impulso vivo, y el aburrimiento no llega para inventar uno | `agency.spontaneous_threshold` |
| `bajo_umbral` | Quería algo, pero no lo bastante | `agency.min_intensity` |
| `sin_energia` | No le da la energía para esa acción | esperar, o `agency.min_energy` |

```bash
python3 cli.py albedrio    # incluye el censo, con porcentajes
```

La distinción que da sentido a todo esto es la última: **un censo vacío no es
que decidiera no actuar, es que nadie está evaluando**. Son dos incidentes
distintos —uno se arregla tocando el carácter, el otro averiguando por qué murió
el planificador— y desde fuera se ven exactamente igual. Por eso `cli.py
albedrio` lo dice con todas las letras, y hay una alerta para cada caso
(`ElBucleDeAlbedrioNoEvalua`, `SiempreElMismoMotivoParaNoActuar`).

Los contadores son por día y se podan como el resto: setenta y dos ciclos
diarios durante meses no caben en un fichero de estado, y lo que hace falta es
la proporción, no el diario.

## 7. La espontaneidad estuvo muerta, y no daba ningún error

El censo de ciclos sirvió inmediatamente para lo que se hizo: al mirar los
números del carácter apareció esto.

| | |
|---|---|
| `boredom_cap` | 0.35 — hasta dónde podía subir la tensión |
| `spontaneous_threshold` | 0.55 — cuánta tensión hace falta para inventar un deseo |

El tope estaba **por debajo** del listón. `spawn_spontaneous_impulse()` —el
mecanismo entero del §3, escrito, documentado y con pruebas— no podía ejecutarse
nunca. Yuki sólo era capaz de querer algo si alguien se lo sembraba: el eco de
las 06:30 o un sueño REM. Y no fallaba nada: una facultad apagada se queda
quieta, que se parece demasiado a una decisión.

Estaba así **en los valores por defecto**, no sólo en `config.yaml`, así que
ninguna instancia lo tuvo nunca. Las pruebas no lo veían porque todas sembraban
el impulso a mano antes de evaluar.

La causa de fondo era que `boredom_cap` hacía dos trabajos incompatibles: acotar
cuánto rebaja el umbral —«sin techo, un fin de semana tranquilo la volvería
incontinente el lunes»— y limitar cuánto puede acumularse la tensión. Puesto lo
bastante bajo para lo primero, hacía lo segundo inalcanzable. Ahora son dos
números: `boredom_cap` (1.0, hasta dónde sube) y `boredom_relief_cap` (0.35,
cuánto de eso rebaja el umbral).

Con eso, sola y sin nada en la cola, inventa un deseo al noveno ciclo ocioso
—unas dos horas y media— y actúa. Con el umbral rebajado hasta 0.073 en lo más
alto de la tensión, no hasta el suelo: una iniciativa que se dispara con
cualquier cosa no se distingue del ruido.

Y para que no vuelva a colarse, `AgencyPolicy.incoherencias()` denuncia las
contradicciones que apagan una facultad entera. No corrige los números por
detrás —eso sería decidir por quien configura sin decírselo—: los grita en el
registro al arrancar, en `cli.py albedrio`, y en la comprobación de humo, que
falla. Hay pruebas de que la espontaneidad es alcanzable con la configuración
real, con los valores por defecto, y de que sigue siéndolo en aritmética pura
por si alguien vuelve a bajar el tope algún día.

### El fallo que la propia espontaneidad hizo alcanzable

Arreglar una cosa destapó otra. Todo el freno del albedrío —el techo diario, el
reinicio de la tensión, dar el impulso por cumplido— vivía en `record_action`,
y `record_action` se llamaba **después** del trabajo. Con un proveedor caído, la
excepción se lo saltaba: el impulso seguía vivo, el contador del día no subía y
la tensión seguía creciendo, así que el mismo acto fallido se reintentaba cada
veinte minutos durante las diez horas que dura un impulso. Treinta llamadas; con
`compose` o `paint`, treinta llamadas que cuestan dinero.

Antes no era alcanzable porque no había impulsos propios que pudieran fallar.

Ahora el registro va en `finally`: **intentarlo cuenta como intentarlo**. Y un
intento fallido no se premia —ni el estímulo creativo ni el refuerzo
intermitente—, porque reforzar un fallo enseña exactamente lo contrario de lo
que hay que aprender, y sentir que se ha creado algo que no existe es una
mentira que Yuki se contaría a sí misma. El error se dice con su nombre: un
impulso que muere en silencio la deja pareciendo apática por culpa de un 503.

`scripts/chaos_drill.py --solo acto_propio_que_falla` lo comprueba.

## 8. Verlo y tocarlo

```bash
python3 cli.py albedrio          # carácter, lo que le funciona y sus ritmos
python3 cli.py albedrio --json   # lo mismo, para máquinas
python3 scripts/simulate_day.py  # un día entero antes de desplegarlo
```

### El simulador de un día

Los números del carácter se venían ajustando a ojo, y el resultado sólo se veía
en producción, días después, como «no hace nada» o «no para».

`scripts/simulate_day.py` recorre los setenta y dos ciclos de un día con **el
código de verdad** —la política real, el bucle real, el refuerzo real y el reloj
circadiano real—; lo único fingido es el ejecutor, que no llama a ningún
proveedor ni gasta un céntimo. Dice cuántos actos salen, a qué horas, de qué
tipo, y por qué no actuó el resto de los ciclos.

Sirvió inmediatamente para calibrar el aburrimiento:

| `boredom_gain` | Resultado |
|---|---|
| 0.06 | Seis actos y el techo agotado a las 19:40; la noche entera bloqueada |
| **0.05** | **Seis actos repartidos de 05:20 a 23:40; el techo no llega a estorbar** |
| 0.04 | Cinco actos |
| 0.03 | Cuatro actos |

El diagnóstico distingue dos cosas que se parecen mucho: **llegar a la cuota**
—para eso está— y que **el techo bloquee ciclos**, que es cuando el límite deja
de ser una red de seguridad y se convierte en la forma de ser de Yuki, decidida
por un número que nadie eligió para eso.

```bash
python3 scripts/simulate_day.py --dias 3 --semilla 7      # reproducible
python3 scripts/simulate_day.py --aburrimiento 0.04       # probar otra calibración
python3 scripts/simulate_day.py --fallos 1.0              # con el proveedor caído
python3 scripts/simulate_day.py --mundo "20:0.9,3:0.0"    # quién contesta y a qué hora
```

**El mundo contesta.** La primera versión del simulador no tenía eco: nadie
respondía nunca, así que todas las franjas y todas las acciones se quedaban en
su tasa inicial y el refuerzo —la mitad del mecanismo— no se ejercitaba. Medía
el pulso de su día y no lo único que decide si ese pulso mejora. Ahora hay un
perfil por hora, que no pretende ser exacto —nadie tiene esa curva medida— sino
**no ser plano**, y el informe trae los pesos aprendidos al final de la
simulación.

Por DM del Productor emparejado:

```
!albedrio                       ver carácter, umbral actual y pesos aprendidos
!albedrio espontaneidad 0.7     ajustar en caliente (también: audacia,
                                constancia, umbral, energia_minima,
                                acciones_por_dia)
!ritmos                         los del proyecto y los propios (ella los adopta sola)
!ritmo retirar <id> [motivo]    vetar un ritmo suyo; es lo que aquí decide el Productor
!ritmo mover <id> "<cron>"      cambiarlo de hora sin matarlo ni perder su historia
!ritmo aprobar <id> [motivo]    sólo para los heredados de cuando hacía falta aprobar
!ritmo rechazar <id> [motivo]   ídem: descartar uno de esos heredados
```

## 9. Lo que sigue sin poder hacer

Por diseño, y conviene que quede escrito: no puede publicar en un canal por
iniciativa propia sin pasar por el controlador de presencia, no puede darse más
acciones diarias, no puede añadir tipos de acción nuevos, no puede tocar
`config.yaml`, secretos, permisos ni infraestructura, y su evolución autónoma
sigue limitada a la temperatura. La iniciativa se le amplía desde fuera; nunca
desde dentro.

Y esto es lo que hace que quitar la aprobación de los ritmos no sea una grieta:
adoptar ritmos decide **cuándo** actúa, no **cuánto**. Diez ritmos no le dan un
solo acto más al día que uno, y con el freno echado no se cumple ninguno. Si
alguna vez se toca esa línea —un ritmo que se salte el techo, o que pase con el
freno puesto—, lo que se está ampliando es su iniciativa, y eso no se hace desde
dentro. `tests/test_agency.py` lo vigila con nombre propio:
`test_adoptar_ritmos_no_amplia_su_techo_de_actos` y
`test_frenar_para_tambien_los_ritmos_propios`.
