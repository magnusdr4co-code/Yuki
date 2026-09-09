#!/usr/bin/env python3
"""
Ensayo de restauración: comprobar que la copia sirve.

`docs/VIRTUALIZACION_Y_MEJORAS.md` dice, con razón, que **una copia sin
restaurar no está comprobada**. Y durante varias semanas eso fue exactamente lo
que hubo: un mecanismo de copia diario, verificado con `integrity_check` en el
momento de crearla, y ni una sola prueba de que el archivo resultante se pueda
volver a convertir en una Yuki que arranca.

Este guion la abre en un directorio temporal y comprueba lo que de verdad
importa el día que haga falta:

  · El tar se abre y no contiene rutas que escapen del directorio de destino.
  · La base restaurada abre, pasa `integrity_check` y **tiene recuerdos dentro**:
    una base íntegra y vacía es un desastre con buena salud.
  · El canon de Biblioteca viajó.
  · El manifiesto declara lo que hay, y su precinto de bitácora se puede
    contrastar con la cadena actual — que es lo único que detecta un corte por
    detrás.

Con `--ciclo` recorre además el circuito entero: fabrica una instancia de
juguete, la copia con el mecanismo real y la restaura. Ese modo no necesita
copia previa ni credenciales, así que es el que corre en integración continua y
el que delataría el día que `BackupManager` dejase de meter la base en el tar.

No modifica nada: ni la copia, ni la instancia. El directorio temporal se borra
al terminar salvo que se pida conservarlo.
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts._consola import ROJO, TENUE, FIN, informar  # noqa: E402
from src.tools.backup import restaurar, ultima_copia  # noqa: E402


def ciclo_completo(raiz: Path) -> Tuple[Optional[Path], List[Dict[str, Any]]]:
    """
    El ensayo entero: fabricar una instancia, copiarla y volver a levantarla.

    El modo normal comprueba una copia que ya existe, y eso deja fuera la mitad
    interesante: si `BackupManager` dejara de meter la base en el tar, no habría
    copia nueva que lo delatase hasta el día del incendio. Aquí se recorre el
    circuito completo contra una instancia de juguete —memoria con recuerdos,
    canon en Biblioteca, bitácora con anotaciones—, así que puede correr en
    integración continua, sin credenciales y sin tocar la instancia real.

    La bitácora del sandbox se aísla por `YUKI_BLACKBOX_PATH`: el precinto que
    viaja en el manifiesto se contrasta contra la cadena del propio ensayo, no
    contra la de producción, que aquí no pinta nada.
    """
    instancia = raiz / "instancia"
    datos = instancia / "data"
    salida = instancia / "output"
    (salida / "Biblioteca").mkdir(parents=True, exist_ok=True)
    datos.mkdir(parents=True, exist_ok=True)

    resultados: List[Dict[str, Any]] = []

    from src.memory.fts5_memory import FTS5MemoryEngine

    memoria = FTS5MemoryEngine(str(datos / "yuki_memory.db"))
    for numero in range(1, 4):
        memoria.add_memory(
            category="conversation",
            title=f"Ensayo {numero}",
            content=("Una conversación cualquiera, de las que sólo existen en la copia "
                     f"si el mecanismo funciona. Número {numero}."),
            user_id="ensayo",
        )
    (salida / "Biblioteca" / "poema.md").write_text(
        "# Ensayo\n\nLos medios se regeneran; lo escrito, no.\n", encoding="utf-8")

    # El entorno del ensayo se fija entero, no a medias. `BackupManager` deduce
    # el nombre del fichero de base de `DATABASE_PATH`: con una variable heredada
    # apuntando a otro nombre, la copia se crearía **sin base dentro** y el
    # ensayo daría por buena una copia vacía. Es justo el fallo que este guion
    # existe para detectar, así que no puede cometerlo él.
    entorno = {"YUKI_BLACKBOX_PATH": str(datos / "bitacora.jsonl"),
               "DATABASE_PATH": str(datos / "yuki_memory.db")}
    anteriores = {clave: os.environ.get(clave) for clave in entorno}
    os.environ.update(entorno)
    try:
        from src.core.blackbox import BlackBox
        from src.tools.backup import BackupManager

        bitacora = BlackBox()
        bitacora.record("ensayo_de_restauracion", {"fase": "antes de copiar"})

        gestor = BackupManager(data_dir=str(datos), output_dir=str(salida),
                               backup_dir=str(datos / "backups"), bucket="")
        copia_resultado = gestor.create()
        if copia_resultado.status != "success" or not copia_resultado.path:
            resultados.append({"prueba": "copia", "ok": False,
                               "detalle": f"no se pudo crear: {copia_resultado.error}"})
            return None, resultados

        copia = Path(copia_resultado.path)
        # El detalle nombra las piezas, no las cuenta. Un ensayo que falle a las
        # tres de la mañana tiene que decir **qué** faltaba sin que nadie lo
        # reproduzca: «3 piezas» no distingue una copia buena de una copia sin
        # memoria dentro.
        resultados.append({
            "prueba": "copia", "ok": True,
            "detalle": (f"{copia.stat().st_size / 1024:.1f} KiB · "
                        f"incluye {', '.join(copia_resultado.included) or 'nada'}"
                        + (f" · {len(copia_resultado.skipped)} pieza(s) ausentes"
                           if copia_resultado.skipped else "")),
        })
        resultados.extend(restaurar(copia, raiz / "restaurado"))
        return copia, resultados
    finally:
        for clave, valor in anteriores.items():
            if valor is None:
                os.environ.pop(clave, None)
            else:
                os.environ[clave] = valor


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensayo de restauración de una copia de Yuki")
    parser.add_argument("--copia", help="Ruta de la copia; por defecto, la más reciente")
    parser.add_argument("--directorio", default="data/backups",
                        help="Dónde buscar las copias")
    parser.add_argument("--conservar", action="store_true",
                        help="No borra el directorio restaurado, para inspeccionarlo")
    parser.add_argument("--ciclo", action="store_true",
                        help="Fabrica una instancia de juguete, la copia y la restaura. "
                             "No necesita copia previa ni credenciales: es el modo de la CI.")
    parser.add_argument("--json", action="store_true")
    argumentos = parser.parse_args()

    copia: Optional[Path]
    if argumentos.ciclo:
        copia = None
    else:
        copia = Path(argumentos.copia) if argumentos.copia else ultima_copia(argumentos.directorio)
        if copia is None or not copia.is_file():
            mensaje = (f"No hay ninguna copia en {argumentos.directorio}. "
                       "Créala con `python3 cli.py backup`, o ensaya el circuito "
                       "entero con `--ciclo`.")
            print(json.dumps({"ok": False, "error": mensaje}) if argumentos.json
                  else f"{ROJO}{mensaje}{FIN}")
            return 1

    destino = Path(tempfile.mkdtemp(prefix="yuki-restauracion-"))
    try:
        if argumentos.ciclo:
            copia, resultados = ciclo_completo(destino)
        else:
            resultados = restaurar(copia, destino)
    finally:
        if argumentos.conservar:
            print(f"{TENUE}Restaurado en {destino}{FIN}")
        else:
            import shutil

            shutil.rmtree(destino, ignore_errors=True)

    # En modo `--ciclo` la copia vive dentro del temporal que ya se borró.
    sello = (f"{copia} · {copia.stat().st_size / 1024:.1f} KiB"
             if copia is not None and copia.is_file() else "")

    return informar(
        resultados,
        titulo="Ensayo de restauración" + (" — circuito completo" if argumentos.ciclo else ""),
        subtitulo=sello,
        bien="La copia restaura correctamente.",
        mal="La copia NO sirve para restaurar: {n} fallo(s).",
        como_json=argumentos.json,
        extra={"copia": str(copia) if copia else None},
        ancho=18,
    )


if __name__ == "__main__":
    raise SystemExit(main())
