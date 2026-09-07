# Estado de producción — Yuki

**Verificado:** 2026-09-07 (Europe/Madrid)  
**Proyecto:** `yuki-prod`  
**Instancia:** `yuki-agent` · Compute Engine `e2-small` · `europe-southwest1-a`

## Artefacto activo

| Campo | Valor |
|---|---|
| Repositorio | `europe-southwest1-docker.pkg.dev/yuki-prod/yuki/yuki-agent` |
| Digest desplegado | `sha256:2cd2e807bf0a96f9d188b34d52b9b1fa7afa89c93db8e767807ae3f2569c6810` |
| Commit de código | `b6e4d65` — ruta explícita de producción multimedia por DM |
| Build de Cloud Build | `c86e82ab-95d3-4801-957b-cf8586a281c1` |

La VM descarga `:latest` al arrancar, pero esta tabla identifica el artefacto inmutable
que se comprobó dentro de ambos contenedores. No se toman secretos del repositorio: el
arranque los obtiene de Secret Manager y elimina el fichero temporal de runtime al acabar.

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

- La producción multimedia se ejecuta en memoria; un reinicio no reanuda un trabajo ya
  iniciado. Biblioteca conserva los recursos y resultados que sí alcanzaron a guardarse.
- Los errores de proveedor, formato o adjunto se deben comunicar con el fallo concreto.
  No deben convertirse en prosa que niegue capacidades disponibles.
- La generación de vídeo y música consume crédito del proyecto: se ejecuta únicamente
  ante una orden explícita del Productor emparejado.

## Comprobación posterior a un despliegue

1. Confirmar el digest publicado en Artifact Registry.
2. Reiniciar `yuki-agent` para ejecutar su script de arranque y descargar la imagen.
3. Por IAP, confirmar que `yuki-daemon` y `yuki-salon` usan el digest esperado.
4. Comprobar `GET /health` y el log de conexión de Discord.
5. Ejecutar la prueba pura de intención `looks_like_media_delivery_request` con una orden
   breve de canción y vídeo; no generar medios reales como parte de una prueba de humo.
