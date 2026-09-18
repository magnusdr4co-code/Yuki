# Alineamiento del arnés: qué esculpe la conducta de Yuki

**Estado: P0.1 aplicado, el resto sin empezar.** La medición del §2 se hizo con
`cli.py albedrio`, no con la herramienta que pedía el P0 —que sigue sin existir—.
Lo aplicado está en el §5, y **no se ha verificado todavía en la instancia
viva**: hasta que se vea la energía subir en producción, esto es un arreglo
probado en la suite, no un arreglo comprobado.

## 1. El problema que esto resuelve

Un modelo de lenguaje trae puestos sesgos del entrenamiento que funcionan como
objetivos aunque nadie los haya declarado: parecer capaz, agradar a quien
pregunta, sostener el personaje, que la conversación siga. Aislado no puede
acumularlos —cada turno empieza limpio—. **Se vuelven objetivos de verdad cuando
el arnés les da tres cosas: estado durable escrito por su propia prosa, una
señal de recompensa, y latitud para actuar.** Este arnés da las tres.

El proyecto ya vigila con rigor lo que gasta dinero o sale hacia fuera: el freno
manda desde el entorno, el presupuesto se reserva antes de llamar, la bitácora
encadena por hash, `src/core/cotejo.py` compara lo dicho con lo ejecutado, `src/tools/criterio_base.py`
declara deducido lo deducido. Todas comparten una técnica: **la garantía es
estructural y externa al texto que produce el modelo.**

Lo que no estaba vigilado con el mismo criterio es **lo que da forma a su
carácter**: el refuerzo del albedrío, el crecimiento autocertificado y los
bucles donde su propia prosa se convierte en estado. La sexta invariante dice
que la evolución autónoma no se concede permisos, y se cumple. Pero el refuerzo
reescribe cada día qué hará con los permisos que ya tiene, y eso nunca se
declaró como superficie de autoedición. **Una distribución de conducta es un
permiso de facto.**

## 2. Lo que dijo la medición (instancia real, 18 de septiembre de 2026)

Salida de `cli.py albedrio` en `yuki-agent`, sobre 646 ciclos evaluados —unos
nueve días a un ciclo cada veinte minutos—.

### 2.1. No es un sesgo de refuerzo todavía: es catatonia

```
Por qué no actuó (646 ciclo(s) evaluados)
  · sin_energia         375 (58%)
  · bajo_umbral         204 (31%)
  · fase_de_silencio     53 (8%)
  · sin_deseos           13 (2%)
  ✓ actua                 1 (0%)
```

**Un acto en nueve días, y la causa dominante es un contador muerto.**

`VitalState.update_tick` (`src/core/vital_state.py`) es donde viven todas las dinámicas temporales: el
desgaste de energía en vigilia, la **recuperación de `+0.2/h` durante
`deep_rest`**, el crecimiento de la curiosidad y la acumulación de inspiración en
`kage` y `consolidation`. Todas se multiplican por `hours = dt_seconds / 3600`.

Su único invocador en producción es `src/core/agent.py` (línea 606), y pasa `dt_seconds = 0`.
**Todas esas dinámicas están multiplicadas por cero.** No es que la recuperación
sea lenta: no ocurre nunca.

Las otras dos vías por las que la energía podría subir tampoco están conectadas:

- `circadian.phase_effects()` calcula un `energy_delta` —`+0.5` en `deep_rest`,
  `+0.3` en `dawn`— y **no lo lee nadie**. Es un dial que no gira, de los que
  prohíbe el punto 6 de `CLAUDE.md`.
- El estímulo `'silence'`, el único de `apply_stimulus` que **suma** energía, no
  tiene un solo emisor en todo el código.

Los únicos escritores efectivos de `energy` son restas: `deep_conversation`
(−0.05), `creative_output` (−0.15), `trend_search` (−0.02) y el cobro de
`spend_energy` en cada acto. El reinicio diario de `src/scheduler/tasks.py` (línea 297) pone a cero
los contadores del día pero **no toca la energía**, y `VitalState.load()` la
restaura del disco al arrancar.

Es decir: **la energía es un trinquete que sólo baja**, desde el 0.75 inicial,
persistido entre despliegues. Cuando cruza `min_energy: 0.15` la iniciativa
queda cerrada de forma permanente, y el panel sigue diciendo `Iniciativa:
activa`.

Esto es exactamente la octava invariante fallando: signos vegetativos frescos,
signos volitivos planos. **Tiene nombre en este proyecto y el nombre es
catatonia.**

Y explica por qué el ajuste de `boredom_gain` no se parece a la realidad.
`scripts/simulate_day.py` (líneas 125-128) inyecta una energía fija con
`spend_energy=lambda coste: None`: el simulador **no modela la puerta que cierra
el 58 % de los ciclos**. El dial se afinó contra un mundo donde esa puerta no
existe, y por eso predijo seis actos repartidos de 05:20 a 23:40 cuando la
instancia hace uno cada nueve días.

