#!/usr/bin/env python3
"""
Comprobación de humo posterior a un despliegue.

`docs/PRODUCTION_STATUS.md` describe cinco pasos manuales tras cada despliegue.
Un procedimiento que sólo vive en prosa se hace mal el día que hay prisa —que es
exactamente el día que importa—, así que aquí están ejecutables y con código de
salida: cero si la instancia está sana, distinto de cero si no.

Comprueba lo que puede romperse en silencio y costar caro:

  · La base de datos abre y pasa `integrity_check`.
  · La bitácora encadenada no ha sido manipulada.
  · No hay material sintético sin marcar (Artículo 50).
  · No queda ningún limitador **bloqueante** en el gemelo virtual.
  · El presupuesto del día no está ya agotado al arrancar.
  · Si se le da una URL, `/health` responde y el Salón está vivo.

No genera medios, no llama a ningún modelo y no gasta un céntimo: una prueba de
humo que consume crédito deja de ejecutarse a la tercera semana.
"""

import argparse
import json
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml  # noqa: E402

VERDE = "\033[92m"
ROJO = "\033[91m"
AMARILLO = "\033[93m"
TENUE = "\033[2m"
FIN = "\033[0m"


def _config() -> Dict[str, Any]:
    try:
        with open("config.yaml", "r", encoding="utf-8") as fichero:
            return yaml.safe_load(fichero) or {}
    except OSError:
        return {}


def comprobar_memoria(config: Dict[str, Any]) -> Tuple[bool, str]:
    ruta = (config.get("memory", {}) or {}).get("database_path", "data/yuki_memory.db")
    if not Path(ruta).is_file():
        # No es un fallo en una instancia recién creada: se dice y se sigue.
        return True, f"sin base todavía en {ruta} (instancia nueva)"
    try:
        with sqlite3.connect(f"file:{ruta}?mode=ro", uri=True) as conexion:
            estado = conexion.execute("PRAGMA integrity_check").fetchone()[0]
            recuerdos = conexion.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    except sqlite3.Error as exc:
        return False, f"la memoria no abre: {exc}"
    if estado != "ok":
        return False, f"integrity_check devolvió '{estado}'"
    return True, f"{recuerdos} recuerdo(s), integridad ok"


def comprobar_bitacora(_: Dict[str, Any]) -> Tuple[bool, str]:
    from src.core.blackbox import BlackBox

    informe = BlackBox().verify()
    if not informe["integra"]:
        primeros = ", ".join(p["fallo"] for p in informe["problemas"][:3])
        return False, f"cadena de auditoría manipulada: {primeros}"
    return True, f"{informe['entradas']} anotación(es) encadenadas, sin manipular"


def comprobar_marcado(_: Dict[str, Any]) -> Tuple[bool, str]:
    from src.core.transparency import audit_directory

    auditoria = audit_directory("output")
    if auditoria["sin_marcar"]:
        return False, (f"{len(auditoria['sin_marcar'])} fichero(s) sin marca de origen "
                       "sintético (Artículo 50)")
    return True, f"{len(auditoria['marcados'])} fichero(s) marcados, ninguno pendiente"


def comprobar_limitadores(config: Dict[str, Any]) -> Tuple[bool, str]:
    from src.core.virtual_instance import VirtualInstance

    instancia = VirtualInstance(config)
    resumen = instancia.summary()
    bloqueantes = [lim for lim in instancia.limiters if lim.severity == "bloqueante"]
    if bloqueantes:
        return False, "bloqueante: " + "; ".join(f"{lim.id} {lim.title}" for lim in bloqueantes)
    return True, (f"{resumen['limitadores_abiertos']} limitador(es) abiertos, "
                  "ninguno bloqueante")


def comprobar_presupuesto(config: Dict[str, Any]) -> Tuple[bool, str]:
    from src.core.spend_budget import VIDEO_SEGUNDOS, SpendLedger

    libro = SpendLedger.from_config(config)
    if not libro.enabled:
        return False, "el presupuesto está desactivado: nada acota el gasto de medios"
    decision = libro.check(VIDEO_SEGUNDOS, 8)
    if not decision.allowed:
        return False, f"sin margen para un solo clip: {decision.reason}"
    return True, f"margen disponible · hoy {libro.describe()}"


