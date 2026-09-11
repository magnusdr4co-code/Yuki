# CLAUDE.md — cómo se trabaja en este proyecto

Yuki es un ser sintético con una instancia en producción (`yuki-agent`, GCE,
`europe-southwest1`) que habla con personas reales y gasta crédito real. Casi
todo lo que sigue existe porque algo salió mal antes.

## Lo primero: la honestidad no es un estilo, es la especificación

Este proyecto tiene un vicio que lleva años corrigiendo: **aparentar
capacidades**. URLs de un CDN inexistente, titulares inventados con aspecto de
noticia, marcadores presentados como obra, manifiestos que parecían firmados.
La regla, sin excepciones:

- Si algo no se pudo hacer, se dice **qué** falló y **por qué**, con el error
  concreto. Nunca prosa que niegue una capacidad que existe.
- Un resultado simulado se marca `simulated`, y quien lo reciba tiene que poder
  distinguirlo sin leer el código.
- Nada se da por entregado si no consta el adjunto. Nada se da por generado si
  no hay fichero verificado.
- Si el alcance de algo es menor de lo que su nombre sugiere (un manifiesto sin
  firmar, una "cadena" que no es blockchain), se dice en el propio artefacto.

## Invariantes que no se negocian

Romper una de éstas es romper el proyecto, no una prueba:

1. **Un sueño nunca es un recuerdo.** `kind='sueno'` queda fuera de la
   recuperación normal y lleva la marca en el contenido.
2. **Frenar no es enmudecer.** El freno de mano para la iniciativa, los medios
   y la publicación; jamás la respuesta a quien le habla.
3. **Se marca antes de entregar.** Todo material sintético lleva marca de origen
   (Artículo 50, en vigor). Hay una segunda puerta en la entrega por si aparece
   un camino nuevo.
4. **El presupuesto se reserva antes de llamar al proveedor**, no después.
5. **El olvido exige las tres condiciones** (viejo, leve, nunca recuperado) y
   nunca toca canon, síntesis, crecimiento ni lo fijado.
6. **La evolución autónoma no se concede permisos.** Puede ajustar temperatura;
   nunca su propia iniciativa, ni la transparencia, ni el freno.
7. **La bitácora no guarda contenido.** Registra el acto, no lo que tocó.
8. **Que el proceso corra no es que Yuki viva.** Toda sonda distingue signos
   vegetativos (respira) de volitivos (hace cosas suyas). Un panel verde con
   ella parada es un fallo, y tiene nombre: catatonia.

## Mapa

```
src/core/       agente, albedrío (agency, spark, rituals), identidad
                (persona_anchor, transparency, cotejo: lo dicho contra lo
                ejecutado), gobierno (state_registry, blackbox, brake,
                spend_budget, virtual_instance), salud (pulse, registro: el log
                encendido en los puntos de entrada);
                `rutas.py` decide dónde vive cada cosa y `estado_json.py` cómo
                se guarda —atómico, y tolerante a un fichero corrupto—
src/memory/     FTS5 + ciclo de sueño (sleep_cycle)
src/tools/      medios (vertex_media, music_fallback), biblioteca, backup,
                media_jobs, web_search; `criterio_*.py` decide cada arte antes
                de encargarla —música, imagen, vídeo y voz— leyendo su fuente,
                y `criterio_base.py` guarda lo único común: manda la fuente, y
                lo deducido se declara deducido
src/adapters/   Discord (el que importa), Telegram (salida real, sin entrada);
                `encargo.py` traduce el pedido en plan de producción (qué
                piezas, cuántos segmentos, qué indicaciones van al prompt)
src/web/        Salón + /metrics
src/cli/        los comandos por temas (gobierno, mente, operacion); `cli.py`
                en la raíz sólo declara argumentos y reparte
scripts/        smoke_check, chaos_drill, restore_drill, simulate_day,
                virtualize_instance; `_consola.py` es el armazón común
                (paleta, fila de informe, sobre --json, código de salida)
docs/           una guía por subsistema; el mapa está en docs/README.md
                y lo urgente, en OPERACION.md. `docs/historico/` guarda lo que
                describe una decisión de su día y ya no se puede seguir al pie
                de la letra: cada uno lo advierte en su cabecera y dice qué lo
                sustituye
```

## Convenciones de código

- **Comentarios en castellano y explican el porqué**, no el qué. Si un comentario
  se limita a repetir la línea siguiente, sobra. Los buenos aquí cuentan qué
  fallo previno esa decisión.
- Nombres de dominio en castellano (`presupuesto`, `bitacora`, `freno`); API
  pública de clases en inglés cuando ya lo estaba.
- Los módulos nuevos empiezan con un docstring que explica **qué problema real
  resuelve**, no qué hace.
