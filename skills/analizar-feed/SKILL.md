---
name: analizar-feed
description: Rastrea tendencias y noticias culturales en la web usando Firecrawl a través de Nous Portal para inspirar reflexiones nocturnas o composiciones musicales.
parameters:
  type: object
  properties:
    query:
      type: string
      description: Término de búsqueda o corriente cultural a inspeccionar.
      default: "tendencias arte digital musica tradicional"
    limit:
      type: integer
      description: Número máximo de fuentes a extraer.
      default: 4
  required:
    - query
---

# Habilidad: Analizar Feed (`/analizar-feed`)

Permite a **Yuki** examinar el estado de las conversaciones globales y tendencias artísticas de internet de forma no invasiva consumiendo **Firecrawl** en Nous Portal.

## Pasos de Ejecución:

1. **Scraping y Extracción Limpia:**
   - Ejecuta `search_trends_firecrawl` en Nous Portal para obtener contenido en Markdown puro.
2. **Síntesis Contemplativa:**
   - Analiza los resultados bajo la perspectiva de Yuki: ¿cómo se conecta esta corriente con el fluir del tiempo y las artes tradicionales?
3. **Registro en Memoria:**
   - Almacena las conclusiones relevantes en la base de datos SQLite FTS5 bajo la categoría `core` o `project`.
