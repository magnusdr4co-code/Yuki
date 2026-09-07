#!/usr/bin/env python3
"""
Gemelo virtual de la instancia de Yuki, ejecutable suelto.

Equivale a `python3 cli.py virtualize`, pero sin importar el agente entero: útil
en CI y dentro de la VM, donde arrancar `YukiAgent` abriría la base de datos y
los adaptadores sólo para pedir un informe.

    python3 scripts/virtualize_instance.py
    python3 scripts/virtualize_instance.py --json --output output/virtual/informe.json
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml  # noqa: E402

from src.core.virtual_instance import VirtualInstance  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Capacidades reales y limitadores de la instancia")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--output", help="Fichero de destino; por defecto, salida estándar")
    parser.add_argument("--json", action="store_true", help="Emite JSON en vez de Markdown")
    parser.add_argument(
        "--fail-on-blocking", action="store_true",
        help="Devuelve código 1 si hay algún limitador bloqueante (para CI)",
    )
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as fichero:
        config = yaml.safe_load(fichero)

    instancia = VirtualInstance(config)
    contenido = json.dumps(instancia.to_dict(), ensure_ascii=False, indent=2) if args.json \
        else instancia.render_markdown()

    if args.output:
        destino = Path(args.output)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(contenido + "\n", encoding="utf-8")
        print(f"Informe escrito en {destino}")
    else:
        print(contenido)

    if args.fail_on_blocking and instancia.summary()["limitadores_bloqueantes"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
