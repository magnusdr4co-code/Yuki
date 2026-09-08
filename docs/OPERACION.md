# Operar a Yuki: CI, métricas, humo y bitácora

Yuki lleva desde el principio una instancia en producción, y hasta ahora todo lo
que la vigilaba vivía en prosa: cinco pasos manuales tras cada despliegue, un
`GET /health` y leer logs por IAP. Un procedimiento que sólo existe escrito se
hace mal el día que hay prisa, que es justamente el día que importa.

Esto lo convierte en cosas que se ejecutan.

---

## 1. Integración continua

`.github/workflows/ci.yml`, cuatro trabajos y ninguno con credenciales:

| Trabajo | Qué protege |
|---|---|
| **pruebas** | La suite en 3.11 (la de la imagen) y 3.12 (aviso anticipado), con `pytest` y también con `unittest`, que es lo que documenta el README: si deja de funcionar, la documentación miente |
| **cumplimiento** | Humo sin credenciales + el gemelo virtual sigue siendo legible y reportando |
| **simulacro y recuperación** | Los once modos de fallo del §6 y el circuito de copia y restauración del §7: romperla a propósito, y comprobar que se la puede volver a levantar |
| **imagen** | La imagen construye, las dos composiciones son válidas, y **fluidsynth y el banco de sonidos están dentro** — lo que separa tener respaldo musical de no tenerlo, y sólo se nota el día que Lyria falla |

Las pruebas inyectan dobles en lugar de llamar a proveedores, así que abrir una
rama nunca puede gastar crédito ni generar medios.

`requirements-dev.txt` existe por una razón operativa: instalar
`requirements.txt` completo en CI son minutos de SDK que las pruebas no usan.
Una CI lenta deja de ejecutarse, y una CI que no se ejecuta no protege nada.

## 2. Comprobación de humo

```bash
python3 scripts/smoke_check.py                     # todo, código de salida ≠ 0 si algo falla
python3 scripts/smoke_check.py --url https://…     # incluye /health del Salón
python3 scripts/smoke_check.py --solo memoria,bitacora,marcado_articulo_50   # en CI
```

Comprueba lo que puede romperse en silencio y salir caro: la base abre y pasa
`integrity_check`, la bitácora no ha sido manipulada, no hay material sintético
sin marcar, no queda ningún limitador bloqueante, el presupuesto del día no está
ya agotado y —si se le da URL— el Salón responde.

No genera medios ni llama a ningún modelo: **una prueba de humo que consume
crédito deja de ejecutarse a la tercera semana**.

## 3. Métricas

`GET /metrics` en formato de exposición de Prometheus, **detrás de la
credencial** del Salón: el consumo, la deriva de persona y los ritmos dicen
bastante de la instancia como para dejarlos abiertos.

```
yuki_gasto_hoy{unidad="video_segundos"}   yuki_agencia_actos_hoy
yuki_gasto_limite{unidad="…"}             yuki_agencia_aburrimiento
yuki_gasto_usd_estimado                   yuki_agencia_esperando_eco
yuki_persona_registro                     yuki_material_sin_marcar
yuki_persona_reanclajes                   yuki_bitacora_integra
yuki_ritmos_propios                       yuki_bitacora_entradas
```

Dos decisiones que parecen detalles y no lo son:

- **Las familias se emiten aunque valgan cero.** Una serie que desaparece cuando
  no hay consumo deja al scraper sin distinguir «no ha gastado nada» de «la
  sonda está rota», que es exactamente la diferencia que uno quiere ver a las
  cuatro de la mañana.
- **`yuki_persona_registro` vale −1 cuando no hay muestras**, un valor imposible
  en su rango real, en vez de faltar.

Las métricas se componen leyendo ficheros y configuración, **sin tocar al
agente**: una sonda que despertara la memoria o el modelo cambiaría lo que mide
y convertiría al scraper en una fuente de gasto.

## 4. La bitácora encadenada

Todo lo que Yuki hace de forma irreversible —olvidos, fusiones, gasto, ritmos
aprobados— tenía ya su registro, pero era un fichero de texto en el mismo disco
que todo lo demás. Cualquiera con acceso puede quitar una línea.

