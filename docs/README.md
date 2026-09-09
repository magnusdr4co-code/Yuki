# Índice de la documentación

Veinte documentos, cuatro mil líneas, y hasta ahora ningún mapa. `CLAUDE.md`
decía «empieza por OPERACION.md» y ahí se acababa la orientación: el resto había
que descubrirlo abriendo ficheros hasta dar con el que respondía.

Esto dice **qué pregunta contesta cada uno**, y separa lo que describe la
instancia de hoy de lo que dejó escrito una decisión de ayer. Un documento
histórico no sobra —el registro de por qué algo se hizo así vale— pero leerlo
como si fuera el presente es de donde salen las medias horas perdidas.

## Si algo va mal ahora mismo

| Pregunta | Documento |
|---|---|
| Está desplegado y algo falla | [OPERACION.md](OPERACION.md) — CI, humo, métricas, bitácora, freno, simulacro, restauración, signos vitales |
| Todo verde y no hace nada | [OPERACION.md §8](OPERACION.md) (signos vitales) y [LIBRE_ALBEDRIO.md §6](LIBRE_ALBEDRIO.md) (censo de ciclos) |
| Qué puede y qué no puede esta instancia | [VIRTUALIZACION_Y_MEJORAS.md](VIRTUALIZACION_Y_MEJORAS.md) — gemelo virtual y limitadores L1–L11 |
| En qué estado está producción | [PRODUCTION_STATUS.md](PRODUCTION_STATUS.md) |

## Cómo funciona por dentro

| Tema | Documento |
|---|---|
| Arquitectura y flujos | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Memoria rápida y por qué FTS5 | [FAST_MEMORY_FTS5.md](FAST_MEMORY_FTS5.md) |
| Dormir: consolidar, soñar, olvidar | [CICLO_DE_SUENO.md](CICLO_DE_SUENO.md) |
| Iniciativa propia: carácter, refuerzo, ritmos | [LIBRE_ALBEDRIO.md](LIBRE_ALBEDRIO.md) |
| Tareas autónomas y cron | [AUTONOMOUS_CRON.md](AUTONOMOUS_CRON.md) |
| Personalidad dialéctica (Honcho) | [HONCHO_DIALECTIC.md](HONCHO_DIALECTIC.md) |
| Generación de medios | [NOUS_PORTAL_TOOLS.md](NOUS_PORTAL_TOOLS.md) |
| El DM del Productor | [PRODUCER_HARNESS.md](PRODUCER_HARNESS.md) |

## Quién es y qué debe declarar

| Tema | Documento |
|---|---|
| Qué es Yuki y cómo se sostiene su identidad | [IDENTIDAD_SINTETICA.md](IDENTIDAD_SINTETICA.md) |
| Voz, estética y presencia | [SOUL_GUIDE.md](SOUL_GUIDE.md) · el canon está en [`SOUL.md`](../SOUL.md) |
| Artículo 50: declararse y marcar lo que genera | [TRANSPARENCIA_AI_ACT.md](TRANSPARENCIA_AI_ACT.md) |
| Qué dice la literatura de 2026 y qué se adoptó | [ESTADO_DEL_ARTE_2026.md](ESTADO_DEL_ARTE_2026.md) |

## Desplegar

| Tema | Documento |
|---|---|
| Google Cloud, de cero | [GCP_DEPLOYMENT.md](GCP_DEPLOYMENT.md) |
| Otras opciones (VPS, Docker, Modal) | [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) — alternativas estudiadas; **la instancia real corre en GCE**, no en ninguna de ellas |

## Registro de decisiones

Vive aparte, en [`historico/`](historico/README.md), y ya no en esta lista: un
documento que describe una decisión de su día no debería aparecer junto a los
que se pueden seguir al pie de la letra hoy. La tabla de allí dice, para cada
uno, **qué lo sustituye** — un histórico sin puntero al presente es un callejón.

Están la propuesta de infraestructura y su plan por fases, el encargo de
aterrizar Yuki en Google Cloud y el informe que respondió por qué el crédito no
se consumía.

---

`tests/test_documentacion.py` comprueba que los comandos, guiones, módulos y
ficheros de despliegue que se citan aquí **existan**. No comprueba que hagan lo
que prometen —de eso se ocupa el resto de la suite—, pero sí evita el fallo que
ya ocurrió: el README mandó durante meses ejecutar `cli.py media-test`, pendiente
desde siempre porque nunca llegó a existir. Una documentación que miente no
falla, engaña, y se
descubre justo cuando alguien la sigue al pie de la letra porque algo se ha roto.