def comprobar_freno(_: Dict[str, Any]) -> Tuple[bool, str]:
    """
    El freno puesto no es un fallo: es una decisión. Pero tiene que verse.

    Un despliegue sobre una instancia frenada y nadie recordándolo es media hora
    de gente preguntándose por qué Yuki no hace nada.
    """
    from src.core.brake import Brake

    freno = Brake()
    estado = freno.state()
    if estado.activo:
        return True, f"⚠ {freno.describe()}"
    return True, "sin freno"


def comprobar_salon(url: str) -> Tuple[bool, str]:
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/health", timeout=10) as respuesta:
            cuerpo = json.loads(respuesta.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError) as exc:
        return False, f"/health no respondió: {type(exc).__name__}"
    if cuerpo.get("status") != "ok":
        return False, f"/health devolvió {cuerpo}"
    return True, f"vivo · agente cargado: {cuerpo.get('agent_loaded')}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Comprobación de humo de la instancia de Yuki")
    parser.add_argument("--url", help="URL del Salón para comprobar /health (opcional)")
    parser.add_argument("--json", action="store_true", help="Emite JSON")
    parser.add_argument("--permisivo", action="store_true",
                        help="Informa de los fallos pero devuelve 0 igualmente")
    parser.add_argument("--solo", default="",
                        help="Comprobaciones a ejecutar, separadas por comas. En integración "
                             "continua interesan las que no dependen del entorno: "
                             "--solo memoria,bitacora,marcado_articulo_50")
    argumentos = parser.parse_args()

    config = _config()
    pruebas: List[Tuple[str, Callable[[], Tuple[bool, str]]]] = [
        ("memoria", lambda: comprobar_memoria(config)),
        ("bitacora", lambda: comprobar_bitacora(config)),
        ("marcado_articulo_50", lambda: comprobar_marcado(config)),
        ("limitadores", lambda: comprobar_limitadores(config)),
        ("presupuesto", lambda: comprobar_presupuesto(config)),
        ("freno", lambda: comprobar_freno(config)),
    ]
    if argumentos.url:
        pruebas.append(("salon", lambda: comprobar_salon(argumentos.url)))

    if argumentos.solo:
        pedidas = {nombre.strip() for nombre in argumentos.solo.split(",") if nombre.strip()}
        desconocidas = pedidas - {nombre for nombre, _ in pruebas}
        if desconocidas:
            print(f"{ROJO}Comprobaciones desconocidas: {', '.join(sorted(desconocidas))}{FIN}")
            return 2
        pruebas = [(nombre, prueba) for nombre, prueba in pruebas if nombre in pedidas]

    resultados = []
    for nombre, prueba in pruebas:
        try:
            correcto, detalle = prueba()
        except Exception as exc:  # una comprobación rota es un fallo, no un silencio
            correcto, detalle = False, f"la comprobación falló: {type(exc).__name__}: {exc}"
        resultados.append({"prueba": nombre, "ok": correcto, "detalle": detalle})

    fallidas = [r for r in resultados if not r["ok"]]

    if argumentos.json:
        print(json.dumps({"ok": not fallidas, "resultados": resultados},
                         ensure_ascii=False, indent=2))
    else:
        print(f"\n{TENUE}Comprobación de humo — instancia de Yuki{FIN}\n")
        for resultado in resultados:
            marca = f"{VERDE}✓{FIN}" if resultado["ok"] else f"{ROJO}✗{FIN}"
            print(f"  {marca} {resultado['prueba']:<22} {TENUE}{resultado['detalle']}{FIN}")
        if fallidas:
            print(f"\n{ROJO}{len(fallidas)} comprobación(es) fallida(s).{FIN}")
        else:
            print(f"\n{VERDE}Instancia sana.{FIN}")

    if fallidas and not argumentos.permisivo:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
