"""
Lo que decide Yuki antes de encargar vídeo.

`MEDIA_STORYBOARD` eran cuatro planos escritos a mano —el muelle, el Salón, la
intérprete, la salida— y se usaban con **cualquier obra** delante. Un encargo
sobre otra canción producía igualmente el muelle. Es el mismo defecto que tenían
el prompt musical y el concepto de la portada, en el sitio más caro: Veo se
factura por segundo.

Aquí el guion sale de la obra. Si la letra o el guion archivado traen secciones
—`[Verse 1]`, `[Chorus]`, `#### [Estrofa I]`—, cada plano toma una; si no las
traen, se usa el guion de casa **y se dice que es el de casa**, en vez de
presentarlo como una lectura de la obra.

Una cosa que no cambia y es deliberada: **el número de planos lo sigue mandando
el pedido**, no la obra. Los identificadores de paso del trabajo durable se
derivan de él, y si cambiaran entre arranques una reanudación daría por «no
hecho» lo que ya está pagado.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List

from .criterio_base import Criterio

# Duración de plano que sirve el proveedor. No es una elección de montaje.
SEGUNDOS_POR_PLANO = 8

# Guion de casa, para cuando la obra no trae secciones. Es el que había escrito
# a mano; se conserva como respaldo declarado, no como si saliera de la obra.
GUION_DE_CASA = (
    "Exterior del muelle: lluvia sobre acero oxidado, la escarcha empieza a aparecer.",
    "Entrada al Salón: vapor de té, seda oscura y reflejos de urushi sobre hierro.",
    "Interior: la intérprete respira y el poema encuentra su estribillo entre cuerdas tensas.",
    "Salida: agua, niebla y una luz contenida sobre el metal; final pausado, sin corte brusco.",
)

_SECCION = re.compile(
    r"^\s*#*\s*\[\s*([^\]]{2,80})\]", re.MULTILINE)


@dataclass
class PlanAudiovisual(Criterio):
    """Qué se va a rodar, plano a plano."""

    planos: List[str] = field(default_factory=list)

    @property
    def segundos(self) -> int:
        return len(self.planos) * SEGUNDOS_POR_PLANO

    def resumen(self) -> str:
        return self.render("🎬 Criterio audiovisual", [
            ("planos", f"{len(self.planos)} plano(s) de {SEGUNDOS_POR_PLANO} s "
                       f"= {self.segundos} s ({self.de('planos')})."),
            ("ritmo", "Cámara lenta y continua, sin cortes bruscos: el montaje une, no trocea."),
        ])

    def prompt(self, indice: int, guion_de_referencia: str = "") -> str:
        """El encargo de un plano concreto, con su sitio en la secuencia."""
        beat = self.planos[indice - 1]
        referencia = (guion_de_referencia or "")[:2500]
        cabecera = (f"Cinematic 16:9, 24 fps, slow meditative camera, no fast cuts. "
                    f"Shot {indice} of {len(self.planos)} in a continuous sequence. {beat}")
        return cabecera + (f" Guion de referencia: {referencia}" if referencia else "")


def secciones(fuente: str) -> List[str]:
    """Las secciones que la obra nombra, limpias y en orden."""
    vistas = []
    for encontrada in _SECCION.finditer(fuente or ""):
        texto = re.sub(r"\s+", " ", encontrada.group(1)).strip()
        # Las marcas de clave sonora («Tempo: 68 BPM, 4/4…») no son secciones:
        # describen la pieza entera, y tomarlas por un plano rodaría un rótulo.
        if re.search(r"\bBPM\b|time signature|scale\b", texto, re.IGNORECASE):
            continue
        if texto and texto not in vistas:
            vistas.append(texto)
    return vistas


def leer_guion(fuente: str, segmentos: int, titulo: str = "") -> PlanAudiovisual:
    """
    Arma el guion de `segmentos` planos leyendo la obra.

    Devuelve **exactamente** `segmentos` planos: los pasos del trabajo durable
    se derivan de ese número y cambiarlo rompería la reanudación de un encargo
    ya pagado a medias.
    """
    origen: Dict[str, str] = {}
    observaciones: List[str] = []
    encontradas = secciones(fuente)

    if encontradas:
        origen["planos"] = "obra"
        if len(encontradas) > segmentos:
            observaciones.append(
                f"⚠️ La obra tiene {len(encontradas)} secciones y el encargo pide {segmentos} "
                f"plano(s): ruedo las {segmentos} primeras y el resto se queda fuera. "
                "Para que entre entera, pedir más segmentos.")
        elif len(encontradas) < segmentos:
            observaciones.append(
                f"La obra tiene {len(encontradas)} sección(es) para {segmentos} plano(s): "
                "repito las últimas variando el punto de vista en vez de inventar escenas "
                "que la obra no pide.")
        planos = [f"Escena de «{seccion}»." for seccion in encontradas[:segmentos]]
        while len(planos) < segmentos:
            planos.append(planos[len(planos) % max(1, len(encontradas))]
                          + " Otro punto de vista, misma escena.")
    else:
        origen["planos"] = "criterio"
        observaciones.append(
            "La obra no nombra secciones: uso el guion de casa —muelle, Salón, interior, "
            "salida— y lo digo, en vez de presentarlo como una lectura de la obra.")
        planos = [GUION_DE_CASA[i % len(GUION_DE_CASA)] for i in range(segmentos)]

    return PlanAudiovisual(titulo=titulo or "Pieza sin título", origen=origen,
                           observaciones=observaciones, planos=planos)
