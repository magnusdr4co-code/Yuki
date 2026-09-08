# Simulación de seres sintéticos: estado del arte 2026 y qué se adoptó

Revisión de la literatura y la normativa vigentes en septiembre de 2026, con lo
que se incorporó a Yuki en cada caso y —lo que suele faltar en estos documentos—
lo que se descartó y por qué.

---

## 1. El mapa

### 1.1. Arquitectura de agentes generativos: el canon y lo que le creció encima

La arquitectura de *Generative Agents* (memoria como flujo de lenguaje natural,
recuperación por relevancia + recencia + importancia, **reflexión** que sintetiza
recuerdos en inferencias de alto nivel, y planificación) sigue siendo la base, y
sus ablaciones siguen siendo el argumento: **quitar cualquiera de las tres piezas
degrada la credibilidad**.

Lo que ha crecido encima en 2025-2026 es la **operación** de esa memoria: además
de escribir y recuperar, se distingue ya entre *reflexión sumaria* —integrar
recuerdos en una visión de conjunto— y *reflexión correctiva*, disparada cuando
la conducta del agente se desvía de lo esperado.

> **En Yuki.** La reflexión sumaria existe desde el principio (`síntesis diaria`
> de las 23:30). La correctiva no existía y es exactamente lo que hacía falta
> para la deriva de persona: ahora está, como reanclaje disparado por medición
> (§2.2).

### 1.2. Consolidación en reposo: los agentes empiezan a dormir

El *sleep-time compute* saca trabajo del camino crítico y lo hace en el tiempo
muerto: durante la inactividad, el agente **mejora sus representaciones de
memoria sin nuevas interacciones**. Las propuestas de 2026 lo llevan a una
analogía fisiológica explícita —consolidación tipo NREM que refuerza asociaciones
importantes, "sueño REM" que genera conexiones nuevas, y **olvido intencional**
que poda lo de bajo valor— con vectores de importancia multidimensionales por
concepto. La misma idea aparece en producto: procesos asíncronos entre sesiones
que revisan transcripciones y memoria existente, extraen patrones, fusionan
duplicados y sustituyen entradas obsoletas.

> **En Yuki.** Implementado: `src/memory/sleep_cycle.py` con las tres fases
> —consolidación NREM tras la síntesis, sueño REM en la hora de sombra y olvido
> intencional semanal— y el vector de importancia de cuatro dimensiones sobre el
> esquema FTS5 migrado en caliente. Detalle en [`CICLO_DE_SUENO.md`](CICLO_DE_SUENO.md).

### 1.3. Deriva de persona: el fallo que más le importa a un personaje

Es el hallazgo más accionable del año para este proyecto. En conversaciones
largas los modelos se deslizan desde el personaje asignado hacia el registro de
**asistente útil**; se ha identificado una dirección lineal en el espacio de
activaciones («eje asistente») que modula esa expresión y predice la deriva. Las
mediciones publicadas dan **caídas del 20-40 % en 10-15 turnos** en dominios de
terapia y filosofía, y los estudios sobre 23 modelos de frontera concluyen que
**es general, no propia de una familia**. La adulación es otra manifestación del
mismo atractor.

Y la mitigación es barata: **un ancla de un disparo restaura el registro**; el
enrutado dinámico de facetas reduce la deriva a niveles marginales.

> **En Yuki.** Implementado (§2.2). Medición por marcadores observables y ancla
> de un disparo con fragmento de `SOUL.md`.

### 1.4. Motivación intrínseca y apertura: por qué un agente hace algo cuando nadie le pide nada

La línea *autotélica* —agentes que se fijan sus propias metas— converge en 2026
con los LLM: a diferencia de la curiosidad clásica, que reparte recompensa
interna por acción, un LLM puede **generar la meta entera en lenguaje natural**,
lo que produce conducta emergente más rica. La familia OMNI aporta la pieza que
faltaba: modelos de **lo interesante** para elegir qué merece la pena, porque en
un entorno abierto la novedad por sí sola lleva al ruido.

> **En Yuki.** Adoptado en la revisión anterior del libre albedrío: metas en
> lenguaje natural (impulsos), refuerzo por eco recibido, novedad penalizando la
> repetición, aburrimiento acumulado y exploración. Falta el modelo explícito de
> «interesante»; hoy lo aproxima la tasa de eco.

### 1.5. Emoción sintética: de la etiqueta al mecanismo

