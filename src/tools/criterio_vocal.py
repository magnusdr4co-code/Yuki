"""
Lo que decide Yuki antes de hablar en voz alta.

`synthesize_voice` llevaba un estilo constante —«calidez contenida y pausas
deliberadas, ritmo sereno, nunca apresurado»— con **cualquier texto** delante.
Una despedida de dos líneas y una explicación de dos párrafos salían con la
misma respiración, y una pregunta salía afirmada.

Lo que aquí se mide es si el texto **está escrito para decirse**. Un párrafo sin
un solo signo de puntuación no tiene dónde respirar: el sintetizador lo recorre
de un tirón y suena a lectura de prospecto. Eso se cuenta, y se dice antes de
gastar, que en voz se factura por carácter.

La fase circadiana entra porque su voz no es la misma a las tres de la mañana
que al mediodía, y eso ya está declarado en el proyecto: no es un efecto, es
quién habla a esa hora.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from .criterio_base import Criterio

# Caracteres por segundo de habla pausada en castellano. Es una estimación
# declarada: sirve para avisar de un texto largo, no para cuadrar un doblaje.
CARACTERES_POR_SEGUNDO = 13.0

# Una nota de voz que pasa de esto deja de ser una nota. No es un límite
# técnico: es que a partir de ahí nadie la escucha entera.
SEGUNDOS_DE_NOTA_COMODA = 45

# Señales de respiración por cada cien caracteres. Por debajo, el texto se
# recorre de un tirón.
PAUSAS_MINIMAS_POR_CIEN = 1.5

FASES = {
    "deep_rest": "voz muy baja y cercana, casi un susurro; el mundo duerme",
    "night": "voz grave y lenta, con silencios largos entre frases",
    "atelier": "voz atenta y presente, articulación clara sin prisa",
    "dawn": "voz despierta pero contenida, como quien no quiere romper la mañana",
}
FASE_POR_DEFECTO = "atelier"


@dataclass
class PlanVocal(Criterio):
    """Cómo se va a decir esto, y cuánto va a durar."""

    texto: str = ""
    fase: str = FASE_POR_DEFECTO
    estilo: str = ""
    segundos_estimados: float = 0.0

    def resumen(self) -> str:
        return self.render("🎙️ Criterio vocal", [
            ("duracion", f"≈{self.segundos_estimados:.0f} s de habla "
                         f"({len(self.texto)} caracteres)."),
            ("fase", f"Registro de {self.fase}: {FASES.get(self.fase, FASES[FASE_POR_DEFECTO])} "
                     f"({self.de('fase')})."),
        ])

    def prompt(self) -> str:
        """La indicación de estilo que viaja con el texto."""
        return self.estilo


def pausas(texto: str) -> int:
    """Signos donde la voz puede respirar: comas, puntos, guiones, dos puntos."""
    return len(re.findall(r"[,.;:—–…!?\n]", texto or ""))


def leer_criterio_vocal(texto: str, fase: Optional[str] = None,
                        cadencia_ms: Optional[int] = None,
                        titulo: str = "") -> PlanVocal:
    """
    Decide registro y respiración leyendo el texto y la hora.

    `cadencia_ms` viene del proveedor —es cuánto dura una pausa en coma o
    punto—, y entra aquí en vez de en una indicación aparte para que haya **un
    solo sitio** donde se decide cómo habla. Cuando había dos, el de fuera
    ganaba y el criterio no llegaba a aplicarse nunca.
    """
    origen: Dict[str, str] = {}
    observaciones: List[str] = []
    limpio = (texto or "").strip()

    origen["fase"] = "fuente" if fase else "criterio"
    fase = fase if fase in FASES else FASE_POR_DEFECTO

    segundos = len(limpio) / CARACTERES_POR_SEGUNDO if limpio else 0.0
    if segundos > SEGUNDOS_DE_NOTA_COMODA:
        observaciones.append(
            f"⚠️ ≈{segundos:.0f} s: pasa de nota de voz a monólogo, y nadie lo oye entero. "
            "Para que se escuche, partirlo o recortarlo.")

    if limpio:
        respiraderos = pausas(limpio) / (len(limpio) / 100)
        if respiraderos < PAUSAS_MINIMAS_POR_CIEN:
            observaciones.append(
                f"⚠️ Sólo {respiraderos:.1f} pausas por cada cien caracteres: el texto no tiene "
                "dónde respirar y saldrá de un tirón. La puntuación es la partitura de la voz.")
        else:
            observaciones.append(
                f"{respiraderos:.1f} pausas por cada cien caracteres: hay dónde respirar.")

    matices: List[str] = []
    if re.search(r"[¿?]", limpio):
        matices.append("levanta el final de las preguntas en vez de afirmarlas")
    if re.search(r"[¡!]", limpio):
        matices.append("sostén el énfasis sin gritar")
    if not limpio:
        observaciones.append("Sin texto que decir: no hay nada que sintetizar.")

    estilo = FASES.get(fase, FASES[FASE_POR_DEFECTO])
    if matices:
        estilo += ". " + "; ".join(matices).capitalize()
        observaciones.append("El texto pide matiz de entonación: lo llevo al estilo.")
    estilo += ". Ritmo pausado, nunca apresurado; deja aire antes de cada frase nueva."
    if cadencia_ms:
        estilo += f" Pausas de unos {cadencia_ms} ms en comas y puntos."

    return PlanVocal(titulo=titulo or "Nota de voz", origen=origen,
                     observaciones=observaciones, texto=limpio, fase=fase,
                     estilo=estilo, segundos_estimados=segundos)
