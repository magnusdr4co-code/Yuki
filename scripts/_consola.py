"""
Lo que comparten los cuatro guiones de operación.

`smoke_check`, `chaos_drill`, `restore_drill` y `simulate_day` habían crecido
cada uno por su lado y acabaron repitiendo lo mismo cuatro veces: la paleta de
colores, la fila con su marca y su detalle en gris, el sobre de `--json` y el
código de salida. Cuatro copias no son cuatro veces más trabajo, son cuatro
sitios donde la próxima corrección se aplica en tres.

Aquí está sólo lo que de verdad comparten. Lo que hace cada uno —qué comprueba,
qué rompe, qué simula— se queda en su guion, porque unificar cuatro informes que
dicen cosas distintas en un único armazón habría sido cambiar duplicación por
ceremonia.
"""

import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Sequence, Tuple

VERDE = "\033[92m"
ROJO = "\033[91m"
AMARILLO = "\033[93m"
TENUE = "\033[2m"
NEGRITA = "\033[1m"
FIN = "\033[0m"


def en_la_raiz() -> Path:
    """
    Deja el proyecto importable y devuelve su raíz.

    Los guiones se ejecutan por ruta (`python3 scripts/loquesea.py`), así que sin
    esto `src` no está en el camino de importación.
    """
    raiz = Path(__file__).resolve().parents[1]
    if str(raiz) not in sys.path:
        sys.path.insert(0, str(raiz))
    return raiz


def marca(correcto: bool) -> str:
    return f"{VERDE}✓{FIN}" if correcto else f"{ROJO}✗{FIN}"


def fila(nombre: str, correcto: bool, detalle: str = "", ancho: int = 22) -> str:
    """Una línea de informe: marca, nombre alineado y el porqué en gris."""
    linea = f"  {marca(correcto)} {nombre:<{ancho}}"
    return f"{linea} {TENUE}{detalle}{FIN}" if detalle else linea


def ejecutar(pruebas: Sequence[Tuple[str, Callable[[], Tuple[bool, str]]]]
             ) -> List[Dict[str, Any]]:
    """
    Corre las comprobaciones y recoge el resultado de cada una.

    Una comprobación que revienta es un fallo con su nombre y su traza corta, no
    una excepción que se lleva por delante el informe entero: el día que algo va
    mal es cuando más falta hacen las otras cinco.
    """
    resultados = []
    for nombre, prueba in pruebas:
        try:
            correcto, detalle = prueba()
        except Exception as exc:
            correcto, detalle = False, f"la comprobación falló: {type(exc).__name__}: {exc}"
        resultados.append({"prueba": nombre, "ok": correcto, "detalle": detalle})
    return resultados


def informar(resultados: Sequence[Dict[str, Any]], *, titulo: str = "",
             subtitulo: str = "", bien: str = "Todo en orden.",
             mal: str = "{n} comprobación(es) fallida(s).",
             como_json: bool = False, extra: Dict[str, Any] = None,
             ancho: int = 22) -> int:
    """
    Emite el informe y devuelve el código de salida: 0 si todo pasa.

    El código de salida es lo que permite colgar cualquiera de estos guiones de
    un temporizador o de la integración continua sin escribir nada alrededor.
    """
    fallidas = [r for r in resultados if not r["ok"]]

    if como_json:
        print(json.dumps({"ok": not fallidas, **(extra or {}), "resultados": list(resultados)},
                         ensure_ascii=False, indent=2))
        return 1 if fallidas else 0

    if titulo:
        print(f"\n{NEGRITA}{titulo}{FIN}")
    if subtitulo:
        print(f"{TENUE}{subtitulo}{FIN}")
    print()
    for resultado in resultados:
        print(fila(resultado["prueba"], resultado["ok"], resultado["detalle"], ancho))
    if fallidas:
        print(f"\n{ROJO}{mal.format(n=len(fallidas))}{FIN}")
    else:
        print(f"\n{VERDE}{bien}{FIN}")
    return 1 if fallidas else 0


def filtrar(pruebas: Sequence[Tuple[str, Any]], pedidas: str
            ) -> Tuple[List[Tuple[str, Any]], List[str]]:
    """
    Selección por `--solo a,b,c`.

    Devuelve también los nombres que no existen: pedir una comprobación mal
    escrita tiene que ser un error ruidoso y no un informe vacío que parece
    aprobado.
    """
    nombres = {nombre.strip() for nombre in pedidas.split(",") if nombre.strip()}
    desconocidas = sorted(nombres - {nombre for nombre, _ in pruebas})
    return [(n, p) for n, p in pruebas if n in nombres], desconocidas
