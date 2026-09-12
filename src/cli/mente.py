"""
Comandos de la mente: dormir, querer, sonar a sí misma.

Ciclo de sueño, libre albedrío, deriva de persona y transparencia. Lo que se
ajusta aquí cambia cómo es Yuki, no cómo funciona la instancia.
"""

import asyncio
import json
import os

from .consola import BOLD, CYAN, DIM, GREEN, MAGENTA, RED, RESET, YELLOW, print_banner


def cmd_sleep(fase="noche", seco=False, as_json=False, deshacer=None):
    """Ejecuta una fase del ciclo de sueño sobre la memoria real."""

    import yaml

    from src.memory.fts5_memory import FTS5MemoryEngine
    from src.memory.sleep_cycle import SleepCycle, SleepPolicy

    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    ruta = os.getenv("DATABASE_PATH") or config.get("memory", {}).get(
        "database_path", "data/yuki_memory.db")
    ciclo = SleepCycle(FTS5MemoryEngine(db_path=ruta), SleepPolicy.from_config(config))

    # Sin agente no hay narrador: las fases corren deterministas y no se llama a
    # ningún proveedor desde la terminal.
    if fase == "fusiones":
        pendientes = ciclo.pending_merges()
        if as_json:
            print(json.dumps(pendientes, ensure_ascii=False, indent=2))
            return pendientes
        print_banner()
        print(f"{MAGENTA}{BOLD}🧷 Fusiones deshacibles{RESET}\n")
        if not pendientes:
            print(f"  {DIM}Ninguna dentro del periodo de gracia.{RESET}")
        for grupo in pendientes:
            print(f"  canónico {grupo['canonico']} · {grupo['titulo']} "
                  f"{DIM}(expira en {grupo['expira_en_dias']} días){RESET}")
            for absorbido in grupo["absorbidos"]:
                print(f"    ← {absorbido['id']} · {absorbido['titulo']}")
        print(f"\n  {DIM}Deshacer: python3 cli.py sueno --deshacer <canonico>{RESET}")
        return pendientes

    if deshacer is not None:
        recibo = ciclo.undo_merge(deshacer)
        print(json.dumps(recibo, ensure_ascii=False, indent=2))
        return recibo

    if fase == "nrem":
        resultado = asyncio.run(ciclo.nrem(dry_run=seco))
    elif fase == "rem":
        resultado = asyncio.run(ciclo.dream(dry_run=seco))
    elif fase == "olvido":
        resultado = ciclo.prune(dry_run=seco)
    else:
        resultado = asyncio.run(ciclo.full_night(dry_run=seco, with_prune=True))

    if as_json:
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
        return resultado

    print_banner()
    marca = f"{YELLOW}[ENSAYO EN SECO]{RESET} " if seco else ""
    print(f"{MAGENTA}{BOLD}🌙 Ciclo de sueño — {fase}{RESET} {marca}\n")
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    if fase in ("rem", "noche"):
        sueno = resultado if fase == "rem" else resultado.get("rem", {})
        if sueno.get("sonado"):
            print(f"\n{DIM}El sueño queda fuera de la recuperación normal: "
                  f"para leerlo hay que pedirlo.{RESET}")
    return resultado