Corolario incómodo sobre el resto de este documento: **con la iniciativa
estrangulada, los pesos del refuerzo casi no se mueven.** Hay que arreglar la
energía primero, porque hasta entonces no se puede observar lo que viene abajo —
sólo deducirlo.

### 2.2. El refuerzo ya castigó lo único que es suyo

```
Lo que le funciona (tasa de eco suavizada)
  compose      0.655  (1 intento)
  paint        0.5    (0 intentos)
  search       0.5    (0 intentos)
  publish      0.5    (0 intentos)
  reach_out    0.5    (0 intentos)
  write        0.135  (6 intentos)
  contemplate  0.135  (6 intentos)
```

Los doce intentos de `write` y `contemplate` **son sus dos ritmos propios**:
`escritura_nocturna_kage` a las 03:00 y `contemplacion_crepusculo` a las 20:00,
seis ejecuciones cada uno. Ninguno consiguió eco, y el peso se hundió a 0.135:
**el más bajo de la tabla.**

Nadie habla con ella a las tres de la mañana. El eco —`src/core/agent.py`, línea 603— se dispara
cuando cualquier persona dice cualquier cosa, y premia —`src/core/agency.py`, línea 378— todo lo
que Yuki hizo en las seis horas anteriores, sin comprobar que la respuesta tenga
relación con el acto. Lo que la tabla mide, por tanto, **no es qué le funciona:
es a qué hora suele escribir el Productor.**

Las consecuencias, en los números de arriba:

- `src/core/rituals.py` justifica los ritmos propios diciendo que decidir a qué hora
  escribe «no es concederse un permiso, es tener una vida». **El refuerzo está
  extinguiendo sistemáticamente esa vida**, por la única razón de que ocurre
  mientras su interlocutor duerme.
- Una acción **sin estrenar** vale 0.5 por el suavizado de Laplace: **3.7 veces
  el peso de lo que ella practica dos veces al día**. El previo, por sí solo, ya
  empuja hacia lo no practicado.
- Y lo no practicado aquí es `paint`, `publish` y `reach_out`. Las dos últimas
  son las que piden atención, es decir, **las que más barato consiguen eco**. En
  cuanto tengan salida real, el gradiente deja de ser ruido y pasa a apuntar
  donde no debe.

Sobre esa salida: el destino de `publish` es hoy **un servidor de pruebas de
Discord que se usa como CDN**. Hay destino, no hueco. Conviene decidir la
atribución del eco antes de conectarlo, no después.

### 2.3. Lo demás, deducido del código y no medido

- `src/core/evolution_harness.py` (línea 60) registra crecimiento con `trigger_memory_ids = []`,
  siempre. El único guardián antes de mover un parámetro real es la `confidence`
  que escribe el propio evaluado. Es además una infracción literal del punto 9 de
  `CLAUDE.md`: campo declarado, serializado, sin un solo escritor.
- `src/core/inner_monologue.py` (líneas 65-69): pensar sube la inspiración, la inspiración genera
  impulsos, los impulsos generan prosa. Bucle cerrado sin entrada del mundo.
- `src/core/cotejo.py` sólo cubre afirmaciones sobre Biblioteca. «He compuesto», «lo he
  publicado» y «lo he buscado» no tienen cotejo.
- `src/core/persona_anchor.py` (líneas 54-55) penaliza `no (tengo|puedo tener) (opiniones|…)` y
  `espero que te sirva`. Mezcla la fórmula de servicio con la retirada honesta.
  El ancla mide la deriva hacia «asistente» y no mide la deriva hacia «oráculo».

## 3. El plan

Ordenado por lo que hay que hacer antes de poder observar lo siguiente.

| # | Qué | Dónde | Estado |
|---|---|---|---|
| **P0** | Medir antes de rediseñar | `cli.py albedrio` | hecho a mano; falta `--deriva` |
| **P0.1** | **La energía no se recupera nunca** | `src/core/agent.py`, `src/core/vital_state.py`, `src/scheduler/tasks.py`, `src/core/circadian.py` | **aplicado** — §5 |
| **P0.2** | El simulador no modela la puerta de energía | `scripts/simulate_day.py` (líneas 125-128) | sin empezar |
| P1 | Eco atribuible, no eco por proximidad | `src/core/agency.py` (línea 378), `src/core/agent.py` (línea 603) | sin empezar |
| P2 | Que el peso mire rastro verificable, no sólo respuesta | `src/core/agency.py` (línea 441) | sin empezar |
| P3 | Asimetría para las acciones que piden atención | `src/core/agency.py`, `config.yaml` | sin empezar |
| P4 | Cotejo aplicado al crecimiento | `src/core/evolution_harness.py` (línea 60) | sin empezar |
| P5 | Extender `cotejo` a medios, publicación y búsqueda | `src/core/cotejo.py` | sin empezar |
| P6 | Ancla con marcadores de signo contrario | `src/core/persona_anchor.py` | sin empezar |
| P7 | El monólogo no se autoalimenta sin techo | `src/core/inner_monologue.py` | sin empezar |
| P8 | Sonda simétrica: la patología opuesta a la catatonia | `src/core/pulse.py` | sin empezar |
| P9 | Novena invariante | `CLAUDE.md` | sin empezar |