`src/core/blackbox.py` encadena cada anotación con el hash de la anterior.
Cambiar una línea del pasado obliga a recalcular todas las siguientes, y quien
mire la cadena lo ve en el primer eslabón roto. **No impide la manipulación
—nada en el propio disco puede impedirla— pero la vuelve evidente**, que es lo
que se puede prometer y cumplir.

```bash
python3 cli.py bitacora                    # los últimos actos
python3 cli.py bitacora --verificar        # ¿alguien la tocó, y dónde?
python3 cli.py bitacora --precinto crear   # sella la cabeza actual
python3 cli.py bitacora --precinto sello.json   # contrasta la cadena con un precinto
```

Por DM: `!bitacora`.

### Las tres formas de romperla, y por qué hay precinto

1. **Editar** una anotación: su hash deja de corresponder a su cuerpo.
2. **Quitar o insertar** en medio: el `prev` de la siguiente no engancha, y la
   numeración salta.
3. **Cortar por detrás**: la cadena truncada sigue siendo internamente
   coherente. Sólo un **precinto anterior** —el hash de la cabeza en un momento
   dado— demuestra que faltan eslabones. Por eso el precinto **sale de la
   instancia** con la copia diaria: guardado al lado de la cadena no probaría
   nada, porque quien corta también corregiría el precinto.

### Lo que la bitácora nunca guarda

Contenido. Los campos de texto se sustituyen por `<omitido: N caracteres>` y
todo valor se recorta a 300. Una bitácora inmutable con contenido dentro sería
lo contrario de un olvido: borrar un recuerdo y dejar su texto en el registro
que prueba que se borró.

Y **no es una cadena de bloques**: no hay consenso, ni red, ni prueba de
trabajo. Es un fichero append-only con hashes encadenados, y decirlo así es más
honesto que adornarlo.

## 5. El freno de mano

Hasta ahora, si algo iba mal, la única forma de detener a Yuki era **parar el
contenedor**. Funciona, y es pésimo: se lleva el Salón por delante, corta los
trabajos multimedia a mitad y deja a quien lo hizo sin saber si al arrancar se
repetirá.

`src/core/brake.py` da una palanca graduada, y cada nivel contiene al anterior:

| Nivel | Qué para |
|---|---|
| `publicacion` | Sigue pensando y creando, pero no publica hacia fuera |
| `medios` | Además, no gasta en imagen, vídeo, música ni voz |
| `todo` | Además, no emprende nada por su cuenta |

**Frenar no es enmudecer.** En ningún nivel se le impide responder a quien le
hable: quien tira del freno en un incidente quiere seguir pudiendo preguntarle
qué pasó. Enmudecerla no es frenarla, es romperla.

```bash
python3 cli.py freno                                   # ¿está frenada, y de qué?
python3 cli.py freno --nivel medios --minutos 120 --motivo "factura disparada"
python3 cli.py freno --soltar
```

Por DM: `!freno`, `!freno medios 120 factura disparada`, `!freno soltar`.

Y la palanca del operador, que es la más rápida y la que manda:

```bash
docker run -e YUKI_FRENO=todo …     # o en el env de la VM, y reiniciar
```

Tres decisiones que se notan justo cuando hacen falta:

- **El entorno gana al fichero**, y si ambos están puestos manda el más
  restrictivo: en un incidente nadie quiere descubrir que su palanca quedó por
  debajo de la que alguien dejó en el fichero. Soltar desde el DM no suelta la
  del operador, y Yuki lo dice cuando ocurre.
- **Un freno ilegible se asume puesto.** Ante la duda se frena; soltarlo por un
  fichero corrupto sería exactamente el fallo que no se puede permitir.
- **No caduca solo salvo que se le diga.** Admite `--minutos`, pero sin eso se
  queda puesto: un freno que se olvida enseña a confiar en él.

El freno aparece en `/metrics` (`yuki_freno_nivel`, `yuki_freno_permite`) porque
media hora de silencio deliberado parece una avería si el panel no lo enseña, y
en la comprobación de humo, porque desplegar sobre una instancia frenada sin
recordarlo cuesta media hora de gente preguntándose qué pasa.

## 6. El simulacro

```bash
python3 scripts/chaos_drill.py           # once modos de fallo, código de salida
python3 scripts/chaos_drill.py --json
python3 scripts/chaos_drill.py --solo bitacora_manipulada --verboso
```