def cmd_agency(as_json=False):
    """Estado del libre albedrío: carácter, aprendizaje y ritmos propios."""
    import yaml
    from src.core.agency import AgencyLedger, AgencyPolicy, ReinforcementModel
    from src.core.rituals import RitualStore

    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    politica = AgencyPolicy.from_config(config)
    diario = AgencyLedger(timezone_name=politica.timezone)
    modelo = ReinforcementModel(diario, politica)
    ritmos = RitualStore()
    datos = diario.snapshot()
    pesos = {a: round(modelo.peso(a, datos), 3) for a in politica.allowed_actions}

    if as_json:
        print(json.dumps({
            "politica": politica.to_public(),
            "aburrimiento": round(float(datos.get("boredom", 0.0)), 3),
            "acciones_hoy": diario.acciones_hoy(),
            "umbral_ahora": round(politica.umbral_efectivo(float(datos.get("boredom", 0.0))), 3),
            "pesos_por_accion": pesos,
            "esperando_eco": len(datos.get("pendientes", [])),
            "incoherencias": politica.incoherencias(),
            "censo_de_ciclos": diario.censo(),
            "censo_de_hoy": diario.censo_de_hoy(),
            "ritmos_propios": [r.to_dict() for r in ritmos.aprobados()],
            "ritmos_heredados_sin_activar": [r.to_dict() for r in ritmos.pendientes()],
        }, ensure_ascii=False, indent=2))
        return

    print_banner()
    print(f"{MAGENTA}{BOLD}🌱 Libre albedrío{RESET}\n")
    # Una contradicción en el carácter no da ningún error: apaga una facultad y
    # se queda quieta, que se parece demasiado a una decisión. Va lo primero.
    for problema in politica.incoherencias():
        print(f"  {RED}✗ Carácter incoherente:{RESET} {problema}")
    if politica.incoherencias():
        print()
    estado = "activa" if politica.enabled else f"{RED}apagada{RESET}"
    print(f"  Iniciativa: {estado}")
    print(f"  Espontaneidad {politica.spontaneity:g} · audacia {politica.audacity:g} · "
          f"constancia {politica.constancy:g}")
    print(f"  Umbral base {politica.min_intensity:g} → ahora "
          f"{politica.umbral_efectivo(float(datos.get('boredom', 0.0))):.3f} "
          f"{DIM}(aburrimiento {float(datos.get('boredom', 0.0)):.2f}){RESET}")
    print(f"  Actos hoy: {diario.acciones_hoy()}/{politica.max_actions_per_day} · "
          f"esperando eco: {len(datos.get('pendientes', []))}")
    censo = diario.censo()
    if censo:
        total = sum(censo.values())
        print(f"\n{BOLD}Por qué no actuó{RESET} {DIM}({total} ciclo(s) evaluados){RESET}")
        for motivo, veces in sorted(censo.items(), key=lambda par: -par[1]):
            marca = f"{GREEN}✓{RESET}" if motivo == "actua" else f"{DIM}·{RESET}"
            print(f"  {marca} {motivo:<18} {veces:>4} {DIM}({veces * 100 // total}%){RESET}")
    else:
        # Que no haya censo dice algo por sí mismo: el bucle no ha llegado a
        # evaluar ni una vez, que es distinto de evaluar y decidir que no.
        print(f"\n{YELLOW}El bucle de albedrío no ha evaluado todavía ni un solo ciclo.{RESET}")
        print(f"{DIM}No es que decida no actuar: es que no está corriendo. Mirar el "
              f"planificador y `cli.py pulso`.{RESET}")

    print(f"\n{BOLD}Lo que le funciona{RESET} {DIM}(tasa de eco suavizada){RESET}")
    for accion, peso in sorted(pesos.items(), key=lambda par: -par[1]):
        intentos = datos.get("acciones", {}).get(accion, {}).get("intentos", 0)
        barra = "█" * max(1, int(peso * 20))
        print(f"  {accion:<12} {peso:<6} {DIM}{barra} ({intentos} intento(s)){RESET}")

    propios = ritmos.aprobados()
    print(f"\n{BOLD}Ritmos propios{RESET}")
    for ritmo in propios:
        print(f"  ✅ {ritmo.name} — {ritmo.cron} · {ritmo.action} ({ritmo.runs} ejecuciones)")
    if not propios:
        print(f"  {DIM}Ninguno todavía.{RESET}")
    # Los ritmos de hoy nacen activos, así que esta sección sólo aparece con
    # propuestas de cuando hacía falta aprobar: son ritmos suyos que no suenan.
    pendientes = ritmos.pendientes()
    if pendientes:
        print(f"\n{YELLOW}Heredados sin activar (esperan una aprobación que ya no se pide):{RESET}")
        for ritmo in pendientes:
            print(f"  🕯️  {ritmo.id} · {ritmo.name} — {ritmo.cron} · {ritmo.action}")
            print(f"      {DIM}{ritmo.reason}{RESET}")
        print(f"  {DIM}`!ritmo aprobar <id>` en el DM los pone a sonar.{RESET}")


