#!/usr/bin/env python3
"""
La línea de órdenes de Yuki: declarar los argumentos y repartir.

Los comandos viven en `src/cli/`, agrupados por lo que hacen —gobierno, mente y
operación—. Aquí sólo queda la interfaz. Antes estaban las tres cosas juntas en
mil doscientas líneas, que es un fichero que se lee por búsqueda y no por
lectura: cada añadido acababa pegado donde cayera.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.cli.gobierno import (  # noqa: E402
    cmd_backup, cmd_blackbox, cmd_brake, cmd_pulse, cmd_spend, cmd_state, cmd_virtualize,
)
from src.cli.mente import (  # noqa: E402
    cmd_agency, cmd_persona, cmd_sleep, cmd_transparency,
)
from src.cli.operacion import (  # noqa: E402
    cmd_benchmark, cmd_chat, cmd_cron_task, cmd_daemon, cmd_list_skills, cmd_skill,
    cmd_vertex_check, cmd_web,
)

def main():
    parser = argparse.ArgumentParser(description="CLI de Yuki - Diva Digital Autónoma (Hermes Agent)")
    subparsers = parser.add_subparsers(dest="command", help="Comando a ejecutar")

    subparsers.add_parser("chat", help="Conversación interactiva en terminal")
    subparsers.add_parser("list-skills", help="Listar habilidades estándar en skills/")

    web_p = subparsers.add_parser("web", help="Iniciar Salón Web Dashboard & Canvas API")
    web_p.add_argument("--port", default=None, type=int,
                       help="Puerto HTTP (por defecto: variable de entorno PORT, o 8080)")

    skill_p = subparsers.add_parser("skill", help="Ejecutar una habilidad estándar")
    skill_p.add_argument("name", help="Nombre de la skill")
    skill_p.add_argument("--title", default="El Río Antes de Tener Nombre", help="Título provisional")
    skill_p.add_argument("--concept", default="lluvia sobre metal y pan de oro", help="Concepto visual o tema")
    skill_p.add_argument("--text", default="El agua siempre encuentra su camino.", help="Texto a sintetizar o curar")
    skill_p.add_argument("--scale", default="insen", help="Escala musical (insen, hirajoshi, kumoi, iwato)")
    # Sin valor por defecto a propósito: con uno, «no lo dijo» y «pidió 84» son
    # indistinguibles, y el criterio de composición quedaría siempre pisado por
    # un número que nadie escribió.
    skill_p.add_argument("--bpm", default=None, type=int,
                         help="BPM del beat (si se omite, lo decide la letra o el criterio)")
    skill_p.add_argument("--lyrics-id", dest="lyrics_id", default=None,
                         help="Identificador de Biblioteca de la letra sobre la que componer")
    skill_p.add_argument("--mood", default="lluvia sobre metal", help="Atmósfera musical")
    skill_p.add_argument("--guest", default="Visitante", help="Nombre del invitado")
    skill_p.add_argument("--intention", default="buscar serenidad", help="Intención de la ceremonia")
    skill_p.add_argument("--duration", default=6, type=int,
                         help="Duración del vídeo en segundos (3-10). Se factura por segundo")
    skill_p.add_argument("--image-path", dest="image_path", default=None,
                         help="Portada de partida para /animar-portada")

    cron_p = subparsers.add_parser("cron-task", help="Ejecutar tarea autónoma")
    cron_p.add_argument("--name", default="morning_inspiration_drop", help="Nombre de la tarea")

    subparsers.add_parser("memory-benchmark", help="Ejecutar benchmark de memoria SQLite FTS5 vs OpenClaw")
    subparsers.add_parser("vertex-check", help="Probar la ruta de Vertex AI y estimar el gasto del crédito")
    subparsers.add_parser("run-daemon", help="Ejecutar daemon de presencia continua 24/7")

    virt = subparsers.add_parser(
        "virtualize",
        help="Gemelo virtual de la instancia: capacidades reales y limitadores (sin red)",
    )
    virt.add_argument("--output", help="Escribe el informe en un fichero en vez de la salida estándar")
    virt.add_argument("--json", action="store_true", help="Emite JSON en vez de Markdown")

    gasto = subparsers.add_parser(
        "spend", help="Gasto de hoy frente al presupuesto diario (vídeo, imagen, música, voz, tokens)",
    )
    gasto.add_argument("--json", action="store_true", help="Emite JSON")

    copia = subparsers.add_parser(
        "backup", help="Copia verificada de memoria, canon y estado (y subida si hay bucket)",
    )
    copia.add_argument("--json", action="store_true", help="Emite JSON")
    copia.add_argument("--ensayar", action="store_true",
                       help="Restaura la copia recién creada para comprobar que sirve")

    albedrio = subparsers.add_parser(
        "albedrio", help="Estado del libre albedrío: carácter, refuerzo y ritmos propios",
    )
    albedrio.add_argument("--json", action="store_true", help="Emite JSON")

    transparencia = subparsers.add_parser(
        "transparency",
        help="Auditoría del Artículo 50: declaración de naturaleza y marcado del material",
    )
    transparencia.add_argument("--marcar", action="store_true",
                               help="Marca retroactivamente el material que aún no lo esté")
    transparencia.add_argument("--json", action="store_true", help="Emite JSON")

    persona = subparsers.add_parser(
        "persona", help="Deriva de persona: cuánto se aleja de su registro y reanclajes",
    )
    persona.add_argument("--json", action="store_true", help="Emite JSON")

    pulso = subparsers.add_parser(
        "pulso",
        help="Signos vitales: distingue que el proceso corra de que Yuki viva",
    )
    pulso.add_argument("--json", action="store_true", help="Emite JSON")

    estado = subparsers.add_parser(
        "estado",
        help="Inventario del estado durable, y derechos de acceso y supresión de una persona",
    )
    estado.add_argument("--exportar", metavar="USER_ID",
                        help="Todo lo que Yuki guarda sobre esa persona, en JSON")
    estado.add_argument("--olvidar", metavar="USER_ID",
                        help="Borra de verdad lo que guarda sobre esa persona y emite recibo")
    estado.add_argument("--motivo", default="", help="Motivo del olvido, para la auditoría")
    estado.add_argument("--json", action="store_true", help="Emite JSON")

    sueno = subparsers.add_parser(
        "sueno", help="Ciclo de sueño: consolidar (nrem), soñar (rem), olvidar, o la noche entera",
    )
    sueno.add_argument("--fase", choices=["nrem", "rem", "olvido", "noche", "fusiones"],
                       default="noche")
    sueno.add_argument("--deshacer", type=int, metavar="CANONICO",
                       help="Deshace una fusión dentro del periodo de gracia")
    sueno.add_argument("--seco", action="store_true",
                       help="Ensayo en seco: calcula y muestra, sin tocar la memoria")
    sueno.add_argument("--json", action="store_true", help="Emite JSON")

    bitacora = subparsers.add_parser(
        "bitacora",
        help="Bitácora encadenada de actos: leerla, verificar que nadie la tocó, sellarla",
    )
    bitacora.add_argument("--verificar", action="store_true",
                          help="Recorre la cadena y dice si alguien la manipuló")
    bitacora.add_argument("--precinto", metavar="RUTA|crear",
                          help="'crear' emite un precinto; una ruta lo contrasta con la cadena")
    bitacora.add_argument("--limite", type=int, default=10)
    bitacora.add_argument("--json", action="store_true", help="Emite JSON")

    freno = subparsers.add_parser(
        "freno", help="Freno de mano: parar la iniciativa, los medios o la publicación",
    )
    freno.add_argument("--nivel", choices=["publicacion", "medios", "todo"],
                       help="Pone el freno en ese nivel")
    freno.add_argument("--soltar", action="store_true", help="Suelta el freno del fichero")
    freno.add_argument("--minutos", type=float, help="Caducidad: se suelta solo pasado ese rato")
    freno.add_argument("--motivo", default="", help="Por qué; queda en la bitácora")
    freno.add_argument("--json", action="store_true", help="Emite JSON")

    args = parser.parse_args()

    if args.command == "chat":
        cmd_chat()
    elif args.command == "web":
        cmd_web(args.port)
    elif args.command == "list-skills":
        cmd_list_skills()
    elif args.command == "skill":
        extra = {
            "title": args.title,
            "concept": args.concept,
            "text": args.text,
            "scale": args.scale,
            "bpm": args.bpm,
            "lyrics_id": args.lyrics_id,
            "mood": args.mood,
            "guest": args.guest,
            "intention": args.intention,
            "duration": args.duration,
            "image_path": args.image_path
        }
        cmd_skill(args.name, extra)
    elif args.command == "cron-task":
        cmd_cron_task(args.name)
    elif args.command == "memory-benchmark":
        cmd_benchmark()
    elif args.command == "vertex-check":
        cmd_vertex_check()
    elif args.command == "run-daemon":
        cmd_daemon()
    elif args.command == "virtualize":
        cmd_virtualize(output_path=args.output, as_json=args.json)
    elif args.command == "spend":
        cmd_spend(as_json=args.json)
    elif args.command == "backup":
        cmd_backup(as_json=args.json, ensayar=args.ensayar)
    elif args.command == "albedrio":
        cmd_agency(as_json=args.json)
    elif args.command == "transparency":
        cmd_transparency(marcar=args.marcar, as_json=args.json)
    elif args.command == "persona":
        cmd_persona(as_json=args.json)
    elif args.command == "sueno":
        cmd_sleep(fase=args.fase, seco=args.seco, as_json=args.json, deshacer=args.deshacer)
    elif args.command == "freno":
        cmd_brake(nivel=args.nivel, soltar=args.soltar, minutos=args.minutos,
                  motivo=args.motivo, as_json=args.json)
    elif args.command == "bitacora":
        cmd_blackbox(verificar=args.verificar, precinto=args.precinto,
                     limite=args.limite, as_json=args.json)
    elif args.command == "pulso":
        return cmd_pulse(as_json=args.json)
    elif args.command == "estado":
        cmd_state(exportar=args.exportar, olvidar=args.olvidar,
                  motivo=args.motivo, as_json=args.json)
    else:
        parser.print_help()


if __name__ == "__main__":
    # El código de salida se propaga: `cli.py pulso` sirve para colgarlo de un
    # temporizador, y un diagnóstico grave que devuelve 0 no despierta a nadie.
    raise SystemExit(main() or 0)
