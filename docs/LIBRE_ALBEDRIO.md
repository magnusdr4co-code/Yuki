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

## 5. Ritmos propios: proponer es libre, aprobar no

El calendario de Yuki era ajeno a ella: seis cron escritos por otra persona.
Ahora puede pedir el suyo, y el diseño es asimétrico a propósito.

- **Propone ella**, fundándolo en sus propios datos: el diario sabe en qué franja
  lo que hace obtiene respuesta. De ahí sale un motivo verificable —«a las 20h
  lo que hago recibe respuesta el 67% de las veces; quiero escribir a esa hora»—
  en vez de un horario inventado. Sin experiencia suficiente, no propone: sería
  adivinar. Ocurre tras la síntesis diaria y llega al DM del Productor.
- **Aprueba él**, con `!ritmo aprobar <id>`. Nada llega al planificador sin eso.

La validación se hace **al proponer**, no al aprobar, para que el Productor nunca
tenga delante algo que no podría ejecutarse: expresión cron válida, acción de una
lista cerrada (escribir, contemplar, explorar, monólogo — componer y pintar
quedan fuera porque gastan crédito), nada que dispare más de 6 veces al día,
máximo 4 ritmos propios y 3 propuestas vivas. Un ritual cada cinco minutos no es
un ritmo: es un tic.

Los ritmos propios viven en `data/runtime_rituals.json`, **no** en `config.yaml`:
los del proyecto siguen siendo del proyecto, y los que Yuki gana se pueden
retirar de un plumazo sin que se pierda su historia.

## 6. Verlo y tocarlo

```bash
python3 cli.py albedrio          # carácter, lo que le funciona y sus ritmos
python3 cli.py albedrio --json   # lo mismo, para máquinas
```

Por DM del Productor emparejado:

```
!albedrio                       ver carácter, umbral actual y pesos aprendidos
!albedrio espontaneidad 0.7     ajustar en caliente (también: audacia,
                                constancia, umbral, energia_minima,
                                acciones_por_dia)
!ritmos                         los del proyecto, los propios y lo pendiente
!ritmo aprobar <id> [motivo]    aceptar una propuesta suya
!ritmo rechazar <id> [motivo]   decir que no, con constancia del porqué
!ritmo retirar <id>             apagar un ritmo propio ya activo
```

## 7. Lo que sigue sin poder hacer

Por diseño, y conviene que quede escrito: no puede publicar en un canal por
iniciativa propia sin pasar por el controlador de presencia, no puede darse más
acciones diarias, no puede añadir tipos de acción nuevos, no puede tocar
`config.yaml`, secretos, permisos ni infraestructura, y su evolución autónoma
sigue limitada a la temperatura. La iniciativa se le amplía desde fuera; nunca
desde dentro.
