---
name: consultar-memoria
description: Realiza una búsqueda de alta velocidad en el motor SQLite FTS5 por términos clave o categorías, mostrando recuerdos indexados, snippets y latencia de recuperación.
parameters:
  type: object
  properties:
    query:
      type: string
      description: Término de búsqueda o frase a consultar en la memoria.
    category:
      type: string
      description: Filtrar por categoría ("core", "project", "producer", "visitor", "daily_synthesis").
      default: ""
    limit:
      type: integer
      description: Número máximo de recuerdos a recuperar.
      default: 5
  required:
    - query
---

# Habilidad: Consultar Memoria (`/consultar-memoria`)

Permite inspeccionar directamente los recuerdos almacenados en la base de datos de Yuki para comprobar la precisión y velocidad del motor FTS5.

## Pasos de Ejecución:

1. **Ejecución de Consulta BM25:**
   - Invoca el método `search` de `FTS5MemoryEngine` con ranking híbrido y decaimiento temporal.
2. **Generación de Snippets:**
   - Extrae fragmentos resaltados con `snippet(memories_fts)`.
3. **Reporte:**
   - Muestra los recuerdos encontrados, puntuación de relevancia y tiempo de búsqueda en milisegundos.