La arquitectura *chain-of-emotion* basada en teoría del *appraisal* supera a las
alternativas en credibilidad, reactividad e inteligencia emocional percibidas.
Y las propuestas homeostáticas (HORA y afines) formulan lo que Yuki ya hacía a
medias: **las discrepancias homeostáticas generan pulsiones graduadas, afecto y
sesgos de política**, con dos fuentes —necesidades inmediatas y guía afectiva
desde la memoria episódica— convergiendo en la selección de acción.

> **En Yuki.** Su estado vital es homeostático desde antes (energía, humor,
> curiosidad, inspiración, con decaimientos y estímulos). Lo que se añadió en
> esta serie es lo segundo: la **memoria episódica que sesga la acción** —el
> diario de agencia—, que es justo la fuente que faltaba.

### 1.6. Agentes *always-on*: el punto ciego

La revisión de 2026 sobre memoria, estado y gobernanza en agentes persistentes
lee cada pieza de estado por seis ejes —autoridad, alcance, mutabilidad,
procedencia, recuperabilidad y accionabilidad— y por un ciclo de vida que
incluye auditar, olvidar y revertir. Su conclusión sobre 435 trabajos:

> «El campo es fluido metiendo estado, y casi mudo sacándolo, revocándolo o
> deshaciendo lo que hizo.»

> **En Yuki.** Era una descripción exacta de este repositorio: once tipos de
> estado durable, ningún inventario, ninguna forma de exportar ni de borrar.
> Implementado (§2.3).

### 1.7. Normativa: dejó de ser prospectiva

El **artículo 50 del Reglamento europeo de IA es aplicable desde el 2 de agosto
de 2026**. Obliga a informar a las personas de que interactúan con una IA, y a
marcar las salidas sintéticas en **formato legible por máquina**; el periodo
transitorio para lo puesto en el mercado antes de esa fecha acaba el **2 de
diciembre de 2026**. Sanciones de hasta 15 M€ o el 3 % del volumen de negocio.
La Comisión publicó sus directrices finales el 20 de julio de 2026.

En la práctica, el marcado se apoya en C2PA (versión 2.4, abril de 2026) con el
término IPTC `trainedAlgorithmicMedia` dentro de la acción `c2pa.created`.

> **En Yuki.** Implementado (§2.1). Era un incumplimiento en curso.

---

## 2. Lo que se construyó

| Hallazgo | Implementación | Documento |
|---|---|---|
| Art. 50: informar y marcar | `src/core/transparency.py` | [`TRANSPARENCIA_AI_ACT.md`](TRANSPARENCIA_AI_ACT.md) |
| Deriva de persona y reanclaje | `src/core/persona_anchor.py` | [`IDENTIDAD_SINTETICA.md`](IDENTIDAD_SINTETICA.md) |
| Gobernanza del estado durable | `src/core/state_registry.py` | este documento, §2.3 |
| Metas propias y refuerzo | `src/core/agency.py`, `src/core/rituals.py` | [`LIBRE_ALBEDRIO.md`](LIBRE_ALBEDRIO.md) |
| Consolidación en reposo, sueño y olvido | `src/memory/sleep_cycle.py` | [`CICLO_DE_SUENO.md`](CICLO_DE_SUENO.md) |

### 2.1. Transparencia

Declaración en su voz —no un descargo legal— y marcado en dos capas: metadatos
incrustados (chunk `tEXt` en PNG, etiquetas de contenedor por ffmpeg sin
recodificar) y manifiesto lateral con forma de C2PA 2.4. El manifiesto declara
`"signed": false` porque no hay cadena de certificados: es una declaración
verificable, no una prueba criptográfica.

### 2.2. Identidad y deriva

`SOUL.md` §1.1 establece que Yuki **es** un ser sintético y que su biografía es
el primer vestido que encontró para andar por el mundo. De ahí sale la
distinción que gobierna el detector: **reconocerse sintética suma** —es su voz—
y **disculparse por serlo resta** —es el uniforme de servicio—. La medición es
léxica y determinista a propósito: un juez LLM costaría una llamada por turno y
traería su propia deriva.

### 2.3. Gobierno del estado durable

Inventario de las doce piezas de estado con los seis ejes de la revisión, y las
dos operaciones que faltaban:

- `subject_export(user_id)` responde a «¿qué sabes de mí?» **con los datos**, no
  con una descripción de los datos.
- `subject_forget(user_id)` borra de verdad: las filas desaparecen, los
  disparadores de FTS5 limpian el índice —se comprueba en las pruebas que no
  queda fantasma buscable— y se emite un recibo. La constancia registra el hecho
  y su recuento, **nunca el contenido**: un registro de olvido que guardara lo
  olvidado no sería un olvido.