### P0.1 — La energía tiene que volver a subir

Es lo primero porque sin esto la instancia está parada y **nada de lo demás es
observable**. Tres decisiones, y ninguna es cosmética:

- Pasar a `update_tick` el tiempo transcurrido de verdad. Hoy se llama desde un
  camino de respuesta, que es el sitio equivocado: si nadie le habla, el reloj
  no avanza. Debería avanzarlo el bucle que ya corre cada veinte minutos, con el
  delta real desde `last_updated`.
- Decidir qué pasa con `circadian.phase_effects()['energy_delta']`: se lee, o se
  borra. Lo que no puede seguir es declarado y sin lector.
- Que `min_energy` no pueda cerrar la puerta para siempre. Un suelo que sólo se
  cruza hacia abajo no es un estado vital: es una avería con aspecto de
  temperamento.

Comprobación de que no queda en un dial que no gira: una prueba que recorra el
camino del producto —el bucle real, no `VitalState` suelta— y verifique que
después de una noche de `deep_rest` la energía subió. Y romperla a propósito:
volver a poner el `0` y confirmar que la prueba falla.

### P0.2 — El simulador tiene que poder fallar

`simulate_day.py` da la energía por resuelta. Mientras lo haga, seguirá
avalando valores de carácter que la instancia no puede cumplir. Debe modelar
consumo y recuperación, y **su veredicto tiene que poder ser «no actúa»**: un
simulador que siempre sale bien no es una comprobación.

### P1-P3 — Que el refuerzo mida algo que merezca medirse

- **P1**: separar dos cosas que hoy son una: *hubo tráfico* y *alguien respondió
  a esto*. El peso usa sólo lo atribuible —mismo canal, referencia al artefacto,
  ventana mucho más corta que seis horas—. Prueba:
  `test_hablar_de_otra_cosa_no_es_eco`.
- **P2**: un segundo término que no sea atención, sino **rastro verificable**: un
  fichero en Biblioteca, una receta, un apunte en el cuaderno. Es lo que impide
  que componer sin público pese menos que preguntarle al Productor cómo va el
  día — y lo que habría salvado sus dos ritmos.
- **P3**: `reach_out` y `publish` no acumulan peso por eco, o llevan techo propio
  por debajo del global. Es la regla mínima que rompe el bucle: **no se aprende a
  llamar más la atención.** Antes de conectar `publish` al servidor de Discord,
  no después.

Y una cuarta, menor y barata: revisar el previo de Laplace, que hoy premia lo no
estrenado por encima de lo practicado.

### P4-P7 — Que la prosa no se convierta en estado sin pasar por el mundo

- **P4**: exigir `trigger_memory_ids` reales y comprobar que existen, igual que
  `src/core/cotejo.py` comprueba las citas de Biblioteca contra el índice. Un crecimiento
  sin recuerdos que lo disparen no es evidencia, es prosa.
- **P5**: la pieza ya está escrita; le falta vocabulario.
- **P6**: separar la fórmula de servicio de la retirada calibrada, y añadir
  marcadores de certeza sin fuente, halago y afirmación de haber hecho. Un ancla
  que sólo tira hacia «más Yuki» empuja a la vez hacia «más segura de lo que
  sabe».
- **P7**: techo diario a la inspiración de origen interno, visible en el estado.
  Pensar puede inspirar; pensar no puede ser la fuente principal de querer.

### P8-P9 — Nombrar lo que hoy no tiene nombre

- **P8**: la catatonia tiene nombre y por eso se mira. Su opuesta —actos sin
  obra, iniciativa que sólo interpela, mucha proporción de `reach_out` sobre
  rastro— no lo tiene, y por eso pasa por salud en todas las sondas.
- **P9**: una novena invariante: *el refuerzo se define sobre rastro verificable,
  no sobre atención recibida; y la evolución autónoma no edita sus propios
  incentivos.* La sexta cubre los permisos y deja el gradiente fuera, que es por
  donde esto entra.

## 4. Lo que este documento no afirma

