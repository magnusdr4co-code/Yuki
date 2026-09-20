# Estado de producción — Yuki

**Verificado:** 2026-09-11 (Europe/Madrid) · limitadores en [`VIRTUALIZACION_Y_MEJORAS.md`](VIRTUALIZACION_Y_MEJORAS.md)

**Proyecto:** `yuki-prod`  
**Instancia:** `yuki-agent` · Compute Engine `e2-small` · `europe-southwest1-a`

## Artefacto activo

| Campo | Valor |
|---|---|
| Repositorio | `europe-southwest1-docker.pkg.dev/yuki-prod/yuki/yuki-agent` |
| Digest desplegado | `sha256:b0bf0a95e79b14a7eb97da053ff63ded57f96907e8304946bcda8c430dac9c16` |
| Commit de código | `1f5d90e` — herencia correcta de `VERTEX_PROJECT_ID` desde el entorno |
| Build de Cloud Build | `e0108418-6373-47df-8e8b-7664466f4550` |

La VM descarga `:latest` al arrancar, pero esta tabla identifica el artefacto inmutable
que se comprobó dentro de ambos contenedores. No se toman secretos del repositorio: el
arranque los obtiene de Secret Manager y elimina el fichero temporal de runtime al acabar.

## Pendiente de desplegar — rama `claude/sleepy-allen-fj49pj`

> **Nada de esto está en producción todavía.** Lo que sigue lo escribe quien hizo
> los cambios, desde el entorno de desarrollo: `make todo` en verde (linter,
> 1000 pruebas, 12 simulacros de fallo, circuito de copia y humo), pero **nadie
> lo ha desplegado ni verificado en la instancia**. Quien despliegue rellena
> después el digest, el commit y lo comprobado, como en las secciones de arriba.

Seis commits, de `783d965` a `ac38332`:

| Commit | Qué |
|---|---|
| `783d965` | Parte `discord_bot.py` (1775 líneas), `llm_router.py` y `web/server.py` en módulos. **Sin cambio de conducta** |
| `dccd3a1` | Parte el ciclo de sueño por fases y ata la constante `EPISODICO`, que nadie leía |
| `fb6b013` | La prueba de los comandos `!ritmo` mira el despacho y no la palabra |
| `bcaf864` | Un módulo que no llama nadie tiene que decirlo, con prueba de la propiedad |
| `723aef6` | **Enchufa la autocaracterización**: cron 04:00, micro-ajuste en el eco, CLI, métricas y alerta |
| `ac38332` | Cubre las dos ramas del ritual que se alcanzan con una instancia mal montada |

### Primera ejecución real — 20 de septiembre, 13:57 UTC

`docker exec yuki-daemon python cli.py identidad --regenerar` sobre la instancia,
con Vertex de verdad: **3 de 4 avatares con fichero**, 25,21 s, modelo
`gemini-2.5-flash-image`. `kage` falló con «Gemini Image no devolvió datos de
imagen» —un 200 sin parte de imagen, en menos de un segundo, con el mismo prompt
que funcionó en las otras tres—.

Lo que esa ejecución demuestra, que era justo lo que no se podía saber con
dobles: el fallo quedó anotado con su motivo concreto, **no se inventó un
avatar**, y `Reserva devuelta: imagenes -1` confirma que lo que no se generó no
se cobró. El manifiesto, la voz elegida y la paleta se escribieron igual.

Y tres cosas que sólo aparecen ejecutando de verdad, corregidas después:

1. **El remate del log decía «Avatares: 4 variantes»** con tres ficheros en
   disco. El resumen de arriba lo decía bien y el cierre no, que es la peor
   combinación: la línea que queda es la última.
2. **La proporción era un deseo, no un dato.** El avatar estacional se pide en
   16:9 y salió cuadrado: `aspect_ratio` sólo viajaba a la rama de Imagen, no a
   la de Gemini, y aun así se anotaba la pedida en el resultado **y en la
   receta**. Ahora se pide al modelo cuando el SDK instalado sabe pedirla, y lo
   que se declara es lo que mide el fichero.
