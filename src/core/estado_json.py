"""
Leer y escribir el estado durable en JSON, de una sola manera.

Cinco módulos —agencia, ritmos, transparencia, deriva de persona y libro de
gasto— guardaban su estado en JSON, y los cinco habían escrito por su cuenta el
mismo par de funciones: una lectura que tolera un fichero corrupto y una
escritura atómica. Los `_escribir` eran idénticos línea por línea; los `_leer`
sólo se diferenciaban en el esquema vacío y en el texto del aviso.

Cinco copias no son cinco veces más trabajo: son cinco sitios donde aplicar la
próxima corrección, y cuatro donde olvidarla. Y aquí la corrección importa,
porque las dos propiedades que implementan no son cosméticas:

**La escritura es atómica.** Se escribe a un temporal y se renombra encima. Un
`write_text` directo sobre el fichero bueno deja medio JSON si el proceso muere
a la mitad —y el proceso muere a la mitad justo cuando se está desplegando, que
es cuando más cosas se escriben a la vez—.

**Un estado ilegible no revienta: se empieza de nuevo, y se dice.** Un disco a
medio corromper es cuando más falta hace que Yuki arranque. Perder el diario de
agencia cuesta lo aprendido; que no arranque cuesta la instancia entera. Pero se
avisa por el registro: un fichero que desaparece en silencio es indistinguible
de uno que nunca existió.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("Yuki.Estado")


def leer(path: Path, por_defecto: Callable[[], Dict[str, Any]],
         valido: Optional[Callable[[Dict[str, Any]], bool]] = None,
         que_es: str = "estado") -> Dict[str, Any]:
    """
    El contenido, o un esquema vacío si no hay o no se puede leer.

    `por_defecto` es una función y no un diccionario a propósito: devolver
    siempre el mismo objeto haría que dos lectores compartieran las mismas
    listas por dentro, y el primero que añadiera algo se lo encontraría el otro.

    `valido` comprueba la forma, no sólo que sea JSON. Un fichero con la sintaxis
    correcta y el esquema equivocado —de una versión anterior, de otro módulo—
    revienta más adelante y lejos de aquí, que es la peor forma de fallar.
    """
    if not path.is_file():
        return por_defecto()
    try:
        datos = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(datos, dict) and (valido is None or valido(datos)):
            return datos
        logger.warning("%s con forma inesperada en %s; se empieza uno nuevo.", que_es, path)
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        logger.warning("%s ilegible en %s; se empieza uno nuevo.", que_es, path)
    return por_defecto()


def escribir(path: Path, datos: Dict[str, Any]) -> None:
    """
    Escritura atómica: a un temporal, y renombrado encima.

    `os.replace` es atómico dentro del mismo sistema de ficheros, así que quien
    lea sólo puede encontrar el contenido viejo entero o el nuevo entero, nunca
    la mitad de uno.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporal = path.with_suffix(path.suffix + ".tmp")
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporal, path)
