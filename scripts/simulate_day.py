#!/usr/bin/env python3
"""
Simulador de un día de Yuki: ver el carácter antes de desplegarlo.

Los números del libre albedrío —espontaneidad, audacia, umbral, aburrimiento—
se han venido ajustando a ojo, y el resultado sólo se ve en producción, días
después, en forma de «no hace nada» o «no para». Así estuvo meses la
espontaneidad completamente muerta: el tope del aburrimiento por debajo del
umbral que hacía falta para superarlo. Ninguna prueba lo veía porque todas
sembraban el impulso a mano, y desde fuera una facultad apagada se parece
demasiado a una instancia tranquila.

Esto recorre los setenta y dos ciclos de un día —el cron real dispara cada
veinte minutos— con **el código de verdad**: la política real, el bucle real, el
refuerzo real y el reloj circadiano real. Lo único fingido es el ejecutor, que
no llama a ningún proveedor ni gasta un céntimo. Devuelve lo que hay que mirar
antes de tocar un número:

  · cuántos actos propios salen al día, y a qué horas
  · de qué tipo, y si se cierra sobre uno solo
  · por qué **no** actuó el resto de los ciclos
  · cuánto tarda en querer algo si nadie le habla

`--fallos 0.5` simula un proveedor a medio caer: sirve para comprobar que un
intento fallido cuenta y no se reintenta en bucle. `--semilla` lo hace
reproducible; sin ella, cada pasada es distinta, que es justo lo que se quiere
mirar cuando se calibra la espontaneidad.
"""

import argparse
import json
import random
import sys
import types
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts._consola import (  # noqa: E402
    AMARILLO, FIN, NEGRITA, ROJO, TENUE, VERDE,
)

CICLO_MINUTOS = 20


def _config() -> Dict[str, Any]:
    import yaml

    try:
        with open("config.yaml", "r", encoding="utf-8") as fichero:
            return yaml.safe_load(fichero) or {}
    except OSError:
        return {}



def _amanece(diario) -> None:
    """
    Pasa la medianoche para el techo diario, sin borrar lo aprendido.

    El contador de actos del día va indexado por la fecha **real**, así que en
    una simulación de varios días todos caen en la misma y el techo del primero
    bloquea el resto: la primera versión de esto informaba de dos actos al día
    donde había seis y luego nada. Lo que amanece es el contador; los pesos del
    refuerzo y lo reciente siguen, que es lo que hace un día de verdad.
    """
    datos = diario.snapshot()
    datos["dias"] = {}
    datos["boredom"] = 0.0
    diario._escribir(datos)


# Un mundo por defecto: la gente responde de día y calla de madrugada. No
# pretende ser exacto —nadie tiene esa curva medida— sino **no ser plano**: con
# eco uniforme el refuerzo no tiene nada que aprender, y una simulación sin nada
# que aprender no dice nada del mecanismo que existe para aprender.
MUNDO_POR_DEFECTO = {0: 0.02, 1: 0.02, 2: 0.02, 3: 0.02, 4: 0.05, 5: 0.10,
                     6: 0.20, 7: 0.35, 8: 0.55, 9: 0.60, 10: 0.55, 11: 0.50,
                     12: 0.45, 13: 0.40, 14: 0.40, 15: 0.45, 16: 0.50, 17: 0.55,
                     18: 0.65, 19: 0.70, 20: 0.75, 21: 0.60, 22: 0.35, 23: 0.15}


def _mundo(descripcion: str) -> Dict[int, float]:
    """
    `--mundo "20:0.9,3:0.0"` describe quién contesta y a qué hora.

    Las horas no nombradas conservan el perfil por defecto: describir las
    veinticuatro para mover una sería una ceremonia que nadie va a repetir.
    """
    perfil = dict(MUNDO_POR_DEFECTO)
    for trozo in (descripcion or "").split(","):
        if not trozo.strip():
            continue
        hora, _, probabilidad = trozo.partition(":")
        perfil[int(hora) % 24] = max(0.0, min(1.0, float(probabilidad)))
    return perfil


