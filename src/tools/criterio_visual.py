"""
Lo que decide Yuki antes de encargar una imagen.

`create_single_cover` construía el prompt con una cola fija —«Traditional
shamisen meets modern industrial minimalism»—, relación de aspecto **1:1**
siempre y una iluminación que venía por argumento con `komorebi` por defecto. En
el encargo por DM era peor: el concepto visual estaba escrito a mano en el
adaptador («agua, hierro e invierno; escarcha sobre acero oxidado») con
`lighting="urushi"` clavado, así que la portada de cualquier obra era la portada
de *Herrumbre y Escarcha*.

Es el mismo defecto que tenía la música, y se arregla igual: leer lo que hay
—título, concepto, la obra de la que sale— y decidir, diciendo de dónde salió
cada decisión.

Lo que aquí se mide es **la carga del encuadre**. Un concepto que enumera nueve
elementos no produce una imagen rica: produce una imagen llena, donde el punto
focal se pierde y la paleta minimalista deja de sostenerse. Eso es comprobable
contando, y se avisa antes de gastar.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .criterio_base import Criterio

# Encuadres que el proveedor admite, con lo que cada uno sirve.
ENCUADRES = {
    "1:1": ("portada", "caratula", "single", "sencillo", "cover", "avatar"),
    "4:5": ("cartel", "poster", "feed", "publicacion", "retrato"),
    "16:9": ("escena", "paisaje", "plano", "fondo", "panoramica", "cabecera"),
    "9:16": ("story", "historia", "vertical", "reel", "movil"),
}
ENCUADRE_POR_DEFECTO = "1:1"

# Luces del canon. No son filtros: cada una implica una hora y un material.
LUCES = {
    "industrial_rain": ("lluvia", "neon", "asfalto", "noche", "puerto", "muelle",
                        "metal", "acero", "herrumbre", "oxido", "niebla", "invierno"),
    "urushi": ("urushi", "laca", "oro", "pan de oro", "interior", "te", "vela",
               "seda", "penumbra", "salon", "tinta"),
    "komorebi": ("bosque", "bambu", "sol", "manana", "hoja", "jardin", "verde",
                 "primavera", "agua clara", "luz filtrada"),
}
LUZ_POR_DEFECTO = "komorebi"

# Elementos por encuadre a partir de los cuales la imagen se llena. No es una
# cifra sagrada: es dónde empieza a competir el punto focal en una paleta que
# vive del vacío.
ELEMENTOS_QUE_SATURAN = 6


def _sin_tildes(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in descompuesto if not unicodedata.combining(c)).casefold()


def elementos(concepto: str) -> List[str]:
    """
    Los elementos que el concepto enumera.

    Parte por comas, puntos y conjunciones, que es como se enumera al describir
    una imagen. Es una aproximación —no analiza sintaxis— y sirve para lo que se
    usa: notar cuándo la lista ha crecido tanto que no cabe en un encuadre.
    """
    trozos = re.split(r"[,;.]| y | e | con | sobre ", concepto or "")
    return [t.strip() for t in trozos if len(t.strip()) > 2]


@dataclass
class PlanVisual(Criterio):
    """Qué imagen se va a pedir, y por qué ésa."""

    concepto: str = ""
    encuadre: str = ENCUADRE_POR_DEFECTO
    luz: str = LUZ_POR_DEFECTO
    kigo: str = ""

    def resumen(self) -> str:
        return self.render("🎨 Criterio visual", [
            ("encuadre", f"Encuadre {self.encuadre} ({self.de('encuadre')})."),
            ("luz", f"Luz {self.luz} ({self.de('luz')})."),
            ("kigo", f"Motivo de estación: {self.kigo} ({self.de('kigo')})." if self.kigo else ""),
            ("concepto", f"Concepto: {self.concepto} ({self.de('concepto')})."),
        ])

    def prompt(self) -> str:
        """
        El encargo visual.

        El aire va **declarado**, no supuesto: la paleta vive del vacío y un
        proveedor que llene el encuadre por defecto se lleva por delante lo que
        distingue a esta obra de un montaje de existencias.
        """
        partes = [
            f"{self.titulo}. Concept: {self.concepto}.",
            f"Lighting: {self.luz.replace('_', ' ')}.",
            "Japanese neo-traditional composition: one clear focal point, generous negative "
            "space (ma), restrained palette, physical texture over gloss.",
            "No text, no watermark, no logo.",
        ]
        if self.kigo:
            partes.insert(1, f"Seasonal motif: {self.kigo}.")
        return " ".join(partes)


def _encuadre(texto: str) -> Tuple[str, str]:
    plano = _sin_tildes(texto)
    for relacion, palabras in ENCUADRES.items():
        if any(palabra in plano for palabra in palabras):
            return relacion, "concepto"
    return ENCUADRE_POR_DEFECTO, "criterio"


def _luz(texto: str) -> Tuple[str, str]:
    """
    La luz con más presencia en el texto, no la primera que aparezca.

    Con «lluvia sobre laca de oro» ganan las dos a una palabra; decidir por
    orden de diccionario sería decidir por azar del alfabeto.
    """
    plano = _sin_tildes(texto)
    conteos = {luz: sum(1 for palabra in palabras if palabra in plano)
               for luz, palabras in LUCES.items()}
    mejor = max(conteos, key=lambda luz: conteos[luz])
    if conteos[mejor] == 0:
        return LUZ_POR_DEFECTO, "criterio"
    return mejor, "concepto"


def leer_criterio_visual(concepto: str, titulo: str = "",
                         kigo: Optional[str] = None) -> PlanVisual:
    """
    Decide el encuadre, la luz y el aire de una imagen a partir de su concepto.

    Un concepto vacío no es un error: es una imagen que deja las decisiones a
    quien compone, y entonces todo sale declarado como criterio.
    """
    origen: Dict[str, str] = {}
    observaciones: List[str] = []

    encuadre, origen["encuadre"] = _encuadre(f"{titulo} {concepto}")
    luz, origen["luz"] = _luz(concepto)
    origen["concepto"] = "concepto" if (concepto or "").strip() else "criterio"
    if kigo:
        origen["kigo"] = "estacion"

    piezas = elementos(concepto)
    if len(piezas) > ELEMENTOS_QUE_SATURAN:
        observaciones.append(
            f"⚠️ El concepto enumera {len(piezas)} elementos: en un encuadre {encuadre} "
            "compiten y el punto focal se pierde. Una imagen llena no es una imagen rica; "
            "para que respire, quitar los que no sostengan la escena.")
    elif piezas:
        observaciones.append(
            f"{len(piezas)} elemento(s) en el encuadre: cabe con aire alrededor.")

    if not (concepto or "").strip():
        observaciones.append(
            "Sin concepto escrito: compongo con la paleta del canon y lo digo, "
            "en vez de inventar una intención que nadie dio.")

    return PlanVisual(
        titulo=titulo or "Imagen sin título", origen=origen, observaciones=observaciones,
        concepto=(concepto or "").strip() or "agua, metal y luz contenida",
        encuadre=encuadre, luz=luz, kigo=kigo or "",
    )