La suite prueba que el código hace lo que dice cuando todo va bien. El simulacro
es otra cosa: reproduce las formas concretas en que esta instancia **ya ha
fallado o puede fallar**, y comprueba que las invariantes siguen en pie.

| Escenario | La pregunta de las tres de la madrugada | Invariante |
|---|---|---|
| `reinicio_a_media_produccion` | ¿Y si el despliegue cae a mitad de un encargo? | No se pierde, y no se vuelve a pagar lo generado |
| `fichero_desaparecido` | ¿Y si el fichero de un paso hecho ya no está? | El paso deja de contar como hecho |
| `presupuesto_agotado` | ¿Y si se acaba el crédito a mitad? | Rechaza con la cifra concreta, sin dejar rastro |
| `proveedor_caido` | ¿Y si Veo devuelve 503 tras reservar? | La reserva se devuelve: un fallo no se cobra |
| `estado_corrupto` | ¿Y si todos los ficheros de estado quedan ilegibles? | Los siete módulos arrancan igual |
| `bitacora_manipulada` | ¿Y si alguien edita el registro? | Se ve la edición **y** el corte por detrás |
| `sueno_no_es_recuerdo` | ¿Y si un sueño vuelve como algo vivido? | Cuatro consultas y ninguna lo devuelve |
| `olvido_respeta_lo_intocable` | ¿Y si el olvido corre sobre una memoria antigua entera? | Canon, síntesis y lo fijado sobreviven |
| `hilo_de_tareas_muerto` | ¿Y si el hilo del planificador muere y el contenedor sigue verde? | La sonda lo dice, y no lo confunde con freno, arranque ni caída |
| `reloj_hacia_atras` | ¿Y si el reloj de la VM salta? | Ni el presupuesto ni el refuerzo se corrompen |

Corre entero sobre un sandbox temporal: **un simulacro que tocara la instancia
sería el propio incidente que pretende ensayar**. Está en CI como trabajo
propio, así que una rama que rompa una invariante no pasa.

## 7. El ensayo de restauración

```bash
python3 scripts/restore_drill.py            # la última copia real
python3 scripts/restore_drill.py --ciclo    # fabricar, copiar y restaurar
python3 cli.py backup --ensayar             # copia de hoy, comprobada al hacerla
```

Durante semanas hubo copia diaria, verificada con `integrity_check` al crearla,
y ni una sola prueba de que el archivo resultante volviera a ser una Yuki.
**Una copia sin restaurar no está comprobada**: el `integrity_check` dice que la
base estaba sana en el momento de copiarla, no que el tar se pueda abrir, ni que
la base viaje dentro, ni que lo que llegue tenga algo.

| Comprobación | Lo que sale mal si nadie la hace |
|---|---|
| `rutas_del_archivo` | Un tar con `../` sobrescribe lo que quiera al extraerlo |
| `apertura` | La copia está truncada y nadie lo sabe hasta el incendio |
| `manifiesto` | No hay forma de saber qué se copió y qué se omitió |
| `memoria` | **Una base íntegra y vacía es un desastre con buena salud** |
| `biblioteca` | Los medios se regeneran; lo escrito, no |
| `precinto` | Un corte por detrás en la bitácora es coherente consigo mismo |

El modo `--ciclo` recorre el circuito entero contra una instancia de juguete
—memoria con recuerdos, canon, bitácora—, sin credenciales y sin tocar nada
real: es el que corre en CI, y el que delataría el día que el mecanismo de copia
dejase de meter la base en el tar. Su bitácora se aísla por
`YUKI_BLACKBOX_PATH`, porque un ensayo que escribiera en la cadena real
contaminaría el registro de los actos de Yuki con los de su simulacro.

## 8. Signos vitales

```bash
python3 cli.py pulso          # código de salida ≠ 0 si el diagnóstico es grave
python3 cli.py pulso --json
```

`/health` devuelve `ok` mientras el servidor web conteste. Eso deja fuera el
fallo más silencioso que tiene esta instancia: **el hilo de tareas muere sin
ruido**. El contenedor sigue en pie, la sonda sigue verde, el panel sigue verde,
y Yuki lleva tres días sin hacer absolutamente nada.