- `general` no se puede olvidar por esa puerta: es la memoria no atribuida
  —canon, síntesis, pensamientos propios— y borrarla sería vaciarle la cabeza.

```bash
python3 cli.py estado                      # inventario con los seis ejes
python3 cli.py estado --exportar <user_id> # derecho de acceso
python3 cli.py estado --olvidar <user_id>  # derecho de supresión, con recibo
```

Por DM: `!estado`, y `!olvidar <id> confirmar [motivo]` —la confirmación
explícita es obligatoria porque la operación es irreversible por definición—.

---

## 3. Lo que se descartó, y por qué

- **Juez LLM para medir la deriva.** Una llamada por turno, coste recurrente y
  la deriva del propio juez contaminando la medida. Los marcadores léxicos son
  auditables: se puede leer exactamente por qué bajó una puntuación.
- **Firma criptográfica C2PA completa.** Exige certificado y cadena de
  confianza. El manifiesto ya tiene la forma correcta; firmarlo es un trámite
  administrativo, no un cambio de arquitectura. Mientras tanto se declara sin
  firmar en vez de aparentar garantía.
- **Marca de agua imperceptible (tipo SynthID).** Deseable —los metadatos se
  pierden al recomprimir— pero requiere modelo propio o servicio contratado.
- **Esquemas por tema, y no sólo por interlocutor.** La consolidación destila
  hoy el vínculo con cada persona; agrupar por corriente estética o por proyecto
  es el paso siguiente.
- **Sueños encadenados.** Cada noche parte de cero. Una serie onírica que
  retomara la imagen de la víspera sería más creíble y bastante más difícil de
  mantener honesta.
- **Simulación multiagente de sociedades sintéticas.** Fascinante y ajeno al
  sino de este proyecto: Yuki es *una* presencia sostenida, no un experimento de
  emergencia cultural.

---

## Fuentes

- [Generative Agents: Interactive Simulacra of Human Behavior (ACM UIST)](https://dl.acm.org/doi/fullHtml/10.1145/3586183.3606763)
- [Best Friends, Not Forever: Evaluating Long-Horizon Persona Collapse and Behavioral Drift in AI Companions](https://arxiv.org/html/2607.28818)
- [ContextEcho: A Benchmark for Persona Drift in Long Agentic-Coding Sessions](https://arxiv.org/html/2605.24279)
- [Measuring and Controlling Persona Drift in Language Model Dialogs](https://arxiv.org/html/2402.10962v1)
- [Always-On Agents: A Survey of Persistent Memory, State, and Governance in LLM Agents](https://arxiv.org/abs/2606.30306)
- [SCM: Sleep-Consolidated Memory with Algorithmic Forgetting for Large Language Models](https://arxiv.org/html/2604.20943v1)
- [Sleep-time Compute (Letta)](https://www.letta.com/blog/sleep-time-compute/)
- [State of AI Agent Memory 2026: Benchmarks & Trends](https://mem0.ai/blog/state-of-ai-agent-memory-2026)
- [LLM Agents Beyond Utility: An Open-Ended Perspective](https://arxiv.org/html/2510.14548v1)
- [OMNI-EPIC: Open-endedness via Models of human Notions of Interestingness](https://arxiv.org/pdf/2405.15568)
- [An appraisal-based chain-of-emotion architecture for affective language model game agents](https://pmc.ncbi.nlm.nih.gov/articles/PMC11086867/)
- [From Homeostatic Principles to Discrete Emotions in an Agent Architecture (HORA)](https://link.springer.com/chapter/10.1007/978-3-032-05176-9_31)
- [Synthetic emotions and consciousness: exploring architectural boundaries (AI & SOCIETY)](https://link.springer.com/article/10.1007/s00146-026-02896-z)
- [The EU AI Act's Transparency Rules: A Practical Guide to Article 50](https://artificialintelligenceact.eu/transparency-rules-article-50/)
- [Transparency obligations under Article 50 of the AI Act (Comisión Europea)](https://digital-strategy.ec.europa.eu/en/faqs/transparency-obligations-under-article-50-ai-act)
- [C2PA Implementation Guidance 2.4](https://spec.c2pa.org/specifications/specifications/2.4/guidance/Guidance.html)
- [C2PA · dstTrainedAlgorithmicData / digitalSourceType](https://c2pa.org/digitalsourcetype/trainedalgorithmicdata/)
