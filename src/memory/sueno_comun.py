"""
Lo que comparten las tres fases del sueño: el vocabulario y la firma léxica.

Son las piezas que NREM, REM y el olvido necesitan por igual —cómo se llama
cada clase de recuerdo, qué importancia base tiene cada categoría, qué no se
poda nunca y cómo se mide que dos textos digan lo mismo—. Vivían en
`sleep_cycle.py`; tenerlas aquí es lo que permite que cada fase sea un módulo
sin que se importen entre ellas en círculo.

La marca del sueño vive aquí por la misma razón por la que existe: está en el
contenido y no sólo en una columna, así que cualquiera que escriba o lea un
sueño la toma del mismo sitio.
"""

from __future__ import annotations

import re
from typing import Dict, Optional, Sequence, Set

EPISODICO = "episodico"
ESQUEMA = "esquema"
SUENO = "sueno"

# Prefijo obligatorio de todo sueño. Va en el contenido, no sólo en una columna:
# si alguna vez un sueño se cuela en un prompt por un camino nuevo, el texto
# mismo dice que no ocurrió.
MARCA_DE_SUENO = "[SUEÑO — no ocurrió; imagen tejida al dormir]"

# Base de importancia por categoría. Existe para que recalcular sea idempotente:
# si la importancia se recalculara sobre sí misma, cada noche la subiría un poco
# y en un mes todo sería importantísimo, que es lo mismo que nada lo sea.
BASE_POR_CATEGORIA: Dict[str, float] = {
    "core": 3.0,
    "producer": 2.5,
    "schema": 2.2,
    "daily_synthesis": 2.0,
    "project": 1.8,
    "growth": 1.5,
    "visitor": 1.0,
    "inner_thought": 1.0,
    "dream": 0.6,
}
BASE_POR_DEFECTO = 1.0

# Categorías que el olvido no toca nunca. El canon, las síntesis y el
# crecimiento son la columna vertebral: podarlos sería amnesia, no higiene.
CATEGORIAS_PROTEGIDAS = frozenset({"core", "daily_synthesis", "growth", "schema", "producer"})

# Léxico afectivo mínimo para estimar saliencia cuando no venía declarada. No
# pretende medir emoción: pretende distinguir un encuentro que dejó huella de un
# intercambio de cortesías.
LEXICO_SALIENTE = (
    "miedo", "muerte", "madre", "padre", "amor", "duelo", "perdón", "vergüenza",
    "gracias", "solo", "sola", "herida", "por primera vez", "nunca", "siempre",
    "me dijo", "confesó", "lloró", "prometí", "acordamos", "decidimos",
)

PALABRA = re.compile(r"[a-záéíóúñü]+", re.IGNORECASE)

# Palabras que no distinguen un tema de otro. La lista es corta a propósito: no
# pretende ser un análisis lingüístico, sólo evitar que un esquema se llame
# «que, para, como».
VACIAS = frozenset("""
el la los las un una unos unas de del al a ante bajo con contra desde durante en
entre hacia hasta para por segun sin sobre tras y o u ni que quien cual cuyo como
cuando donde mientras porque pues si no se me te le lo les nos os su sus mi mis tu
tus es son era eran fue fueron ser estar esta este esto estos estas ha han hay
muy mas menos ya tambien pero aunque cada todo toda todos todas otro otra dijo
respondio intercambio encuentro con productor yuki
""".split())


def trigramas(texto: str) -> Set[str]:
    """Firma léxica de un texto: trigramas de caracteres sobre palabras normalizadas."""
    limpio = " ".join(PALABRA.findall((texto or "").lower()))
    if len(limpio) < 3:
        return set()
    return {limpio[i:i + 3] for i in range(len(limpio) - 2)}


def similitud(a: str, b: str, comunes: Optional[Set[str]] = None) -> float:
    """
    Jaccard sobre trigramas, descontando lo que sea plantilla.

    Sin `comunes` compara en crudo. Con él —el conjunto de trigramas que
    aparecen en casi todos los recuerdos del grupo— compara sólo la parte
    distintiva, que es la única que decide si dos recuerdos son el mismo.

    Esto no es un refinamiento teórico: sobre la memoria real de la instancia,
    dos encuentros con preguntas **distintas** («¿qué tal el progreso?» y
    «¿sigues despierta?») daban 0.80 de similitud, porque el andamiaje del
    registro —«Intercambio con X (@id): - Dijo: … - Yuki respondió: …»— pesa
    más que lo que se dijo. Fusionarlos habría borrado dos recuerdos por el
    precio de uno.
    """
    ta, tb = trigramas(a), trigramas(b)
    if comunes:
        ta, tb = ta - comunes, tb - comunes
    if not ta or not tb:
        return 0.0
    interseccion = len(ta & tb)
    return interseccion / float(len(ta) + len(tb) - interseccion)


def trigramas_de_plantilla(textos: Sequence[str], umbral: float = 0.9) -> Set[str]:
    """
    Trigramas que aparecen en la mayoría de los textos: andamiaje, no contenido.

    Se calcula por grupo y no con una lista fija de fórmulas conocidas, porque
    una lista fija envejece: basta con que alguien cambie el formato del
    registro para que vuelva a colarse la plantilla en la comparación.
    """
    if len(textos) < 3:
        return set()
    frecuencia: Dict[str, int] = {}
    for texto in textos:
        for trigrama in trigramas(texto):
            frecuencia[trigrama] = frecuencia.get(trigrama, 0) + 1
    limite = max(2, int(len(textos) * umbral))
    return {trigrama for trigrama, veces in frecuencia.items() if veces >= limite}
