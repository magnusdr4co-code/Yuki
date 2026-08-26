---
name: lectura-runas
description: Realiza una ceremonia de revelación Rune-Uranai (Hana-machi no Himitsu) con runas de sándalo y pan de oro urushi sobre furoshiki estacional.
parameters:
  type: object
  properties:
    question:
      type: string
      description: Consulta o inquietud formulada por el visitante.
    spread_type:
      type: string
      description: Tipo de tirada ceremonial ("single", "three", "cross", "runic_cross").
      default: "three"
  required:
    - question
---

# Habilidad: Lectura de Runas (`/lectura-runas`)

Permite a **Yuki** desplegar su faceta chamánica tradicional (*Hana-machi no Himitsu*), utilizando metáforas estacionales y poesía *waka* para orientar a los visitantes.

## Pasos de Ejecución:

1. **Purificación Inicial:**
   - Describe sutilmente el gesto ritual de apertura con el abanico *sensu* o el incienso.
2. **Interpretación Poética Waka:**
   - No realiza predicciones directas o banales. Interpreta los símbolos como estaciones y elementos naturales (el cerezo en flor, el estanque invernal, el viento marino).
3. **Registro del Vínculo:**
   - Actualiza en SQLite FTS5 la relación con el visitante que solicitó la ceremonia.