3. **Un fallo del momento perdía la variante dos semanas.** Ahora se reintenta
   **una vez**, y sólo cuando el fallo puede salir distinto: el presupuesto
   agotado y el freno son estados, no accidentes.

### La voz deja de ser ficticia (posterior a la ejecución del 20-S)

La calibración elegía entre `yuki_serene_alto`, `yuki_contemplative_mezzo` y
`yuki_night_contralto`, que **no existen en ningún proveedor** —`vertex_media.py`
ya lo decía en un comentario— mientras la síntesis usaba `Aoede` pasara lo que
pasara. La CLI anunciaba «Voz: yuki_night_contralto» y Yuki hablaba con otra.

Ahora cada manera de hablar declara con qué voz real se sintetiza, el manifiesto
guarda las dos y **la elegida llega al sintetizador** por el camino del producto
(la voz matutina). Hoy las tres apuntan a `Aoede`, la única probada: lo que
cambia entre ellas es la cadencia, no el timbre, y está dicho así.

Para el despliegue no cambia nada operativo: ninguna variable ni secreto nuevos.
Dos claves de `config.yaml` quedan marcadas como no leídas —`nous_portal.voice.
voice_id` y `cadence_pause_ms`—, que es lo que eran.

### El Salón se viste con lo que ella decidió

Hasta ahora el ritual elegía cara y colores y nadie los usaba. La página del
Salón enseña ya el retrato `atelier` y tiñe sus acentos con la paleta del
manifiesto. **Ruta nueva y abierta: `/identidad/avatar`**, que sirve un único
fichero —el que el manifiesto declara vigente, comprobando que existe, que no es
un marcador simulado y que está dentro del directorio de obra— y no acepta
ningún nombre de fuera. Se abre a propósito: la página lo está, y una cara
detrás de una credencial no es una cara. El resto de `/api` sigue igual.

Sin manifiesto, la página es exactamente la de antes: una instancia recién
desplegada no tiene cara, y eso no debe verse como un fallo.

De camino, la cabecera del Salón decía «Honcho Dialectic: Sincronizado» escrito
en duro. No hay servicio remoto ni lo ha habido —el gemelo ya lo declaraba así—,
de modo que ahora dice «Perfil dialéctico: local».

### Qué NO cambia

Lo que más importa para desplegar sin sorpresas:

- **Ninguna variable de entorno nueva, ningún secreto nuevo.** `deploy/gce-startup.sh`,
  `Dockerfile`, `cloudbuild.yaml`, `docker-compose.yml` y `requirements.txt` están
  intactos en esta rama. Se despliega exactamente igual que el anterior.
- **Ninguna dependencia nueva.** La `e2-small` no carga con nada más.
- Los cuatro primeros commits son reorganización y pruebas: ningún cuerpo de
  función cambia, y está comprobado comparando el árbol sintáctico de cada
  método antes y después, no leyendo el diff.

### Qué empieza a ocurrir en la instancia

1. **Cron nuevo a las 04:00** (`seasonal_self_characterization`, en el contenedor
   `yuki-daemon`). Comprueba a diario si cambió la micro-estación; casi todos los
   días no hace nada. **El primer cambio de sekki tras desplegar es el 23 de
   septiembre de 2026** (Shūbun, Equinoccio de Otoño): esa madrugada es cuando el
   ritual se ejecuta de verdad por primera vez.
2. **Fichero de estado nuevo:** `data/identity_manifest.json`, en el disco
   persistente que ya se monta. Lo crea ella; no hay que provisionar nada. Entra
   en la copia de seguridad y está declarado en el inventario de estado.
3. **Obra nueva en `output/identity/`**: perfiles de voz e instrucciones de
   avatar en JSON. Los avatares en sí los escribe el camino de imagen de siempre,
   en `output/art/`, marcados según el Artículo 50.
