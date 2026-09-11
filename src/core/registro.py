"""
Encender el log. Noventa y siete `logger.info` que no se veían.

`deploy/gce-startup.sh` declara `LOG_LEVEL=INFO` desde el primer despliegue y
**nadie lo leía**: no hay una sola llamada a `logging.basicConfig` en el
proyecto, así que el nivel efectivo era el de Python por defecto —WARNING en la
raíz— y todo lo que la instancia registraba con `logger.info` se perdía.

No es cosmético. Lo que se perdía es exactamente lo que se mira cuando algo va
mal: qué proveedor sirvió una respuesta, qué paso de un encargo se completó, si
una difusión salió, qué ruta se enrutó a qué modelo. La guía de operación manda
leer `docker logs yuki-daemon` para diagnosticar, y la mitad del diagnóstico no
estaba ahí. Un log vacío no falla: tranquiliza.

Se llama una vez, en los puntos de entrada. No cambia el nivel de un logger ya
configurado por quien nos incruste —`force=False`—, y las pruebas no lo invocan:
pytest gobierna su propia captura.
"""

from __future__ import annotations

import logging
import os
import sys

NIVEL_POR_DEFECTO = "INFO"

# Formato con el nombre del logger delante: los de este proyecto se llaman
# `Yuki.<subsistema>`, así que el origen se lee de un vistazo en `docker logs`.
FORMATO = "%(asctime)s %(levelname)-7s %(name)s — %(message)s"
FECHA = "%Y-%m-%dT%H:%M:%S"


def configurar(nivel: str | None = None) -> str:
    """
    Deja el log listo y devuelve el nivel aplicado.

    Un `LOG_LEVEL` con una errata no puede dejar la instancia muda ni tumbarla:
    se cae al valor por defecto y se avisa **por el propio log**, que a esas
    alturas ya funciona.
    """
    pedido = (nivel or os.getenv("LOG_LEVEL") or NIVEL_POR_DEFECTO).strip().upper()
    resuelto = getattr(logging, pedido, None)
    valido = isinstance(resuelto, int)

    logging.basicConfig(
        level=resuelto if valido else getattr(logging, NIVEL_POR_DEFECTO),
        format=FORMATO, datefmt=FECHA, stream=sys.stdout,
    )
    if not valido:
        logging.getLogger("Yuki").warning(
            "LOG_LEVEL='%s' no es un nivel conocido; se usa %s.", pedido, NIVEL_POR_DEFECTO)
        return NIVEL_POR_DEFECTO
    return pedido