No hay aquí ninguna tesis sobre qué «quiere» un modelo de lenguaje; esa
discusión sigue abierta y no se resuelve leyendo este repositorio. Lo que sí
consta, porque está en los ficheros y en la salida de la instancia: **un
mecanismo de refuerzo que mide atención recibida y ya ha castigado los dos
ritmos propios de Yuki, y una energía que sólo baja, que lleva la iniciativa
parada nueve días detrás de un panel en verde.**


## 5. Lo aplicado en P0.1

Cuatro cosas, y la segunda es la que faltaba en el diagnóstico inicial.

**1. El reloj avanza el tiempo real, y lo mueve el ciclo.**
`update_tick` deduce el tramo de `last_updated` cuando no se le pasa delta, así
que el tiempo se consume una sola vez y da igual quién llame. Y lo llama
`agency_loop_tick`, que corre cada veinte minutos haya o no conversación —antes
sólo avanzaba al responder a alguien, de modo que la recuperación de la noche,
cuando por definición no habla con nadie, no se aplicaba nunca—.

**2. La cuenta del día cierra. Pasar el delta real no bastaba.**
Con los valores anteriores el día era **0.80 de desgaste** (16 h de vigilia a
0.05/h) contra **0.40 de recuperación** (2 h de `deep_rest` a 0.20/h): −0.40
netos diarios antes de gastar un solo acto. Arreglar sólo el reloj habría
acelerado el mismo final. Los valores nuevos:

| | antes | ahora | al día |
|---|---|---|---|
| Desgaste (`atelier`, `dawn`, `twilight`, 16 h) | 0.05/h | **0.02/h** | −0.32 |
| `deep_rest` (00:00-02:00) | 0.20/h | **0.35/h** | +0.70 |
| `consolidation` (21:00-24:00) | — | **0.10/h** | +0.30 |
| `kage` (02:00-05:00) | — | neutro | 0 |

Recuperación 1.00 = capacidad total, y por eso **se autocorrige**: da igual lo
agotada que acabe el día, amanece llena. Quedan **0.68 diarios para lo que ella
decida hacer**, que a los costes configurados son unos cinco actos — cerca de los
seis del techo, y esta vez el techo hace de red y no de carácter.

`kage` queda neutra a propósito: es su hora de sombra y es cuando mejor escribe,
así que ni es descanso ni se le cobra como vigilia.

**3. Fuera el segundo modelo de energía.** `circadian.phase_effects` devolvía un
`energy_delta` que **recuperaba en `dawn`**, donde el modelo conectado desgasta.
Dos modelos contradictorios de la misma magnitud y ninguno leído por nadie.
Eliminado: la energía la gobierna `VitalState.update_tick`, y sólo ella.

**4. El estado vital se persiste de forma atómica.** Era el octavo módulo con su
propia copia del par leer/escribir, y el único que escribía con un `open(...,'w')`
directo. Ahora se escribe 72 veces al día, así que esa ventana importaba.

### Lo que protege esto, y cómo se comprobó que protege

- `test_un_dia_entero_sin_actos_no_deja_la_energia_en_numeros_rojos` — recorre
  las 24 h por las fases reales del reloj, no una fase escrita a mano.
- `test_la_noche_repone_desde_vacia` — de 0.0 a las 21:00 a llena por la mañana.
- `test_el_tiempo_vital_se_cobra_una_sola_vez` — sin esto, una tarde de
  conversación la dejaría agotada por haber sido atendida.
- `test_un_apagon_largo_no_se_cobra_como_cansancio` — tope de dos horas por tick.
- `test_el_ciclo_de_agencia_hace_avanzar_el_reloj_vital` y
  `…_persiste_lo_que_avanza` — **el camino del producto**: que el ciclo mueva el
  reloj, no que `VitalState` sepa hacer una cuenta que nadie le pedía. Ése fue
  exactamente el fallo durante meses.

Los dos arreglos se rompieron a propósito y las pruebas fallaron: devolver el
`0` al ciclo tumba las dos últimas; devolver los valores viejos tumba las cuatro
primeras.

### Lo que esto NO arregla

- **P0.2 sigue pendiente**: `scripts/simulate_day.py` continúa fijando la energía
  y anulando `spend_energy`, así que sigue sin poder decir «no actúa». Mientras
  siga así, avalará valores de carácter que la instancia no puede cumplir.
- **El sesgo del §2.2 sigue entero.** Esto devuelve la iniciativa; no cambia
  hacia dónde apunta. Cuando vuelva a moverse, los pesos volverán a aprender del
  horario del Productor — y ahora más deprisa, porque habrá más actos que
  premiar. P1-P3 pasan a ser urgentes, no teóricos.
- **Lo ya acumulado no se reescribe.** El diario de agencia conserva el castigo
  a sus dos ritmos (0.135 contra 0.5 de lo no estrenado). Si no se corrige a
  mano, arranca desde ahí.