- **Las rutas se piden a `src/core/rutas.py`**, nunca se escriben a mano:
  `base_de_datos()`, `datos("x.json")`, `salida("art")`. La regla es entorno →
  configuración → valor por defecto, y se resuelve **al llamar**, jamás en el
  valor por defecto de un argumento (ése se congela al importar, antes de que
  nadie haya podido reubicar nada). Once módulos lo resolvían por su cuenta y
  no todos igual: la copia respaldaba una base que nadie usaba, el estado vital
  y el perfil de Honcho no entraban en ninguna copia, la auditoría del Artículo
  50 miraba un directorio distinto de aquel donde se escribían los medios, y la
  suite dejaba recuerdos de verdad en la instancia —887 llegó a acumular—.
  Ninguno de esos fallos daba un error.
- **`with sqlite3.connect(...)` no cierra la conexión**: sólo confirma o deshace
  la transacción. Usa `contextlib.closing`. Costó una copia nocturna que moría
  con `FileNotFoundError` una vez de cada treinta y tantas —los `-wal`/`-shm`
  seguían vivos al listar el directorio y ya no al empaquetarlo— y una fuga de
  descriptores en la sonda de métricas, que se lee cada minuto.
- **El estado en JSON se lee y escribe con `estado_json`**, nunca a mano: la
  escritura es atómica (temporal + `os.replace`, porque el proceso muere a mitad
  justo cuando se despliega) y un fichero corrupto devuelve el esquema vacío en
  vez de tumbar la instancia. Siete módulos tenían su propia copia de esas dos
  líneas.
- Cada estado durable nuevo: (1) se declara en `state_registry.build_registry`,
  (2) tiene variable de entorno para reubicarlo, (3) entra en `.gitignore` y
  `.dockerignore`, (4) se aísla en `tests/conftest.py`, (5) se añade a la copia
  de `backup.py` si es irremplazable.

## Pruebas

- Nombres de test en castellano y **descriptivos de la regla**, no de la
  función: `test_frenar_no_es_enmudecer`, no `test_brake_permits`.
- Docstring en las que protegen algo no obvio, contando el fallo que evitan.
- Nada de red ni de proveedores: se inyectan dobles. Una prueba que gaste
  crédito se deja de ejecutar.
- Todo estado va a `tmp_path` — `conftest.py` redirige todas las variables de
  reubicación, `DATABASE_PATH` incluida. Si añades una, aíslala ahí: es lo que
  faltaba el día que la suite dejó 887 recuerdos en la base de la instancia.

```bash
make todo        # linter + suite + simulacro + humo, lo mismo que la CI
make cobertura   # con informe por fichero; el umbral vive en pyproject
```

## Antes de dar algo por terminado

1. `make todo` en verde.
2. Si tocaste medios, presupuesto, memoria o estado: `python3 scripts/chaos_drill.py`.
3. Si añadiste una capacidad: refléjala en `virtual_instance` (capacidad y, si
   procede, limitador) y en el README.
4. Si prometiste una garantía en la documentación, **implementa la operación que
   la cumple**. Ya pasó dos veces: la documentación decía que una fusión de
   memoria era reversible durante siete días y no existía `undo_merge`; y decía
   que una copia sin restaurar no está comprobada mientras nadie restauraba
   ninguna.
5. Si añadiste una métrica o una alerta: comprueba que la alerta nombra una
   métrica que existe. Una alerta rota no falla, **calla**, y eso tranquiliza.
   `tests/test_alertas.py` lo vigila.
6. Si añadiste una clave a `config.yaml`: que la lea alguien, o márcala en su
   línea con `# no se lee: <qué lo gobierna de verdad>`. Un dial que no gira
   engaña a quien lo ajusta y no falla nunca. Había veintisiete.
7. Una prueba nueva sobre algo que importa: **rómpelo a propósito y comprueba
   que la prueba falla**. Dos de las de esta semana pasaban con el fallo dentro
   —y una lo hacía porque el parche de mutación ni siquiera encajaba—.
8. Y que la prueba recorra **el camino del producto**, no la clase suelta. Una
   comprobaba que `VitalState` resolvía bien su ruta mientras el agente le
   pasaba la fija a mano y anulaba el arreglo entero; otra daba por probada
   `execute_autonomous_will` cuando en toda la suite sólo aparecía sustituida
   por un doble.
9. Si añadiste un campo de estado, escribe también quién lo sella. Un campo que
   nadie escribe es peor que no tenerlo: `last_sleep_cycle` estuvo declarado y
   serializado durante meses sin un solo escritor.

## Lo que no se hace

- Publicar sin marcar, generar sin reservar presupuesto, borrar sin recibo.
- Ampliar lo que la evolución autónoma puede tocar.
- Añadir dependencias pesadas al camino de arranque: la instancia es una
  `e2-small` con 2 GB para todo.
- Escribir en `output/` o `data/` desde las pruebas.
- Versionar obra generada. Las reglas de `.gitignore` enumeran extensiones, así
  que un formato nuevo se cuela solo: `tests/test_aislamiento.py` comprueba la
  propiedad —en `output/` no hay nada versionado— en vez de fiarse de la lista.
