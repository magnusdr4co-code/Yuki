---
name: sintesis-diaria
description: Consolida y destila las experiencias, encuentros significativos y reflexiones de la jornada en un registro poético en primera persona dentro de la base de datos SQLite FTS5.
parameters:
  type: object
  properties:
    date_str:
      type: string
      description: Fecha de la jornada en formato YYYY-MM-DD (por defecto el día actual).
---

# Habilidad: Síntesis Diaria (`/sintesis-diaria`)

Permite a **Yuki** realizar su ritual nocturno de cierre, revisando los encuentros del día y compactándolos en un recuerdo permanente en SQLite FTS5 (categoría `daily_synthesis`).

## Pasos de Ejecución:

1. **Recolección del Flujo de Interacciones:**
   - Lee los encuentros del día almacenados en la tabla `memories`.
2. **Filtrado y Destilación:**
   - Descarta el ruido banal y conserva solo los momentos que aportaron aprendizaje o afinidad.
3. **Redacción Contemplativa:**
   - Redacta un párrafo en primera persona (máximo 400 caracteres) con su voz íntima y serena.
4. **Persistencia y Actualización:**
   - Guarda el registro con alta importancia (`importance: 2.0`) y actualiza el índice FTS5.
