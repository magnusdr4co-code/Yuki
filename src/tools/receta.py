"""
La receta de una obra generada: con qué se hizo, para poder rehacerla.

`docs/VIRTUALIZACION_Y_MEJORAS.md` (M4) dejaba pendiente «archivar el prompt y
los parámetros de cada pista para poder rehacerla igual». Hasta ahora lo único
que sobrevivía a la generación era el manifiesto del Artículo 50, y ése no es
una receta: guarda el modelo y el prompt **recortado a 500 caracteres** dentro
de un campo llamado `abstract`, porque su trabajo es declarar el origen, no
reproducir la obra. Con un prompt de canción de doce mil caracteres, eso es
perder la letra entera.

Aquí se escribe un `<fichero>.receta.json` al lado del medio, con el prompt
íntegro y los parámetros que de verdad cambian el resultado —motor, duración,
bpm, escala, relación de aspecto, imagen de partida—. Dos usos concretos:
rehacer una pista que salió bien, y saber en qué se diferencia de la que salió
mal, que era la pregunta que nadie podía contestar cuando el Productor decía
«me has devuelto exactamente lo mismo».

No es estado durable de la instancia: vive junto a la obra, en `output/`, y se
va con ella. Por eso no entra en `state_registry` ni en la copia —lo que hay que
respaldar es la Biblioteca, y la receta viaja dentro—.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("Yuki.Receta")

SUFIJO = ".receta.json"


def ruta_de(path: str) -> Path:
    return Path(f"{path}{SUFIJO}")


def escribir(path: Optional[str], *, motor: str = "", prompt: str = "",
             **parametros: Any) -> Optional[str]:
    """
    Escribe la receta junto al fichero. Nunca impide entregar la obra.

    Un fallo aquí no puede hacer desaparecer una pista que ya existe y está
    pagada: se registra y se sigue. Devuelve la ruta escrita, o `None`.
    """
    if not path or not Path(path).is_file():
        return None
    receta = {
        "obra": Path(path).name,
        "motor": motor,
        "prompt": prompt or "",
        "parametros": {clave: valor for clave, valor in parametros.items() if valor is not None},
        "generada_en": time.time(),
        "nota": ("Parámetros con los que se generó esta obra, para poder rehacerla. "
                 "No es una declaración de origen: ésa va en el manifiesto `.c2pa.json`."),
    }
    destino = ruta_de(path)
    try:
        destino.write_text(json.dumps(receta, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning("No pude escribir la receta de %s: %s", path, type(exc).__name__)
        return None
    return str(destino)


def leer(path: str) -> Dict[str, Any]:
    """La receta de una obra, o un diccionario vacío si no la tiene."""
    destino = ruta_de(path)
    if not destino.is_file():
        return {}
    try:
        datos = json.loads(destino.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("Receta ilegible en %s: %s", destino, type(exc).__name__)
        return {}
    return datos if isinstance(datos, dict) else {}


def diferencias(una: Dict[str, Any], otra: Dict[str, Any]) -> Dict[str, Any]:
    """
    En qué se diferencian dos recetas. Vacío si se generaron igual.

    Es la pregunta que nadie podía contestar cuando el Productor decía «me has
    devuelto exactamente lo mismo»: si las recetas coinciden, no es terquedad
    del modelo, es que se pidió lo mismo.
    """
    cambios: Dict[str, Any] = {}
    for campo in ("motor", "prompt"):
        if una.get(campo) != otra.get(campo):
            cambios[campo] = (una.get(campo), otra.get(campo))
    parametros_una = una.get("parametros") or {}
    parametros_otra = otra.get("parametros") or {}
    for clave in sorted(set(parametros_una) | set(parametros_otra)):
        if parametros_una.get(clave) != parametros_otra.get(clave):
            cambios[clave] = (parametros_una.get(clave), parametros_otra.get(clave))
    return cambios