def cmd_persona(as_json=False):
    """Deriva de persona: cuánto se ha ido de su registro y cuántas veces se reancló."""
    import yaml
    from src.core.persona_anchor import PersonaAnchor, PersonaPolicy

    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    soul = ""
    if os.path.exists("SOUL.md"):
        with open("SOUL.md", "r", encoding="utf-8") as f:
            soul = f.read()

    vigia = PersonaAnchor(soul_text=soul, policy=PersonaPolicy.from_config(config))
    informe = vigia.report()

    if as_json:
        print(json.dumps(informe, ensure_ascii=False, indent=2))
        return

    print_banner()
    print(f"{CYAN}{BOLD}🪞 Deriva de persona{RESET}\n")
    if not informe["muestras"]:
        print(f"  {DIM}Sin muestras todavía: hablará y se medirá sola.{RESET}")
        return
    media = informe["media_reciente"]
    color = GREEN if media and media >= informe["umbral"] else RED
    print(f"  Muestras: {informe['muestras']} · umbral {informe['umbral']}")
    print(f"  Media reciente: {color}{media}{RESET} · mínimo {informe['minimo_reciente']}")
    print(f"  Turnos por debajo del umbral: {informe['por_debajo_del_umbral']}")
    print(f"  Reanclajes aplicados: {informe['anclajes']}")
    if informe["marcadores_frecuentes"]:
        print(f"\n{BOLD}Por dónde se va{RESET}")
        for marcador, veces in informe["marcadores_frecuentes"]:
            print(f"  {veces}× {DIM}{marcador}{RESET}")


def cmd_transparency(marcar=False, as_json=False):
    """Auditoría del Artículo 50: qué se ha declarado y qué material está marcado."""
    import yaml
    from src.core.transparency import (
        DisclosureLedger, MediaMarker, TransparencyPolicy, audit_directory,
    )

    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    politica = TransparencyPolicy.from_config(config)
    registro = DisclosureLedger(reminder_days=politica.reminder_days)
    auditoria = audit_directory("output")

    if marcar and auditoria["sin_marcar"]:
        marcador = MediaMarker(politica)
        for ruta in list(auditoria["sin_marcar"]):
            marcador.mark(ruta, model="retroactivo", kind="archivo")
        auditoria = audit_directory("output")

    if as_json:
        print(json.dumps({
            "politica": {"enabled": politica.enabled, "mark_media": politica.mark_media,
                         "reminder_days": politica.reminder_days},
            "declaraciones": registro.disclosures(),
            "auditoria": auditoria,
        }, ensure_ascii=False, indent=2))
        return

    print_banner()
    print(f"{YELLOW}{BOLD}⚖️  Transparencia (Artículo 50, en vigor desde 2026-08-02){RESET}\n")
    estado = f"{GREEN}activa{RESET}" if politica.enabled else f"{RED}DESACTIVADA{RESET}"
    print(f"  Declaración de naturaleza: {estado} · se repite cada {politica.reminder_days} días")
    print(f"  Personas ya informadas: {len(registro.disclosures())}")
    print(f"\n  Material generado: {auditoria['total']} fichero(s)")
    print(f"  {GREEN}Marcados: {len(auditoria['marcados'])}{RESET}")
    if auditoria["sin_marcar"]:
        print(f"  {RED}Sin marcar: {len(auditoria['sin_marcar'])}{RESET}")
        for ruta in auditoria["sin_marcar"][:10]:
            print(f"    • {ruta}")
        if len(auditoria["sin_marcar"]) > 10:
            print(f"    {DIM}… y {len(auditoria['sin_marcar']) - 10} más{RESET}")
        print(f"\n  {DIM}Márcalos con: python3 cli.py transparency --marcar{RESET}")
    else:
        print(f"  {DIM}Nada pendiente de marcar.{RESET}")
