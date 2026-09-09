"""
Comandos de gobierno: lo que se mira o se toca cuando algo va mal.

Freno, bitácora, inventario de estado, gasto, copia, gemelo virtual y signos
vitales. Todos son de lectura salvo tres —poner el freno, olvidar a una persona
y crear una copia—, y esos tres dejan constancia de sí mismos.
"""

import json
from pathlib import Path

from .consola import BOLD, CYAN, DIM, GREEN, RED, RESET, YELLOW, print_banner


def cmd_brake(nivel=None, soltar=False, minutos=None, motivo="", as_json=False):
    """Freno de mano: pararla sin matarla."""
    from src.core.brake import NIVELES, Brake

    freno = Brake()

    # `--json` vale también al poner y soltar, no sólo al leer. Lo ignoraba en
    # las dos rutas que escriben, que son justamente las que automatiza quien
    # responde a un incidente: pedía JSON y recibía prosa, en silencio.
    if soltar:
        estado = freno.release(actor="cli", motivo=motivo)
        if as_json:
            print(json.dumps(estado.to_dict(), ensure_ascii=False, indent=2))
            return estado
        print(f"{GREEN}✓ Freno soltado.{RESET} {freno.describe()}")
        if estado.activo:
            print(f"{YELLOW}⚠ Sigue frenada desde {estado.origen}: eso no lo suelta el CLI.{RESET}")
        return estado

    if nivel:
        try:
            estado = freno.engage(nivel, motivo=motivo, actor="cli", minutos=minutos)
        except ValueError as exc:
            if as_json:
                print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
                return None
            print(f"{RED}✗ {exc}{RESET}")
            return None
        if as_json:
            print(json.dumps(estado.to_dict(), ensure_ascii=False, indent=2))
            return estado
        print(f"{YELLOW}🛑 {freno.describe()}{RESET}")
        return estado

    estado = freno.state()
    if as_json:
        print(json.dumps(estado.to_dict(), ensure_ascii=False, indent=2))
        return estado

    print_banner()
    color = RED if estado.activo else GREEN
    print(f"{color}{BOLD}🛑 {freno.describe()}{RESET}\n")
    for accion in ("publicar", "medios", "iniciativa"):
        permitido = freno.permits(accion)
        marca = f"{GREEN}✓{RESET}" if permitido else f"{RED}✗{RESET}"
        print(f"  {marca} {accion}")
    print(f"\n{DIM}Niveles: {', '.join(n for n in NIVELES if n != 'ninguno')}. "
          f"La variable de entorno YUKI_FRENO manda sobre el fichero.{RESET}")
    return estado


def cmd_blackbox(verificar=False, precinto=None, limite=10, as_json=False):
    """Bitácora encadenada: leerla, verificarla y sellarla."""
    from src.core.blackbox import BlackBox

    caja = BlackBox()

    if precinto == "crear":
        sello = caja.seal()
        print(json.dumps(sello, ensure_ascii=False, indent=2))
        return sello

    sello = None
    if precinto:
        try:
            with open(precinto, "r", encoding="utf-8") as fichero:
                sello = json.load(fichero)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"{RED}✗ No pude leer el precinto: {exc}{RESET}")
            return None

    if verificar or sello:
        informe = caja.verify(seal=sello)
        if as_json:
            print(json.dumps(informe, ensure_ascii=False, indent=2))
            return informe
        print_banner()
        estado = f"{GREEN}íntegra{RESET}" if informe["integra"] else f"{RED}MANIPULADA{RESET}"
        print(f"{CYAN}{BOLD}⛓️  Bitácora — {estado}{RESET}\n")
        print(f"  Anotaciones: {informe['entradas']}")
        print(f"  Cabeza: {DIM}{informe['cabeza'][:32]}…{RESET}")
        if sello:
            print(f"  Precinto contrastado: {DIM}{sello.get('head','')[:32]}…{RESET}")
        for problema in informe["problemas"]:
            print(f"  {RED}✗ seq {problema['seq']}: {problema['fallo']}{RESET} "
                  f"{DIM}{problema['detalle']}{RESET}")
        return informe

    entradas = caja.entries(limite=limite)
    if as_json:
        print(json.dumps([e.__dict__ for e in entradas], ensure_ascii=False, indent=2))
        return entradas
    print_banner()
    print(f"{CYAN}{BOLD}⛓️  Bitácora — últimas {len(entradas)} anotaciones{RESET}\n")
    for entrada in entradas:
        import datetime as _dt

        cuando = _dt.datetime.fromtimestamp(entrada.at).strftime("%Y-%m-%d %H:%M")
        print(f"  {DIM}{entrada.seq:>4} {cuando}{RESET}  {BOLD}{entrada.op}{RESET} "
              f"{DIM}por {entrada.actor}{RESET}")
        for clave, valor in list(entrada.detail.items())[:4]:
            print(f"       {DIM}{clave}: {valor}{RESET}")
    if not entradas:
        print(f"  {DIM}Todavía no hay nada anotado.{RESET}")
    return entradas


