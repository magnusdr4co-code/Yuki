"""
Lo común a los criterios de las artes: decidir, y decir de dónde salió cada cosa.

Los prompts de generación eran constantes escritas a mano. La música llevaba 72
BPM con cualquier letra delante; la portada, «agua, hierro e invierno» con
cualquier obra; el vídeo, cuatro planos del muelle; la voz, «calidez contenida»
con cualquier texto. El encargo no podía cambiar nada, y eso no se notaba porque
el resultado siempre salía bien *de alguna manera*.

Cada arte mide cosas distintas —sílabas por verso, elementos por encuadre,
secciones por minuto— así que aquí no hay una medida común. Lo que sí es común
son dos reglas, y por eso viven juntas:

**Manda la fuente.** Si la letra, el concepto o el texto traen sus propias
marcas, se respetan. Son decisiones de quien los escribió.

**Lo deducido se declara deducido.** Cada campo lleva su origen, y el resumen
distingue lo que eligió Yuki de lo que dedujo el criterio. Sin eso, un criterio
es indistinguible de una constante con mejor prensa.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

# Cómo se nombra cada procedencia al resumir. `fuente` es lo que ya venía
# escrito; `criterio`, lo que este código dedujo al medir; `argumento`, lo que
# alguien impuso a mano por la línea de comandos.
ETIQUETAS_DE_ORIGEN = {
    "fuente": "de la fuente",
    "letra": "de la letra",
    "concepto": "del concepto",
    "texto": "del texto",
    "obra": "de la obra",
    "criterio": "por criterio",
    "argumento": "impuesto a mano",
    "estacion": "de la estación",
}


@dataclass
class Criterio:
    """Una decisión artística tomada antes de gastar, con su porqué."""

    titulo: str
    origen: Dict[str, str] = field(default_factory=dict)
    observaciones: List[str] = field(default_factory=list)

    def de(self, campo: str) -> str:
        """Cómo se nombra el origen de un campo. Sin origen declarado, criterio."""
        return ETIQUETAS_DE_ORIGEN.get(self.origen.get(campo, "criterio"), "por criterio")

    def render(self, encabezado: str, filas: Sequence[Tuple[str, str]]) -> str:
        """
        El resumen que se dice **antes** de llamar al proveedor.

        Las observaciones van al final y sin adornar: son avisos sobre lo que va
        a salir mal, y enterrarlos entre las decisiones es como no darlos.
        """
        lineas = [f"{encabezado} para «{self.titulo}»:"]
        lineas += [f"- {texto}" for _, texto in filas if texto]
        lineas += [f"- {nota}" for nota in self.observaciones]
        return "\n".join(lineas)