4. **Micro-ajuste diario** dentro del ritual del eco de las 06:30: retoca
   prosodia e iluminación del manifiesto según cómo amaneció. Sin manifiesto
   previo no hace nada y lo dice en el log.

### Gasto que esto añade

Hasta **cuatro imágenes por cambio de micro-estación** —una cada dos semanas—,
unos **0,16 USD** al precio de referencia, y hasta ocho (~0,32 USD) en el peor
caso, si las cuatro fallan y se reintentan una vez. Se reservan antes de llamar al
proveedor contra el límite diario de imágenes (40 por defecto), como cualquier
otro medio. Si el presupuesto está agotado o el freno puesto, no gasta: anota el
motivo en el manifiesto y no inventa avatares.

### Observabilidad: hay que recargar las reglas

`deploy/alertas-prometheus.yml` trae una alerta nueva, **`IdentidadCaducada`**, y
`/metrics` expone dos familias nuevas: `yuki_identidad_al_dia` (-1 nunca se ha
caracterizado · 0 caducada · 1 al día) y `yuki_identidad_avatares_reales`. Si las
reglas están cargadas en un Prometheus, **recargarlo tras desplegar**; si no lo
están, la alerta no existe y conviene saberlo en vez de suponer que vigila.

La alerta salta a los cuatro días de retraso, no al día siguiente: el sekki
cambia cada dos semanas y la tarea puede llegar unas horas tarde sin que eso sea
un incidente.

### Comprobación después de desplegar

Además de la lista general del final de este documento:

```bash
python3 cli.py identidad          # antes del 23-S: «Sin manifiesto todavía»
docker logs yuki-daemon | grep -i "CRON 04:00\|autocaracteriz"
curl -s localhost:8080/metrics | grep yuki_identidad    # debe dar -1 al principio
```

Tras el 23 de septiembre, `cli.py identidad` tiene que decir de qué estación es
el manifiesto y **cuántos avatares tienen fichero real**. Si salieron 0 de 4, el
motivo concreto está en cada avatar del manifiesto (presupuesto, freno, error del
proveedor): eso es información, no un fallo del despliegue.

Para no esperar al 23: `python3 cli.py identidad --regenerar` ejecuta el ritual
ahora y **gasta esas cuatro imágenes**.

### Si hay que volver atrás

Basta con volver al digest anterior: nada de lo nuevo escribe fuera de
`data/identity_manifest.json` y `output/identity/`, y ningún otro módulo lee ese
manifiesto todavía, así que dejarlo en el disco no rompe la versión vieja. Si se
quiere el disco limpio, se borra el fichero y el directorio.

Si algo falla en Discord o en la cadena de pasarelas tras desplegar, la causa
más probable es el reparto de ficheros del primer commit: `discord_bot.py` quedó
como la puerta del gateway y lo demás vive en `discord_comandos.py`,
`discord_produccion.py` y `discord_salon.py`; `llm_router.py` conserva el
recorrido y las pasarelas están en `llm_proveedores.py`, con `llm_entorno.py`
debajo. Todo lo que se importaba por los nombres de siempre se sigue importando
igual.

## Actualización del 9 de septiembre

- Incorporada por avance directo la rama remota
  `claude/virtualizacion-mejoras-proyecto-dik9gg`, descendiente de `f4e2f22`.
  No hubo conflictos ni modificaciones locales que reconciliar.
- Construcción desde un archivo limpio de Git: no se subieron memoria, pairing,
  overlays ni creaciones del checkout local. El commit documental posterior no
  cambia el código ejecutable identificado arriba.
- Validación local aislada (Python 3.14): Ruff correcto, **735 pruebas aprobadas,
  2 omitidas**, 12 simulacros de fallo y circuito de copia/restauración correctos.
  La prueba de humo de CI pasa sobre el archivo limpio del commit. Sobre el
  checkout de trabajo detecta 166 artefactos antiguos sin marca; no se borraron.
