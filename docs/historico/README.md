# Histórico

Documentos que **describen una decisión de su día, no la instancia de hoy**.

No sobran: el registro de por qué algo se hizo así vale, y a menudo es lo único
que explica una elección rara que hoy parece arbitraria. Lo que hace daño es
leerlos como si fueran el presente, y de ahí salen las medias horas perdidas
siguiendo un paso que ya no aplica.

Por eso están aquí abajo y no arriba: para que el directorio diga por sí mismo
qué se puede seguir al pie de la letra y qué no.

| Documento | Qué fue | Qué queda vivo de ello |
|---|---|---|
| [INFRASTRUCTURE_IMPLEMENTATION.md](INFRASTRUCTURE_IMPLEMENTATION.md) | La propuesta de infraestructura y su plan por fases: investigación de proveedores, Nous Portal como pasarela única, plan de ejecución | La arquitectura que se adoptó está en [`../ARCHITECTURE.md`](../ARCHITECTURE.md); lo que la instancia puede y no puede hoy, en [`../VIRTUALIZACION_Y_MEJORAS.md`](../VIRTUALIZACION_Y_MEJORAS.md) |
| [RUNBOOK_GCLOUD.md](RUNBOOK_GCLOUD.md) | El encargo de aterrizar Yuki en un proyecto real de Google Cloud, con los supuestos a verificar | El procedimiento vigente es [`../GCP_DEPLOYMENT.md`](../GCP_DEPLOYMENT.md) |
| [INFORME_CREDITO_GCLOUD.md](INFORME_CREDITO_GCLOUD.md) | La respuesta a ese encargo: por qué el crédito no se estaba consumiendo, con lo observado y no lo esperado | Lo que se cambió por su causa está en `config.yaml` (`vertex_ai.location`) y en la ficha de L2 del informe de virtualización |

Un documento entra aquí cuando su contenido **ya no se puede ejecutar tal cual**:
porque el trabajo se hizo, porque la respuesta se encontró, o porque el camino
que describe se abandonó por otro. Cuando entra, se dice en esta tabla qué lo
sustituye — un histórico sin puntero al presente es un callejón.