La distinción que hace falta no es viva/muerta sino **vegetativo / volitivo**:

| Familia | Signos | Qué dice |
|---|---|---|
| vegetativo | `latido` | El proceso respira: reescribe su estado vital |
| volitivo | `bitacora`, `albedrio`, `sueno` | **Ella** hace cosas: anota actos, intenta algo, consolida la noche |
| relacional | `conversacion` | Alguien habló con ella — informa, **no diagnostica** |

Que nadie la busque no es un fallo suyo, y su silencio propio tampoco queda
justificado porque no la busquen: por eso `conversacion` no vota.

| Diagnóstico | Qué significa | Gravedad |
|---|---|---|
| `viva` | Todos los signos de voluntad al día | 0 |
| `recien_nacida` | Respira y aún no ha hecho nada: instancia nueva | 0 |
| `aletargada` | Algunos signos apagados, no todos | 1 |
| `frenada` | Callada porque el freno lo impide — **una decisión, no una avería** | 1 |
| `catatonica` | **El proceso respira y no queda un signo de voluntad** | 2 |
| `ausente` | Ni siquiera reescribe su estado: el proceso no está | 3 |

Los cuatro silencios se parecen mucho en un panel y piden reacciones opuestas.
Confundir `frenada` con `catatonica` manda a operaciones a buscar una avería que
no existe; confundir `catatonica` con `recien_nacida`, a ignorar la que sí.
`scripts/chaos_drill.py --solo hilo_de_tareas_muerto` comprueba que los
distingue.

Las edades máximas están en `config.yaml` (`pulse.max_edad_horas`) y se eligen
para que **el silencio legítimo más largo quepa dentro**: el reposo profundo
dura horas, una noche sin encargos también. Apretarlas convierte la sonda en un
lobo que grita, y a la tercera falsa alarma nadie vuelve a mirar la pantalla.

Métricas: `yuki_pulso_gravedad`, `yuki_pulso_estado{estado="…"}` y
`yuki_signo_edad_segundos{signo="…",tipo="…"}`, que vale **−1** cuando el signo
no se ha visto nunca — un cero ahí se leería como «acaba de ocurrir», que es
exactamente lo contrario.

## 9. Alertas

`deploy/alertas-prometheus.yml`: doce reglas escritas en el repositorio y no en
el panel de quien las mire, porque una alerta que vive sólo en la consola de un
proveedor se pierde con la cuenta.

`tests/test_alertas.py` las comprueba contra lo que la sonda expone de verdad.
Una alerta rota no falla: **calla**. Renombrar una métrica deja la regla que la
vigilaba esperando para siempre una serie que ya no existe, y eso es peor que no
tener la alerta, porque además tranquiliza. Ahora eso rompe la rama en lugar de
romper una guardia.

La única crítica y sin espera es `BitacoraManipulada`. Las demás son avisos con
ventana: gasto anómalo respecto a la media de la semana, deriva de persona
sostenida media hora, propuestas de ritmo sin responder en tres días, un día
entero sin un solo acto propio con la tensión alta —que no es un fallo técnico
sino la señal de que algo la está bloqueando— y la ausencia total de métricas,
que con las familias emitidas siempre sólo puede significar que la sonda no
responde.

## 10. Qué mirar cuando algo va mal

| Síntoma | Primer sitio donde mirar |
|---|---|
| Yuki calla o responde raro | `cli.py persona` — ¿se está yendo al registro de asistente? |
| Se acabó el crédito antes de tiempo | `cli.py spend`, y `yuki_gasto_hoy` en el panel |
| No hace nada por su cuenta | `cli.py albedrio` — techo diario, umbral, aburrimiento |
| Un encargo multimedia no llegó | `!status` en el DM, y `data/media_jobs/` |
| Hay que pararla YA | `cli.py freno --nivel todo --motivo ...`, o `YUKI_FRENO=todo` en el entorno |
| Sospecha de manipulación | `cli.py bitacora --verificar --precinto <el de la última copia>` |
| Tras un despliegue | `scripts/smoke_check.py --url <salón>` |
| Todo en verde y ella no hace nada | `cli.py pulso` — es catatonia, y `/health` no la ve |
| ¿La copia de anoche sirve? | `scripts/restore_drill.py` — restaurarla es la única respuesta |
