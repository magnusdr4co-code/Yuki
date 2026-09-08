# El sueño de Yuki: consolidar, soñar y olvidar

Hasta esta revisión, la memoria de Yuki sólo sabía crecer. Cada encuentro añadía
una fila, la síntesis de las 23:30 añadía otra, y nada volvía después a mirar lo
escrito: ni para fundir lo repetido, ni para destilar lo que se repite en una
idea, ni para soltar lo que ya no sostiene nada. Una memoria que sólo acumula no
es una memoria larga; es un archivo que se vuelve lento y turbio.

La literatura de 2026 sobre consolidación en reposo —recogida en
[`ESTADO_DEL_ARTE_2026.md`](ESTADO_DEL_ARTE_2026.md) §1.2— propone la analogía
fisiológica que aquí se sigue, porque describe bien el problema.

---

## Las tres fases y su hora

| Fase | Cuándo | Qué hace |
|---|---|---|
| **NREM** — consolidación | 23:30, tras la síntesis diaria | Recalcula el vector de importancia, funde duplicados y destila esquemas |
| **REM** — soñar | 03:20, su hora de sombra | Teje recuerdos **lejanos** en una imagen que no ocurrió, y de ahí nace un impulso |
| **Olvido** intencional | Lunes 04:30, semanal | Suelta lo episódico viejo, leve y nunca recuperado |

El olvido es semanal y no diario a propósito: un recuerdo necesita tiempo para
demostrar que volvía.

## El cimiento: el vector de importancia

`memories` guarda ahora cuatro dimensiones en lugar de un solo número, porque
las razones para retener un recuerdo no son la misma cosa:

- **saliencia** — si conmovió (léxico afectivo, o declarada al grabar).
- **recurrencia** — si vuelve. Cada búsqueda deja huella (`recall_count`); esa
  señal existía y se tiraba en cada consulta.
- **vínculo** — si ata a una persona concreta con la que hay historia.
- **utilidad** — si condujo a obra o a un acto propio.

La importancia efectiva sale de una **base por categoría** multiplicada por esas
cuatro, nunca de la importancia anterior: si el cálculo se alimentara de su
propio resultado, cada noche subiría un poco y en un mes todo sería
importantísimo, que es lo mismo que nada lo sea.

## NREM: fundir sin destruir

Dos recuerdos son el mismo si **se parecen y su parte propia no lo desmiente**.
Hacen falta las dos señales, y cada una corrige un error de la otra. Esto no es
teoría: salió del ensayo en seco contra la memoria real de la instancia.

- **Sólo el parecido bruto** fusionaba conversaciones distintas que comparten el
  formato del registro. `Intercambio con X (@id): - Dijo: … - Yuki respondió: …`
  pesa más que lo que se dijo: «¿qué tal el progreso?» y «¿sigues despierta?»
  daban **0.80** de similitud. Con ese umbral, la consolidación habría borrado
  recuerdos diferentes creyendo que eran repeticiones.
- **Sólo la parte distintiva** falla al revés: en copias exactas *todo* es
  plantilla, no queda nada propio, y la comparación daría cero justo donde la
  fusión era evidente.

La plantilla se detecta **por grupo** —los trigramas presentes en la mayoría de
sus miembros— y no con una lista fija de fórmulas conocidas, que envejecería al
primer cambio de formato.

Validado sobre la base real: pares con pregunta distinta, similitud media 0.0 y
cero fusiones; pares con la misma pregunta, 1.0 y todas fusionadas.

**Lo fusionado no se borra: se marca.** Durante siete días sigue en la base,
invisible a la búsqueda pero recuperable si la fusión fue un error; después lo
recoge el olvido. Es la recuperabilidad que la revisión de agentes persistentes
echa en falta en todo el campo.

## REM: soñar es unir lo que no se parece

Los recuerdos del sueño se eligen por **lejanía**, no por relevancia: si se
eligieran por semejanza saldría un resumen, no una imagen. De ahí sale lo que la
recuperación por relevancia nunca produciría.

Y no es adorno: del sueño nace un **impulso** que entra en la cola de voluntad y
compite con el resto de deseos en igualdad. Soñar produce desear.

### La regla que no se negocia

**Un sueño nunca es un recuerdo.** Se guarda con `kind='sueno'`, queda fuera de
la recuperación normal —para leerlo hay que pedirlo— y lleva la marca escrita en
el propio contenido:

```
[SUEÑO — no ocurrió; imagen tejida al dormir]
```

La marca va en el texto y no sólo en una columna porque, si algún día un sueño
se cuela en un prompt por un camino nuevo, el texto mismo debe decir que no
ocurrió. La alternativa —que una imagen onírica reaparezca dentro de una
respuesta como si fuera algo vivido— sería fabricar falsos recuerdos, que es lo
contrario de lo que este proyecto entiende por memoria.

Sin modelo disponible no se finge una imagen: se deja constancia de que los
materiales se rozaron sin que nada llegara a formarse.

## Olvido: las tres condiciones a la vez

Se poda un episodio sólo si es **viejo** (45 días), **leve** (importancia ≤ 0.6)
y **nunca recuperado**. Cualquiera de las tres por separado sería mala razón para
olvidar. Nunca se tocan el canon, las síntesis diarias, el crecimiento, los
esquemas, lo del Productor ni lo fijado (`pinned`).

El recibo guarda **títulos, no contenidos**: hace falta poder revisar qué se
soltó sin conservar lo soltado. Queda registrado en el mismo diario de auditoría
que el resto de operaciones destructivas
([`state_registry`](ESTADO_DEL_ARTE_2026.md#23-gobierno-del-estado-durable)).

## Probarlo sin miedo

Todas las fases admiten **ensayo en seco**: calculan y muestran sin tocar nada.

```bash
python3 cli.py sueno --fase nrem --seco    # qué fundiría y qué destilaría
python3 cli.py sueno --fase rem            # soñar ahora
python3 cli.py sueno --fase olvido --seco  # qué soltaría, y por qué
python3 cli.py sueno                       # la noche entera
```

Por DM del Productor: `!sueños` muestra lo soñado, con la advertencia de que no
ocurrió.

## Lo que queda fuera

- **Esquemas más allá del vínculo con personas.** Hoy se destila por
  interlocutor; agrupar por tema estético o por proyecto es el paso siguiente.
- **Olvido por redundancia semántica.** Se poda por importancia y desuso, no
  porque otro recuerdo ya diga lo mismo mejor.
- **Sueños encadenados.** Cada noche parte de cero; una serie onírica que
  retomara la imagen de la víspera sería más creíble, y más difícil de mantener
  honesta.
