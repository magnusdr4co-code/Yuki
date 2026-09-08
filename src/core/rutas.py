"""
Dónde vive cada cosa. Un solo sitio que lo decida.

Las dos variables que reubican el estado de Yuki —`DATABASE_PATH` para la
memoria y `YUKI_OUTPUT_DIR` para lo que crea— estaban resueltas a mano en once
módulos, y no todos igual. El resultado fueron dos fallos de la misma familia,
ninguno de los cuales daba error:

  · El agente leía la ruta de la memoria de `config.yaml` ignorando
    `DATABASE_PATH`, mientras la copia de seguridad, la sonda de signos vitales
    y la comprobación de humo sí lo respetaban. Una instancia con esa variable
    puesta escribía en un sitio y respaldaba y vigilaba otro: una copia
    impecable de una base que nadie usa.

  · `nous_portal` respetaba `YUKI_OUTPUT_DIR`; `vertex_media`, `media_creator`,
    `midi_generator`, `music_fallback` y `creation_library` escribían en
    `output/…` fijo. Y la auditoría del Artículo 50 mira la ruta de la variable.
    Es decir: material sintético sin marcar que el auditor **no puede ver**.
    Eso ya no es ruido en las pruebas, es un agujero de cumplimiento.

La regla, una y la misma en todas partes: **la variable de entorno manda sobre
la configuración, y la configuración sobre el valor por defecto**. Y se resuelve
al llamar, nunca en el valor por defecto de un argumento: eso lo congelaría en
el momento de importar el módulo, que es antes de que nadie haya podido
reubicar nada.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

SALIDA_POR_DEFECTO = "output"
BASE_POR_DEFECTO = "data/yuki_memory.db"


def salida(sub: str = "") -> Path:
    """
    Raíz de lo que Yuki crea, o una carpeta dentro de ella.

    `salida("art")` en vez de `"output/art"`. La diferencia sólo se nota el día
    que alguien reubica el directorio —o el día que la suite escribe cinco
    ficheros de medios en el `output/` del repositorio, que es como se
    descubrió—.
    """
    raiz = Path(os.getenv("YUKI_OUTPUT_DIR", "").strip() or SALIDA_POR_DEFECTO)
    return raiz / sub if sub else raiz


def base_de_datos(config: Optional[Dict[str, Any]] = None) -> Path:
    """La memoria: entorno, luego configuración, luego el valor por defecto."""
    del_entorno = os.getenv("DATABASE_PATH", "").strip()
    if del_entorno:
        return Path(del_entorno)
    de_config = ((config or {}).get("memory", {}) or {}).get("database_path")
    return Path(de_config or BASE_POR_DEFECTO)
