# Estado de producción — Yuki

**Verificado:** 2026-09-11 (Europe/Madrid) · limitadores en [`VIRTUALIZACION_Y_MEJORAS.md`](VIRTUALIZACION_Y_MEJORAS.md)

**Proyecto:** `yuki-prod`  
**Instancia:** `yuki-agent` · Compute Engine `e2-small` · `europe-southwest1-a`

## Artefacto activo

| Campo | Valor |
|---|---|
| Repositorio | `europe-southwest1-docker.pkg.dev/yuki-prod/yuki/yuki-agent` |
| Digest desplegado | `sha256:8c6ab9f8563478e5b63c43ec639fd59a7cacf72633f29d38cd0c406015805192` |
| Commit de código | `5db53c5` — integración de las mejoras remotas de producción |
| Build de Cloud Build | `dd05c8b9-0ef6-4c9b-9f1b-77d75a3f8957` |

La VM descarga `:latest` al arrancar, pero esta tabla identifica el artefacto inmutable
que se comprobó dentro de ambos contenedores. No se toman secretos del repositorio: el
arranque los obtiene de Secret Manager y elimina el fichero temporal de runtime al acabar.

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

## Actualización del 11 de septiembre

- `origin/main` no tenía cambios nuevos; se incorporó la rama remota de mejoras
  `claude/virtualizacion-mejoras-proyecto-dik9gg` hasta `47df74c` mediante merge
  `5db53c5`, y el resultado quedó publicado en `origin/main`.
- La integración añade planes de encargo gobernados por la petición, reanudación
  más segura ante fallos de Discord, presupuesto anunciado antes de gastar,
  cotejo entre recibos y prosa, recetas de obra, entrega del Salón y ajustes de
  Honcho/Telegram. No se generaron medios como prueba de despliegue.
- Validación: Ruff correcto, **858 pruebas aprobadas y 2 omitidas**, 12 simulacros
  y circuito de restauración correctos. El humo sobre archivo Git limpio pasó;
  el checkout operativo conserva el hallazgo histórico de archivos generados sin
  marcar y no se modificó ninguna obra.
- Imagen construida desde el repositorio y publicada con digest
  `sha256:8c6ab9f8563478e5b63c43ec639fd59a7cacf72633f29d38cd0c406015805192`.
  El startup script la descargó y recreó ambos contenedores conservando el disco
  persistente, pairing y overlays.
- Verificación posterior: `yuki-daemon` activo, `yuki-salon` saludable, `/health`
  devuelve `200`, Discord conectado a Temple y Dev Server, ruta de producción
  multimedia y pairing pasan dentro del contenedor, y la memoria contiene 85
  recuerdos íntegros.
- Pulso actual: `aletargada` pero sano; el latido es reciente y hay actividad de
  bitácora, aunque el signo de albedrío lleva 37,9 h apagado. No se falseó el
  estado ni se lanzó una generación facturable para maquillar la sonda.

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
