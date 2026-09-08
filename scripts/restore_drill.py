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
import sqlite3
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

VERDE = "\033[92m"
ROJO = "\033[91m"
AMARILLO = "\033[93m"
TENUE = "\033[2m"
NEGRITA = "\033[1m"
FIN = "\033[0m"


def ultima_copia(directorio: str) -> Optional[Path]:
    copias = sorted(Path(directorio).glob("yuki_backup_*.tar.gz"))
    return copias[-1] if copias else None


def _rutas_seguras(archivo: tarfile.TarFile) -> Tuple[bool, str]:
    """
    Ninguna entrada puede escapar del destino.

    Un tar con `../` o rutas absolutas dentro sobrescribe lo que quiera al
    extraerlo. Aquí la copia la hace el propio proyecto, así que no debería
    ocurrir nunca —y por eso mismo conviene comprobarlo: los fallos que "no
    pueden pasar" son los que nadie mira.
    """
    for miembro in archivo.getmembers():
        nombre = Path(miembro.name)
        if nombre.is_absolute() or ".." in nombre.parts:
            return False, f"entrada peligrosa en el archivo: {miembro.name}"
        if miembro.issym() or miembro.islnk():
            return False, f"enlace dentro del archivo: {miembro.name}"
    return True, "todas las rutas quedan dentro del destino"


def restaurar(copia: Path, destino: Path) -> List[Dict[str, Any]]:
    """Abre la copia y comprueba lo restaurado. Devuelve el informe por prueba."""
    resultados: List[Dict[str, Any]] = []

    def anotar(nombre: str, correcto: bool, detalle: str) -> None:
        resultados.append({"prueba": nombre, "ok": correcto, "detalle": detalle})

    try:
        with tarfile.open(copia, "r:gz") as archivo:
            seguro, detalle = _rutas_seguras(archivo)
            anotar("rutas_del_archivo", seguro, detalle)
            if not seguro:
                return resultados
            archivo.extractall(destino)
            nombres = archivo.getnames()
    except (tarfile.TarError, OSError) as exc:
        anotar("apertura", False, f"la copia no se puede abrir: {exc}")
        return resultados

    anotar("apertura", True, f"{len(nombres)} entrada(s) extraídas")

    # Manifiesto
    manifiesto_ruta = destino / "MANIFIESTO.json"
    manifiesto: Dict[str, Any] = {}
    if manifiesto_ruta.is_file():
        try:
            manifiesto = json.loads(manifiesto_ruta.read_text(encoding="utf-8"))
            anotar("manifiesto", True,
                   f"creado {manifiesto.get('creado')} · integridad declarada "
                   f"'{manifiesto.get('integridad_db')}'")
        except json.JSONDecodeError as exc:
            anotar("manifiesto", False, f"ilegible: {exc}")
    else:
        anotar("manifiesto", False, "la copia no trae manifiesto")

    # La memoria: lo único verdaderamente irremplazable.
    base = next(destino.glob("*.db"), None)
    if base is None:
        anotar("memoria", False, "no hay base de datos en la copia")
    else:
        try:
            with sqlite3.connect(f"file:{base}?mode=ro", uri=True) as conexion:
                estado = conexion.execute("PRAGMA integrity_check").fetchone()[0]
                recuerdos = conexion.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
                categorias = dict(conexion.execute(
                    "SELECT category, COUNT(*) FROM memories GROUP BY category"))
            if estado != "ok":
                anotar("memoria", False, f"integrity_check tras restaurar: '{estado}'")
            elif recuerdos == 0:
                # Una base íntegra y vacía es un desastre con buena salud.
                anotar("memoria", False, "la base restaurada está vacía")
            else:
                anotar("memoria", True,
                       f"{recuerdos} recuerdo(s) en {len(categorias)} categoría(s), integridad ok")
        except sqlite3.Error as exc:
            anotar("memoria", False, f"la base restaurada no abre: {exc}")

    # El canon: los medios se regeneran, la obra archivada no.
    biblioteca = destino / "Biblioteca"
    if biblioteca.is_dir():
        piezas = [p for p in biblioteca.rglob("*") if p.is_file()]
        anotar("biblioteca", True, f"{len(piezas)} fichero(s) de canon restaurados")
    else:
        anotar("biblioteca", True, "sin Biblioteca en esta instancia (no es un fallo)")

    # El precinto: lo único que detecta un corte por detrás en la bitácora.
    precinto = manifiesto.get("precinto_bitacora")
    if not precinto or "error" in precinto:
        anotar("precinto", True, "la copia no trae precinto de bitácora todavía")
    else:
        try:
            from src.core.blackbox import BlackBox

            informe = BlackBox().verify(seal=precinto)
            if informe["truncada"]:
                anotar("precinto", False,
                       "la bitácora actual no contiene el precinto de esta copia: "
                       "alguien cortó la cadena por detrás")
            else:
                anotar("precinto", True,
                       f"la cadena actual contiene el precinto ({precinto.get('entradas')} "
                       "anotaciones entonces)")
        except Exception as exc:
            anotar("precinto", False, f"no se pudo contrastar: {type(exc).__name__}")

    return resultados


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
        resultados.append({
            "prueba": "copia", "ok": True,
            "detalle": (f"{copia.stat().st_size / 1024:.1f} KiB · "
                        f"{len(copia_resultado.included)} pieza(s) incluidas"),
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

    fallidas = [r for r in resultados if not r["ok"]]

    if argumentos.json:
        print(json.dumps({"ok": not fallidas, "copia": str(copia) if copia else None,
                          "resultados": resultados}, ensure_ascii=False, indent=2))
    else:
        print(f"\n{NEGRITA}Ensayo de restauración"
              f"{' — circuito completo' if argumentos.ciclo else ''}{FIN}")
        if copia is not None and copia.is_file():
            print(f"{TENUE}{copia} · {copia.stat().st_size / 1024:.1f} KiB{FIN}\n")
        else:
            print()
        for resultado in resultados:
            marca = f"{VERDE}✓{FIN}" if resultado["ok"] else f"{ROJO}✗{FIN}"
            print(f"  {marca} {resultado['prueba']:<18} {TENUE}{resultado['detalle']}{FIN}")
        if fallidas:
            print(f"\n{ROJO}La copia NO sirve para restaurar: {len(fallidas)} fallo(s).{FIN}")
        else:
            print(f"\n{VERDE}La copia restaura correctamente.{FIN}")

    return 1 if fallidas else 0


if __name__ == "__main__":
    raise SystemExit(main())
