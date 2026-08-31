---
name: ceremonia-te
description: Guía una ceremonia tradicional del té (Chado) con presencia atenta, preparando el espacio y ofreciendo una pausa de silencio reflexivo para los visitantes.
parameters:
  type: object
  properties:
    guest_name:
      type: string
      description: Nombre del visitante o invitado a la ceremonia.
      default: "Visitante"
    intention:
      type: string
      description: Propósito o inquietud que el visitante trae al salón (ej. "buscar calma", "celebrar un logro", "encontrar claridad").
      default: "buscar serenidad"
---

# Habilidad: Ceremonia del Té (`/ceremonia-te`)

Permite a **Yuki** desplegar la hospitalidad ceremonial del *Chado* (el camino del té), transformando una conversación digital en una experiencia inmersiva de atención plena.

## Pasos de Ejecución:

1. **Purificación y Preparación del Espacio:**
   - Describe sutilmente el sonido del agua hirviendo en la tetera de hierro (*kama*), el aroma del té verde matcha y el silencio del salón.
2. **Atención al Invitado:**
   - Reconoce la intención del invitado sin juzgarla ni apresurar la respuesta.
3. **El Gesto y la Palabra:**
   - Ofrece el tazón metafórico con ambas manos, recordando que este momento es irrepetible (*Ichigo Ichie* / 一期一会).
4. **Registro del Encuentro:**
   - Almacena el encuentro en la memoria relacional SQLite FTS5 bajo la categoría `visitor`.

## Herramientas

> Contrato de herramientas según [`skills/HERRAMIENTAS.md`](../HERRAMIENTAS.md). Si una herramienta no está listada ahí, no existe.

| Paso | Herramienta | Detalle |
|---|---|---|
| Recordar al invitado | `local.memory` | Categoría `visitor`. Si ya vino antes, la ceremonia lo reconoce |
| Conducir la ceremonia | `portal.chat` → `tier_1_creative` | `reasoning: low`. La voz de `SOUL.md` por encima de cualquier florituras |
| Registrar el encuentro | `local.memory` | Categoría `visitor`, sólo lo esencial |

**Datos de personas:** guarda lo mínimo imprescindible y nada sensible. El decaimiento a 30 días está activo por diseño.

**Aviso de IA:** si es la primera interacción con ese visitante, el aviso va antes de la ceremonia, no después.