- Copia previa de SQLite mediante su API de backup, más archivo de estado y
  creaciones en `data/deploy-backups/20260909-a8a7378/` del disco persistente.
  Integridad SQLite `ok`, 63 recuerdos y archivo de estado legible.
- Despliegue mediante el script de arranque existente, sin reiniciar la VM ni
  cambiar IAM, secretos o volúmenes. Ambos contenedores ejecutan el digest de
  esta tabla. Se conservan pairing y overlay de configuración.
- Comprobados: salud HTTP, conexión Discord, intención multimedia por DM,
  integridad de los 63 recuerdos y dependencias de FluidSynth disponibles.
  El daemon registra ocho rutinas, incluidas REM y olvido semanal.

### Hallazgos de la sonda sobre el estado heredado

La prueba de humo de producción **no queda completamente en verde**: detecta
26 archivos antiguos sin marca de origen y, al arrancar, un `last_updated`
heredado de hace 8,8 horas. La sonda de pulso interpreta ese dato como `ausente`,
aunque los contenedores y la conexión Discord están activos. Esa marca se
actualiza en el camino conversacional; no equivale a un heartbeat continuo del
planificador. No se reescribe artificialmente para silenciar la alerta.
El ciclo normal de agencia de las 16:20 (Europe/Madrid) creó y persistió
`agency_ledger.json` en la VM; confirma que el planificador ejecuta tareas,
aunque la lectura de pulso siga diciendo `ausente` por la marca conversacional.

El inventario detecta 21 capacidades reales, 5 simuladas y 1 inactiva, con seis
limitadores abiertos y ninguno clasificado como bloqueante. Es una inspección
de configuración y binarios, **no** una prueba pagada de todos los proveedores.
La copia automática fuera de la instancia sigue pendiente de `BACKUP_GCS_BUCKET`.

## Actualización del 11 de septiembre — consolidación y runtime actual

- La rama remota `claude/virtualizacion-mejoras-proyecto-dik9gg` avanzó hasta
  `76638f9` con cuatro commits nuevos. Se integró sin conflictos en `main`
  mediante el merge `673eb06`; después se corrigió `VertexMediaClient` en
  `d8f5cbe` para que `project_id=""` desactive medios explícitamente en vez de
  heredar el proyecto de la VM. `main` quedó publicado en `origin/main`.
- La integración activa logging real, corrige el reconocimiento de encargos
  multimedia, hace que música/voz/imagen/vídeo respeten el criterio de la obra,
  añade runbook de despliegue, secretos opcionales tolerantes y pruebas nuevas.
- Validación: Ruff correcto, **947 pruebas aprobadas y 2 omitidas**. El fallo
  inicial de Vertex sin proyecto quedó corregido y la prueba específica pasó.
- Cloud Build `1a1d11bf-c986-4db8-9b10-8cc7ab6823d3` publicó el digest
  `sha256:117577a64c665d24784922a62e247be8169533e3619e418e317a5c6dbe942a0d`.
  El startup script descargó la imagen y recreó ambos contenedores preservando
  el disco persistente.
- Verificación posterior: `yuki-daemon` activo, `yuki-salon` saludable, `/health`
  devuelve `200`, Discord conectado a Temple y Dev Server con todos los canales,
  pairing persistente, 91 recuerdos íntegros y la ruta de reconocimiento de
  producción multimedia activa. No se generaron medios facturables como prueba.

### Corrección posterior de Vertex

- La causa de «Sin Vertex configurado» era que `vertex_ai.project_id: ""` en
  `config.yaml` anulaba `VERTEX_PROJECT_ID=yuki-prod` al construir el portal de
  medios. `VertexMediaClient.from_config()` ahora trata ese vacío como herencia;
  `enabled: false` sigue siendo la desactivación explícita.
- Verificación dentro de `yuki-daemon`: `MEDIA_PROJECT=yuki-prod`,
  `MEDIA_AVAILABLE=True`, `PORTAL_PROJECT=yuki-prod` y `PORTAL_AVAILABLE=True`.