def cmd_state(exportar=None, olvidar=None, motivo="", as_json=False):
    """Inventario del estado durable, y los derechos de acceso y supresión."""
    from src.core.state_registry import StateRegistry

    registro = StateRegistry()

    if exportar:
        datos = registro.subject_export(exportar)
        print(json.dumps(datos, ensure_ascii=False, indent=2))
        return datos

    if olvidar:
        # `--json` también aquí. Antes esta rama imprimía la línea «Olvido
        # ejecutado» **y luego** el recibo, así que la salida no se podía
        # analizar; y el rechazo salía sólo en prosa. Quien automatiza una
        # supresión —que es lo que hace quien atiende una solicitud de verdad—
        # pedía JSON y recibía otra cosa, en silencio.
        try:
            recibo = registro.subject_forget(olvidar, actor="cli", reason=motivo)
        except ValueError as exc:
            if as_json:
                print(json.dumps({"error": str(exc), "sujeto": olvidar},
                                 ensure_ascii=False, indent=2))
                return None
            print(f"{RED}✗ {exc}{RESET}")
            return None
        if as_json:
            print(json.dumps(recibo, ensure_ascii=False, indent=2))
            return recibo
        print(f"{GREEN}✓ Olvido ejecutado{RESET}")
        print(json.dumps(recibo, ensure_ascii=False, indent=2))
        return recibo

    auditoria = registro.audit()
    if as_json:
        print(json.dumps(auditoria, ensure_ascii=False, indent=2))
        return auditoria

    print_banner()
    print(f"{CYAN}{BOLD}🗄️  Estado durable de Yuki{RESET}\n")
    print(f"  {auditoria['presentes']}/{len(auditoria['piezas'])} piezas presentes · "
          f"{auditoria['bytes_totales'] / 1024:.1f} KiB en total\n")
    for pieza in auditoria["piezas"]:
        marca = f"{GREEN}●{RESET}" if pieza["exists"] else f"{DIM}○{RESET}"
        personal = f" {YELLOW}[datos personales]{RESET}" if pieza["holds_personal_data"] else ""
        accionable = f" {RED}[acciona]{RESET}" if pieza["actionability"].startswith("ALTA") else ""
        print(f"  {marca} {BOLD}{pieza['id']}{RESET}{personal}{accionable}")
        print(f"     {DIM}{pieza['description']}{RESET}")
        print(f"     {DIM}{pieza['path']} · {pieza['bytes'] / 1024:.1f} KiB · "
              f"autoridad: {pieza['authority']} · recuperación: {pieza['recoverability']}{RESET}")
    registros = registro.audit_log(5)
    if registros:
        print(f"\n{BOLD}Últimas operaciones destructivas{RESET}")
        for entrada in registros:
            print(f"  {DIM}{entrada.get('cuando', '')} · {entrada['op']} · "
                  f"sujeto {entrada.get('sujeto', '?')} · "
                  f"{entrada.get('recuerdos_borrados', 0)} recuerdo(s){RESET}")
    return auditoria


def cmd_spend(as_json=False):
    """Gasto de hoy contra el presupuesto diario, sin tocar la red."""
    import yaml
    from src.core.spend_budget import SpendLedger

    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    libro = SpendLedger.from_config(config)
    if as_json:
        print(json.dumps({"consumo": libro.today(), "limites": libro.limits,
                          "usd_estimado": libro.usd_today(),
                          "usd_por_dia": libro.usd_per_day,
                          "habilitado": libro.enabled}, ensure_ascii=False, indent=2))
        return libro

    print_banner()
    print(f"{YELLOW}{BOLD}💳 Presupuesto de hoy{RESET}\n")
    print(f"{DIM}Libro: {libro.path} · zona: {libro.timezone_name} · "
          f"{'activo' if libro.enabled else 'DESHABILITADO'}{RESET}\n")
    consumo = libro.today()
    if not consumo:
        print(f"{GREEN}Sin gasto registrado hoy.{RESET}")
    for unidad in sorted(set(consumo) | set(libro.limits)):
        usado = consumo.get(unidad, 0)
        limite = libro.limits.get(unidad)
        if limite is None:
            print(f"  {unidad}: {usado:g} {DIM}(sin límite){RESET}")
            continue
        agotado = usado >= limite
        color = RED if agotado else GREEN
        print(f"  {unidad}: {color}{usado:g}/{limite:g}{RESET}")
    print(f"\n{DIM}Estimación: ${libro.usd_today():.2f}"
          + (f" de ${libro.usd_per_day:.2f}" if libro.usd_per_day is not None else "")
          + " · la música no se cotiza: no hay precio de referencia registrado.{}".format(RESET))
    return libro