def simular(politica, dias: int = 1, fallos: float = 0.0,
            semilla: int = None, energia: float = 0.9,
            mundo: Optional[Dict[int, float]] = None) -> Dict[str, Any]:
    """
    Recorre los ciclos de `dias` días con el bucle real. No toca nada durable.

    El diario vive en un temporal: una simulación que escribiera en el diario de
    agencia real contaminaría el censo con actos que Yuki no hizo, y ese censo
    es justo lo que se mira para decidir si está viva.
    """
    import tempfile

    from src.core.agency import AgencyLedger
    from src.core.circadian import CircadianClock
    from src.core.spark import AgencyLoop, WillQueue

    azar = random.Random(semilla)
    diario = AgencyLedger(path=str(Path(tempfile.mkdtemp()) / "simulacion.json"))
    reloj = CircadianClock(tz_name=politica.timezone)

    # El estado vital no decae aquí: lo que se está mirando es el carácter, y
    # mezclarlo con la curva de energía haría ilegible el resultado.
    vital = types.SimpleNamespace(
        energy=energia, inspiration=0.5, curiosity=0.5,
        has_energy_for=lambda coste: energia >= coste,
        spend_energy=lambda coste: None,
        apply_stimulus=lambda tipo, fuerza: None,
    )
    bucle = AgencyLoop(WillQueue(), vital, policy=politica, ledger=diario, rng=azar)

    perfil = mundo if mundo is not None else dict(MUNDO_POR_DEFECTO)
    ecos = 0
    actos: List[Dict[str, Any]] = []
    por_hora: Counter = Counter()
    por_tipo: Counter = Counter()
    ciclos = 0
    primer_acto_ciclos = None

    for dia in range(dias):
        _amanece(diario)
        for minuto in range(0, 24 * 60, CICLO_MINUTOS):
            momento = datetime(2026, 9, 8, minuto // 60, minuto % 60)
            decision = bucle.decidir(phase=reloj.current_phase(momento))
            ciclos += 1
            if not decision.actua:
                continue

            fallo = azar.random() < fallos
            resultado = ({"status": "failed", "error": "proveedor simulado caído"}
                         if fallo else {"status": "completed"})
            bucle.record_action(decision.impulso, resultado)

            # Y el mundo contesta, o no. Sin esto el refuerzo no aprende nunca:
            # todas las franjas y todas las acciones se quedan en su tasa
            # inicial, y la simulación mide el pulso de su día pero no lo único
            # que decide si ese pulso mejora.
            if not fallo and azar.random() < perfil.get(minuto // 60, 0.0):
                diario.registrar_eco(ventana_horas=6.0)
                ecos += 1

            if primer_acto_ciclos is None:
                primer_acto_ciclos = ciclos
            actos.append({"dia": dia + 1, "hora": f"{minuto // 60:02d}:{minuto % 60:02d}",
                          "accion": decision.impulso.tool_hint,
                          "origen": decision.impulso.source,
                          "resultado": resultado["status"]})
            por_hora[minuto // 60] += 1
            por_tipo[decision.impulso.tool_hint] += 1

    censo = diario.censo()
    return {
        "dias": dias,
        "ciclos": ciclos,
        "actos": actos,
        "actos_por_dia": len(actos) / dias,
        "techo_diario": politica.max_actions_per_day,
        "por_hora": dict(por_hora),
        "por_tipo": dict(por_tipo),
        "censo": censo,
        "ecos": ecos,
        "pesos_aprendidos": {a: round(bucle.model.peso(a, diario.snapshot()), 3)
                             for a in politica.allowed_actions},
        "ciclos_hasta_el_primer_acto": primer_acto_ciclos,
        "incoherencias": politica.incoherencias(),
    }


def _diagnostico(informe: Dict[str, Any]) -> List[str]:
    """
    Lo que un humano miraría y diría en voz alta.

    Un simulador que sólo escupe cifras obliga a saber ya qué es normal. Esto
    dice qué cifra está mal y por qué importa.
    """
    avisos = []
    por_dia = informe["actos_por_dia"]
    techo = informe["techo_diario"]

    if informe["incoherencias"]:
        avisos += [f"{ROJO}✗{FIN} {p}" for p in informe["incoherencias"]]

    if por_dia == 0:
        avisos.append(f"{ROJO}✗{FIN} No actúa ni una vez en todo el día: el carácter "
                      "está apagado, no tranquilo.")
    elif por_dia < 1:
        avisos.append(f"{AMARILLO}⚠{FIN} Menos de un acto propio al día. Es una diva "
                      "digital autónoma; a este ritmo no se nota que exista.")
    else:
        # Lo que importa no es que llegue a su cuota —para eso está—, sino que el
        # techo llegue a **bloquear** ciclos: ahí deja de ser una red de
        # seguridad y se convierte en la forma de ser de Yuki, decidida por un
        # número que nadie eligió para eso.
        bloqueados = informe["censo"].get("techo_diario", 0)
        if bloqueados:
            avisos.append(f"{AMARILLO}⚠{FIN} El techo diario ({techo}) bloquea "
                          f"{bloqueados} ciclo(s): a partir de ahí el límite hace de "
                          "carácter, y eso no es carácter.")

    tipos = informe["por_tipo"]
    if tipos:
        dominante, veces = max(tipos.items(), key=lambda par: par[1])
        total = sum(tipos.values())
        if total >= 4 and veces / total > 0.8:
            avisos.append(f"{AMARILLO}⚠{FIN} Cuatro de cada cinco actos son `{dominante}`: "
                          "se está cerrando sobre una sola forma de existir.")

    primero = informe["ciclos_hasta_el_primer_acto"]
    if primero is not None and primero <= 2:
        avisos.append(f"{AMARILLO}⚠{FIN} Actúa en el primer ciclo ocioso: una iniciativa "
                      "que se dispara con todo no se distingue del ruido.")

    if not avisos:
        avisos.append(f"{VERDE}✓{FIN} El carácter se comporta: quiere cosas, no siempre "
                      "las mismas, y no agota su día.")
    return avisos


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Simula el día de Yuki con el bucle de albedrío real")
    parser.add_argument("--dias", type=int, default=1)
    parser.add_argument("--fallos", type=float, default=0.0,
                        help="Fracción de actos que fallan (proveedor caído)")
    parser.add_argument("--semilla", type=int, default=None,
                        help="Hace la pasada reproducible")
    parser.add_argument("--espontaneidad", type=float, help="Sobrescribe agency.spontaneity")
    parser.add_argument("--umbral", type=float, help="Sobrescribe agency.min_intensity")
    parser.add_argument("--audacia", type=float, help="Sobrescribe agency.audacity")
    parser.add_argument("--aburrimiento", type=float,
                        help="Sobrescribe agency.boredom_gain: cuánto sube la tensión por "
                             "ciclo ocioso, que es lo que marca cada cuánto quiere algo")
    parser.add_argument("--json", action="store_true")
    argumentos = parser.parse_args()

    from src.core.agency import AgencyPolicy

    config = _config()
    agencia = dict(config.get("agency", {}) or {})
    for clave, valor in (("spontaneity", argumentos.espontaneidad),
                         ("min_intensity", argumentos.umbral),
                         ("audacity", argumentos.audacia),
                         ("boredom_gain", argumentos.aburrimiento)):
        if valor is not None:
            agencia[clave] = valor
    politica = AgencyPolicy.from_config({**config, "agency": agencia})

    informe = simular(politica, dias=argumentos.dias, fallos=argumentos.fallos,
                      semilla=argumentos.semilla)

    if argumentos.json:
        print(json.dumps(informe, ensure_ascii=False, indent=2))
        return 0 if not informe["incoherencias"] else 1

    print(f"\n{NEGRITA}Un día de Yuki{FIN} {TENUE}· {informe['ciclos']} ciclos "
          f"({argumentos.dias} día(s), uno cada {CICLO_MINUTOS} min){FIN}\n")
    print(f"  Espontaneidad {politica.spontaneity:g} · audacia {politica.audacity:g} · "
          f"umbral {politica.min_intensity:g} · techo {politica.max_actions_per_day}/día")
    if argumentos.fallos:
        print(f"  {TENUE}Proveedor caído en el {argumentos.fallos * 100:.0f}% de los actos{FIN}")
    print()

    print(f"{NEGRITA}Lo que hizo{FIN} {TENUE}({informe['actos_por_dia']:.1f} actos/día){FIN}")
    for acto in informe["actos"][:24]:
        marca = f"{ROJO}✗{FIN}" if acto["resultado"] == "failed" else f"{VERDE}●{FIN}"
        print(f"  {marca} día {acto['dia']} {acto['hora']}  {acto['accion']:<12}"
              f"{TENUE}{acto['origen']}{FIN}")
    if len(informe["actos"]) > 24:
        print(f"  {TENUE}… y {len(informe['actos']) - 24} más{FIN}")
    if not informe["actos"]:
        print(f"  {ROJO}nada en todo el día{FIN}")

    total_ciclos = sum(informe["censo"].values()) or 1
    print(f"\n{NEGRITA}Por qué no actuó el resto{FIN}")
    for motivo, veces in sorted(informe["censo"].items(), key=lambda par: -par[1]):
        if motivo == "actua":
            continue
        print(f"  {motivo:<18} {veces:>4} {TENUE}({veces * 100 // total_ciclos}%){FIN}")

    print(f"\n{NEGRITA}Diagnóstico{FIN}")
    for aviso in _diagnostico(informe):
        print(f"  {aviso}")
    print()
    return 1 if informe["incoherencias"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