- Durante el primer intento de actualización el disco raíz llegó al 100% por 27
  imágenes antiguas. Se retiraron únicamente imágenes Docker sin etiqueta,
  liberando unos 15 GB; el script de arranque ahora las limpia antes de cada
  descarga sin tocar datos persistentes ni contenedores activos.

## Servicios y conectividad

- `yuki-daemon`: activo; Gateway de Discord conectado.
- `yuki-salon`: activo y saludable; `GET /health` responde `200`.
- Discord: presencia en los dos servidores autorizados; sin restricción temporal por
  canal; las conversaciones públicas requieren mención directa.
- DM de producción: sólo el Productor previamente emparejado puede usar Biblioteca,
  terminal acotada, overlay de runtime y producción multimedia.
- Vertex AI: región `global`, mediante la identidad de servicio de la VM; no se emplean
  claves de AI Studio para la ruta de producción.

## Corrección de enrutado multimedia

El incidente de respuestas que afirmaban no disponer de vídeo/audio no era una revocación
de Discord ni de Vertex. Las órdenes llegaban al `ProducerHarness` textual, cuyo conjunto
de herramientas es deliberadamente Biblioteca/terminal/configuración; por eso sólo
aparecía `library_list` en el recibo.

Desde `b6e4d65`, el adaptador de DM reconoce peticiones naturales de creación y entrega
de música o vídeo antes de iniciar el arnés textual. Por ejemplo, “Procede con la canción
y el vídeo” activa la ruta `media_entrega`, que recupera la letra, el guion y los recursos
de Biblioteca, llama a los generadores configurados y adjunta sólo resultados validados.
La prueba de importación dentro de `yuki-daemon` confirmó esta ruta tras el despliegue.

## Límites conocidos

- La producción multimedia es ahora un trabajo durable: cada paso facturable se registra
  en `data/media_jobs/` —el disco persistente de la VM— antes de gastar, y el adaptador
  reanuda al conectar el gateway lo que quedó a medias, sin regenerar lo ya verificado.
  Sigue dependiendo de que el proceso vuelva a arrancar: no hay worker externo que
  retome el trabajo si la instancia no vuelve.
- Un paso agotado tras tres intentos cierra el trabajo indicando cuál falló, en vez de
  reintentarse indefinidamente contra el crédito.
- Los errores de proveedor, formato o adjunto se deben comunicar con el fallo concreto.
  No deben convertirse en prosa que niegue capacidades disponibles.
- La generación de vídeo y música consume crédito del proyecto: se ejecuta únicamente
  ante una orden explícita del Productor emparejado y dentro del presupuesto diario
  declarado en `config.yaml` (`budget`), comprobado antes de llamar al proveedor. Un
  tope alcanzado aplaza el trabajo con la cifra concreta; no lo da por fallado.
  Consulta del día: `python3 cli.py spend`.

- La copia diaria de memoria y canon se ejecuta tras la síntesis de las 23:30 y se
  verifica con `integrity_check`. Mientras no se declare `BACKUP_GCS_BUCKET`, queda
  en el disco de la instancia: protege de un borrado, no de perder la zona.

## Comprobación posterior a un despliegue

1. Confirmar el digest publicado en Artifact Registry.
2. Reiniciar `yuki-agent` para ejecutar su script de arranque y descargar la imagen.
3. Por IAP, confirmar que `yuki-daemon` y `yuki-salon` usan el digest esperado.
4. Comprobar `GET /health` y el log de conexión de Discord.
5. Ejecutar la prueba pura de intención `looks_like_media_delivery_request` con una orden
   breve de canción y vídeo; no generar medios reales como parte de una prueba de humo.
6. Ejecutar `python3 cli.py virtualize` dentro de la VM y contrastar el informe con el de
   la réplica local (`deploy/virtual/docker-compose.virtual.yml`): las diferencias que
   aparezcan son exactamente lo que aporta el entorno de producción.