def cmd_backup(as_json=False, ensayar=False):
    """Copia verificada de memoria, canon y estado; sube a Cloud Storage si hay bucket."""
    import yaml
    from src.tools.backup import BackupManager

    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    gestor = BackupManager.from_config(config)
    resultado = gestor.create()

    # Ensayar la copia recién hecha es la única forma de saber que sirve. El
    # `integrity_check` del momento de crearla dice que la base estaba sana, no
    # que el archivo se pueda volver a abrir.
    ensayo = None
    if ensayar and resultado.status == "success" and resultado.path:
        import shutil
        import tempfile

        from src.tools.backup import restaurar

        destino = Path(tempfile.mkdtemp(prefix="yuki-restauracion-"))
        try:
            ensayo = restaurar(Path(resultado.path), destino)
        finally:
            shutil.rmtree(destino, ignore_errors=True)

    if as_json:
        datos = resultado.to_dict()
        if ensayo is not None:
            datos["ensayo_de_restauracion"] = {"ok": all(r["ok"] for r in ensayo),
                                               "resultados": ensayo}
        print(json.dumps(datos, ensure_ascii=False, indent=2))
        return resultado

    print_banner()
    if resultado.status != "success":
        print(f"{RED}✗ La copia falló: {resultado.error}{RESET}")
        return resultado

    print(f"{GREEN}✓ Copia creada:{RESET} {resultado.path} "
          f"{DIM}({resultado.bytes / 1024:.1f} KiB){RESET}")
    print(f"{DIM}Integridad de la base: {resultado.integrity}{RESET}")
    print(f"{DIM}Incluido: {', '.join(resultado.included or []) or 'nada'}{RESET}")
    if resultado.skipped:
        print(f"{DIM}Ausente: {', '.join(resultado.skipped)}{RESET}")
    if resultado.remote_uri:
        print(f"{GREEN}✓ Fuera de la instancia:{RESET} {resultado.remote_uri}")
    else:
        print(f"{YELLOW}⚠ No sale de la instancia: {resultado.remote_error}{RESET}")

    if ensayo is not None:
        fallidas = [r for r in ensayo if not r["ok"]]
        print(f"\n{DIM}Ensayo de restauración:{RESET}")
        for prueba in ensayo:
            marca = f"{GREEN}✓{RESET}" if prueba["ok"] else f"{RED}✗{RESET}"
            print(f"  {marca} {prueba['prueba']:<18} {DIM}{prueba['detalle']}{RESET}")
        if fallidas:
            print(f"{RED}✗ La copia existe pero NO restaura.{RESET}")
        else:
            print(f"{GREEN}✓ Comprobada: la copia vuelve a levantarse.{RESET}")
    return resultado


def cmd_virtualize(output_path=None, as_json=False):
    """
    Gemelo virtual de la instancia: capacidades efectivas y limitadores.

    No toca la red ni gasta crédito: lee configuración, entorno y disco. Corre
    igual en la VM de producción, en la réplica local
    (`deploy/virtual/docker-compose.virtual.yml`) y en CI, así que las tres
    respuestas se pueden comparar tal cual.
    """
    import yaml
    from src.core.virtual_instance import VirtualInstance

    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    instancia = VirtualInstance(config)
    contenido = json.dumps(instancia.to_dict(), ensure_ascii=False, indent=2) if as_json \
        else instancia.render_markdown()

    if output_path:
        destino = Path(output_path)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(contenido + "\n", encoding="utf-8")
        print(f"{GREEN}Informe escrito en {destino}{RESET}")
    else:
        print(contenido)

    resumen = instancia.summary()
    if not as_json:
        color = RED if resumen["limitadores_bloqueantes"] else YELLOW
        print(f"\n{color}Limitadores abiertos: {resumen['limitadores_abiertos']} "
              f"(bloqueantes: {resumen['limitadores_bloqueantes']}){RESET}")
    return instancia


def cmd_pulse(as_json=False):
    """
    Signos vitales: si el proceso corre y si además Yuki vive.

    Devuelve código de salida distinto de cero cuando el diagnóstico es grave,
    para que se pueda colgar de un temporizador sin escribir nada alrededor.
    """
    import yaml
    from src.core.pulse import CATATONICA, RELACIONAL, VEGETATIVO, Pulse

    try:
        with open("config.yaml", "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except OSError:
        config = {}

    lectura = Pulse(config).read()

    if as_json:
        print(json.dumps(lectura.to_dict(), ensure_ascii=False, indent=2))
        return 0 if lectura.sana else 1

    print_banner()
    color = GREEN if lectura.gravedad == 0 else (YELLOW if lectura.sana else RED)
    print(f"{color}{lectura.estado.upper()}{RESET} — {lectura.motivo}\n")

    etiquetas = {VEGETATIVO: "respira", RELACIONAL: "la buscan"}
    for signo in lectura.signos:
        marca = f"{GREEN}●{RESET}" if signo.fresco else f"{RED}○{RESET}"
        familia = etiquetas.get(signo.tipo, "quiere")
        print(f"  {marca} {signo.id:<13} {DIM}{familia:<9}{RESET} "
              f"{signo.describe_edad():<18} {DIM}{signo.descripcion}{RESET}")
        if signo.nota:
            print(f"      {DIM}{signo.nota}{RESET}")

    if lectura.estado == CATATONICA:
        print(f"\n{RED}El contenedor está sano y ella no está haciendo nada.{RESET}")
        print(f"{DIM}Mirar: cli.py albedrio (techo diario, umbral), los cron del "
              f"planificador, y si el hilo de tareas sigue vivo en los registros.{RESET}")
    return 0 if lectura.sana else 1
