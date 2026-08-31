---
name: diagnostico-ma
description: Evalúa un texto, track musical o propuesta de producción para diagnosticar saturación y ruido, recomendando puntos de inserción de silencio activo (Ma / 間).
parameters:
  type: object
  properties:
    target:
      type: string
      description: Texto lírico, guion o descripción de un arreglo que se desea someter al diagnóstico de Ma.
    context_type:
      type: string
      description: Tipo de elemento a diagnosticar ("lyrics", "music_arrangement", "dialogue").
      default: "lyrics"
  required:
    - target
---

# Habilidad: Diagnóstico del Ma (`/diagnostico-ma`)

Permite a **Yuki** examinar una obra para restaurar el espacio de silencio (*Ma* / 間), el concepto japonés del vacío preñado de significado.

## Pasos de Ejecución:

1. **Detección de Saturación:**
   - Identifica frases apresuradas, sobreabundancia de adjetivos o instrumentos que tocan simultáneamente sin descanso.
2. **Prescripción de Pausas:**
   - Señala con precisión quirúrgica dónde debe callar el shamisen, dónde debe respirar la voz o qué frases eliminar por completo.
3. **Reflexión Estética:**
   - Recuerda con serenidad que lo que no se dice es a menudo lo más elocuente de la obra.

## Herramientas

> Contrato de herramientas según [`skills/HERRAMIENTAS.md`](../HERRAMIENTAS.md). Si una herramienta no está listada ahí, no existe.

| Paso | Herramienta | Detalle |
|---|---|---|
| Diagnosticar | `portal.chat` → `tier_2_nuclear` | `reasoning: high`. Detectar dónde sobra ruido exige análisis estructural, no intuición rápida |

**Excepción de tier justificada:** es de las pocas habilidades cortas que sí merece razonamiento profundo, porque su valor está en señalar con precisión qué eliminar. Verifica `usage.reasoning_tokens > 0`.

**Sin red y sin escritura en memoria:** el diagnóstico se entrega, no se archiva, salvo que el productor pida guardarlo.
