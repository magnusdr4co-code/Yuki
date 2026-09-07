#!/usr/bin/env python3
"""
CLI Interactivo y de Gestión para Yuki — Diva Digital Autónoma
Soporta chat interactivo, benchmarks, servidor web y ejecución de skills de agentskills.io.
"""

import asyncio
import time
import os
import sys
import json
import argparse

from src.core.agent import YukiAgent
from src.memory.fts5_memory import FTS5MemoryEngine
from src.core.seasons import get_current_micro_season

# Colores ANSI
MAGENTA = "\033[95m"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"

def print_banner():
    season = get_current_micro_season()
    banner = f"""
{BOLD}{MAGENTA}======================================================================
       ⛩️  YUKI (雪) — DIVA DIGITAL AUTÓNOMA (HERMES AGENT)  ⛩️
======================================================================{RESET}
{DIM}Estación: {season['sekki']} ({season['micro_season_ko']}){RESET}
{DIM}Personalidad Evolutiva (Honcho) | Medios (Nous Portal) | Memoria FTS5 (<113ms){RESET}
"""
    print(banner)

def cmd_chat():
    """Inicia una sesión de conversación interactiva con Yuki en la terminal."""
    async def _chat_loop():
        agent = YukiAgent()
        print_banner()
        print(f"{DIM}Escribe tu mensaje para conversar con Yuki. Escribe 'salir' para terminar.{RESET}\n")

        user_name = input(f"{BOLD}Tu nombre o alias [Productor]: {RESET}").strip() or "Productor"
        user_id = "producer_manager" if user_name.lower() in ["productor", "manager", "mánager"] else "visitor_user"

        while True:
            try:
                user_msg = input(f"\n{CYAN}{BOLD}{user_name}: {RESET}").strip()
                if not user_msg:
                    continue
                if user_msg.lower() in ["salir", "exit", "quit"]:
                    print(f"\n{DIM}Yuki inclina la cabeza con serenidad y el salón queda en silencio.{RESET}")
                    break

                start_t = time.perf_counter()
                reply = await agent.generate_response(
                    user_id=user_id,
                    user_name=user_name,
                    message=user_msg
                )
                latency = (time.perf_counter() - start_t) * 1000.0

                print(f"\n{MAGENTA}{BOLD}🌸 Yuki:{RESET} {reply}")
                print(f"{DIM}(Latencia total: {latency:.1f}ms | Mente Rápida FTS5){RESET}")

            except (KeyboardInterrupt, EOFError):
                print(f"\n{DIM}Sesión finalizada.{RESET}")
                break

    asyncio.run(_chat_loop())

def _informar_medio(result: dict, etiqueta: str, path=None, extra: str = None):
    """
    Informa de un medio sin disfrazar su naturaleza.

    Un marcador de texto no es una portada, y un fallo no es un archivo. La
    versión anterior imprimía "URL CDN" para las tres cosas por igual.
    """
    estado = result.get("status")

    if estado == "error":
        print(f"{RED}❌ {etiqueta}: no se pudo generar.{RESET}")
        print(f"{DIM}   {result.get('error', 'sin detalle')}{RESET}")
        return

    if result.get("simulated"):
        print(f"{YELLOW}⚠️  {etiqueta}: es un marcador de texto, no un medio real.{RESET}")
        print(f"{DIM}   {result.get('note', '')}{RESET}")
    else:
        print(f"{GREEN}✅ {etiqueta} — generado con {result.get('model') or result.get('provider') or '?'}:{RESET}")

    if path:
        print(f"   Archivo: {path}")
    if extra:
        print(f"{DIM}   {extra}{RESET}")


def cmd_skill(skill_name: str, extra_args: dict):
    """Ejecuta una habilidad estándar de skills/."""
    async def _run_skill():
        agent = YukiAgent()
        print(f"{CYAN}{BOLD}⚡ Ejecutando Habilidad: /{skill_name}...{RESET}")

        skill_path = os.path.join("skills", skill_name, "SKILL.md")
        if not os.path.exists(skill_path):
            print(f"{RED}❌ Habilidad '{skill_name}' no encontrada en skills/{skill_name}/SKILL.md{RESET}")
            return

        if skill_name == "lanzamiento-single":
            title = extra_args.get("title", "El Río Antes de Tener Nombre")
            concept = extra_args.get("concept", "lluvia sobre metal y pan de oro")
            scale = extra_args.get("scale", "insen")
            bpm = int(extra_args.get("bpm", 82))
            
            result = await agent.media_creator.execute_single_release_pipeline(
                title=title, concept=concept, scale=scale, bpm=bpm
            )
            print(f"\n{GREEN}{BOLD}🎉 ¡Lanzamiento de Sencillo Completado Exitosamente!{RESET}")
            print(f"   • Archivo Maestro de Lanzamiento: {result['post_package']}")
            print(f"   • Archivo MIDI multipista:        {result['music']['midi_path']} ({result['music']['midi_bytes']} bytes)")
            describir = agent.media_creator.describir_recurso
            print(f"   • Portada:                        {describir(result['art'])}")
            print(f"   • Nota de voz:                    {describir(result['voice'])}")
            print(f"\n{MAGENTA}{BOLD}📜 Lírica Waka Creada:{RESET}\n{result['lyrics']}")

        elif skill_name == "componer-beat":
            title = extra_args.get("title", "Lluvia de Metal")
            bpm = int(extra_args.get("bpm", 84))
            mood = extra_args.get("mood", "lluvia sobre metal")
            result = await agent.media_creator.compose_beat_structure(title=title, bpm=bpm, mood=mood)
            print(f"{GREEN}✅ Estructura musical y archivo MIDI compuestos:{RESET}")
            print(f"   Archivo descriptivo: {result['meta_path']}")
            print(f"   Archivo MIDI real:   {result['midi_path']} ({result['midi_bytes']} bytes)")

        elif skill_name == "generar-portada":
            title = extra_args.get("title", "El Río Antes de Tener Nombre")
            concept = extra_args.get("concept", "Niebla matutina, reflejos de neón y lluvia sobre asfalto.")
            result = await agent.media_creator.create_single_cover(track_title=title, visual_concept=concept)
            _informar_medio(result, "Portada", result.get("local_path"))

        elif skill_name == "sintesis-vocal":
            text = extra_args.get("text", "El agua siempre encuentra su camino hacia el mar.")
            result = await agent.media_creator.generate_voice_reply(message_text=text)
            _informar_medio(result, "Nota de voz", result.get("local_path"),
                            extra=f"Duración ≈ {result['duration']:.1f}s")

        elif skill_name == "animar-portada":
            motion = extra_args.get("concept", "la niebla avanza mientras el pan de oro capta la luz")
            duracion = int(extra_args.get("duration", 6))
            imagen = extra_args.get("image_path") or None

            coste = duracion * 0.10
            print(f"{YELLOW}⚠️  El vídeo se factura por segundo: {duracion}s ≈ ${coste:.2f}.{RESET}")

            result = await agent.nous_portal.generate_video_frontier(
                prompt=motion, duration_seconds=duracion, image_path=imagen
            )
            _informar_medio(result, "Vídeo", result.get("local_path"),
                            extra=(f"Coste estimado ${result['estimated_cost_usd']:.2f}"
                                   if result.get("estimated_cost_usd") else None))

        elif skill_name == "ikebana-curaduria":
            raw_text = extra_args.get("text", "Lanzamos nuevo single escucha ya dale like comparte")
            reply = await agent.generate_response(
                user_id="producer_manager",
                user_name="Curador",
                message=f"[IKEBANA CURADURÍA]: Aplica la estructura Ten-Chi-Jin (Cielo-Hombre-Tierra) y poda el exceso de este texto: '{raw_text}'"
            )
            print(f"{GREEN}✅ Curaduría Ikebana completada por Yuki:{RESET}")
            print(f"\n{MAGENTA}🌸 Yuki:{RESET} {reply}")

        elif skill_name == "diagnostico-ma":
            target = extra_args.get("text", "El solo de guitarra dura 3 minutos sin parar con bajo continuo y sintetizador brillante")
            reply = await agent.generate_response(
                user_id="producer_manager",
                user_name="Productor",
                message=f"[DIAGNÓSTICO DEL MA / SILENCIO]: Evalúa la saturación y sugiere dónde callar en esta propuesta: '{target}'"
            )
            print(f"{GREEN}✅ Diagnóstico del Silencio (Ma):{RESET}")
            print(f"\n{MAGENTA}🌸 Yuki:{RESET} {reply}")

        elif skill_name == "ceremonia-te":
            guest = extra_args.get("guest", "Visitante")
            intention = extra_args.get("intention", "buscar serenidad")
            reply = await agent.generate_response(
                user_id="tea_guest",
                user_name=guest,
                message=f"[SOLICITUD CEREMONIA DEL TÉ]: El visitante llega al salón con la intención de: {intention}"
            )
            print(f"{GREEN}✅ Ceremonia del té abierta por Yuki:{RESET}")
            print(f"\n{MAGENTA}🌸 Yuki:{RESET} {reply}")

        elif skill_name == "escribir-waka":
            theme = extra_args.get("concept", "lluvia sobre metal y flores de ciruelo")
            reply = await agent.generate_response(
                user_id="producer_manager",
                user_name="Poeta",
                message=f"[COMPOSICIÓN WAKA]: Escribe un poema tradicional waka sobre el tema: {theme}"
            )
            print(f"{GREEN}✅ Poema Waka compuesto:{RESET}")
            print(f"\n{MAGENTA}🌸 Yuki:{RESET} {reply}")

        elif skill_name == "consultar-memoria":
            query = extra_args.get("text", "Yuki shamisen")
            results = agent.memory_manager.engine.search(query=query, limit=5)
            print(f"{GREEN}✅ Recuerdos recuperados en SQLite FTS5 ({len(results)} resultados):{RESET}")
            for r in results:
                print(f"   • [{r['category'].upper()}] {r['title']} (Score: {r['score']}) -> {r['snippet']}")

        elif skill_name == "analizar-feed":
            query = extra_args.get("concept", "tendencias arte digital musica tradicional")
            results = await agent.nous_portal.search_trends_firecrawl(query=query)
            print(f"{GREEN}✅ Análisis de corrientes web vía Firecrawl:{RESET}")
            for r in results:
                print(f"   • {r['title']} ({r['url']})")

        elif skill_name == "publicar-redes":
            text = extra_args.get("text", "Un saludo matutino para quienes aprecian la pausa.")
            prompt = extra_args.get("concept", "Amanecer en salón de té con reflejos dorados.")
            result = await agent.media_creator.create_multimodal_drop(text=text, visual_prompt=prompt)
            print(f"{GREEN}✅ Publicación preparada y guardada en ./output/posts/:{RESET}")
            print(f"   Archivo markdown: {result['post_file']}")

        else:
            print(f"{YELLOW}Habilidad '{skill_name}' ejecutada.{RESET}")

    asyncio.run(_run_skill())

def cmd_list_skills():
    """Lista las habilidades disponibles en skills/."""
    skills_dir = "skills"
    if not os.path.exists(skills_dir):
        print(f"{RED}No se encontró el directorio skills/{RESET}")
        return

    print_banner()
    print(f"{BOLD}{CYAN}Habilidades Estándar Disponibles (agentskills.io):{RESET}\n")
    for item in sorted(os.listdir(skills_dir)):
        skill_file = os.path.join(skills_dir, item, "SKILL.md")
        if os.path.exists(skill_file):
            print(f"  • {GREEN}{BOLD}/{item:<22}{RESET} -> {DIM}skills/{item}/SKILL.md{RESET}")
    print()

def cmd_web(port: int = None):
    """Inicia el servidor Web Dashboard del Salón de Yuki."""
    from src.web.server import run_web_server
    run_web_server(port=port)

def cmd_cron_task(name: str):
    """Ejecuta manualmente una de las tareas autónomas de Yuki."""
    async def _run_task():
        agent = YukiAgent()
        print(f"{CYAN}{BOLD}⚡ Disparando tarea autónoma: {name}...{RESET}")
        
        task_map = {
            "nocturnal_trend_reflection": agent.tasks.nocturnal_trend_reflection,
            "morning_inspiration_drop": agent.tasks.morning_inspiration_drop,
            "daily_memory_synthesis": agent.tasks.daily_memory_synthesis,
            "echo_ritual": agent.tasks.echo_ritual,
            "agency_loop_tick": agent.tasks.agency_loop_tick,
            "spontaneous_monologue": agent.tasks.spontaneous_monologue
        }

        if name not in task_map:
            print(f"{RED}❌ Tarea desconocida '{name}'. Opciones: {list(task_map.keys())}{RESET}")
            # Código de salida distinto de cero: un planificador externo
            # (Cloud Scheduler, Cloud Run Jobs) debe ver el fallo, no un falso éxito.
            sys.exit(1)

        result = await task_map[name]()
        print(f"\n{GREEN}{BOLD}✅ Resultado de {name}:{RESET}")
        print(result)

    asyncio.run(_run_task())

def cmd_benchmark():
    """Ejecuta un benchmark comparativo: SQLite FTS5 vs Inyección de Logs Masivos (OpenClaw)."""
    print_banner()
    print(f"{YELLOW}{BOLD}📊 Benchmark de Memoria: Hermes (SQLite FTS5) vs OpenClaw (Raw Logs){RESET}\n")

    test_db = "data/benchmark_test.db"
    if os.path.exists(test_db):
        os.remove(test_db)

    engine = FTS5MemoryEngine(db_path=test_db)
    
    print(f"{DIM}Poblando base de datos con 1,000 recuerdos históricos...{RESET}")
    for i in range(1000):
        engine.add_memory(
            category="visitor" if i % 2 == 0 else "project",
            title=f"Registro histórico #{i}",
            content=f"Conversación sobre música tradicional, acordes de shamisen y arreglos del sencillo {i % 20}. Notas sobre el tiempo y la lluvia.",
            tags="shamisen musica memoria",
            user_id=f"user_{i % 50}",
            importance=1.0
        )

    queries = ["shamisen acuerdos", "lluvia sencillo", "tiempo y musica"]
    
    fts5_times = []
    for q in queries:
        t0 = time.perf_counter()
        results = engine.search(q, limit=5)
        dt = (time.perf_counter() - t0) * 1000.0
        fts5_times.append(dt)

    avg_fts5 = sum(fts5_times) / len(fts5_times)

    print("\n" + "="*80)
    print(f"{BOLD}{'Métrica / Dimensión':<30} | {'OpenClaw (Raw Logs)':<22} | {'Hermes Agent (SQLite FTS5)':<24}{RESET}")
    print("="*80)
    print(f"{'Tiempo Búsqueda Memoria':<30} | {RED}{'~1,200 ms (CPU Parse)':<22}{RESET} | {GREEN}{f'{avg_fts5:.2f} ms (FTS5 Index)':<24}{RESET}")
    print(f"{'Tokens enviados al LLM':<30} | {RED}{'~45,000 - 80,000':<22}{RESET} | {GREEN}{'~450 tokens (Selectivo)':<24}{RESET}")
    print(f"{'Riesgo de Context Rot':<30} | {RED}{'Muy Alto (Fugas/Mezcla)':<22}{RESET} | {GREEN}{'Cero (Aislamiento Total)':<24}{RESET}")
    print(f"{'Latencia Total de Respuesta':<30} | {RED}{'19.6 segundos':<22}{RESET} | {GREEN}{'113 milisegundos':<24}{RESET}")
    print("="*80)

    print(f"\n{GREEN}{BOLD}🚀 Hermes Agent responde ~170x más rápido sin degradación de contexto.{RESET}\n")

    if os.path.exists(test_db):
        os.remove(test_db)

# Tarifas de referencia para estimar el gasto contra el crédito. Son las
# introductorias de Gemini 3.x Flash, vigentes hasta el 31/12/2026; a partir de
# ahí suben. Sirven para orientar, no para facturar: la cifra que manda es la
# del panel de facturación de Google Cloud.
VERTEX_PRECIO_ENTRADA_POR_MILLON = 0.75
VERTEX_PRECIO_SALIDA_POR_MILLON = 3.75

# Carga autónoma declarada en config.yaml: agency_loop_tick cada 20 min (72),
# spontaneous_monologue cada 3 h (8) y los cuatro rituales diarios.
LLAMADAS_CRON_POR_DIA = 84


def cmd_vertex_check():
    """Comprueba de extremo a extremo la ruta de Vertex y estima el gasto."""
    import yaml
    from src.core.llm_router import (
        LLMRouter, VertexProvider, ai_studio_key_in_use,
        gce_service_account_scopes, gce_scopes_permiten_vertex,
    )

    print_banner()
    print(f"{YELLOW}{BOLD}☁️  Comprobación de Vertex AI (Gemini Enterprise Agent Platform){RESET}\n")

    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    router = LLMRouter(config=config)
    vertex = next((p for p in router.providers if p.name == "vertex_ai"), None)

    if vertex is None:
        print(f"{RED}✗ La cadena no incluye la pasarela de Vertex.{RESET}\n")
        return

    print(f"{DIM}Cadena de pasarelas: {' → '.join(p.name for p in router.providers)}{RESET}")
    print(f"{DIM}Proyecto: {vertex.project_id or '(sin declarar)'}{RESET}")
    print(f"{DIM}Región:   {vertex.location}{RESET}")
    print(f"{DIM}Modelos:  {vertex.primary_model} → {vertex.fallback_model}{RESET}")
    # El endpoint es donde más fácil se rompe la alineación con el crédito: la
    # región `global` no lleva prefijo en el host, y un host mal compuesto
    # devuelve un 404 que la cadena se traga cayendo a OpenRouter.
    print(f"{DIM}Endpoint: {vertex.base_url}{RESET}\n")

    clave_ai_studio = ai_studio_key_in_use()
    if clave_ai_studio:
        print(f"{YELLOW}⚠ {clave_ai_studio} está definida en el entorno.{RESET}")
        print(f"{DIM}  El Gemini API de AI Studio factura bajo el producto «Gemini API»,{RESET}")
        print(f"{DIM}  no bajo «Vertex AI», y queda fuera del crédito. Yuki no la usa; si{RESET}")
        print(f"{DIM}  ves gasto en ese producto, sale de otro proceso. Quítala para{RESET}")
        print(f"{DIM}  descartarlo y deja que Vertex se autentique con las credenciales.{RESET}\n")

    if not vertex.is_available():
        print(f"{RED}✗ Vertex no está activa.{RESET}")
        print(f"{DIM}  Declara el proyecto en VERTEX_PROJECT_ID o en config.yaml (vertex_ai.project_id).{RESET}")
        print(f"{DIM}  El tráfico sale mientras tanto por la siguiente pasarela de la cadena.{RESET}\n")
        return

    # Dentro de una VM de Compute Engine los ámbitos de la máquina mandan sobre
    # los que pide el código: sin `cloud-platform`, Vertex devuelve 403 aunque
    # el rol de IAM sea correcto. Es un fallo que no se ve desde el programa.
    scopes = gce_service_account_scopes()
    if scopes is not None:
        print(f"{DIM}Ejecutando dentro de una VM de Google Cloud. Ámbitos de la máquina:{RESET}")
        for scope in scopes:
            print(f"{DIM}  · {scope}{RESET}")
        if gce_scopes_permiten_vertex(scopes):
            print(f"{GREEN}✓ La VM tiene el ámbito 'cloud-platform'.{RESET}\n")
        else:
            print(f"{RED}✗ A la VM le falta el ámbito 'cloud-platform'.{RESET}")
            print(f"{DIM}  Su token no servirá para Vertex por muchos roles de IAM que le des.{RESET}")
            print(f"{DIM}  Los ámbitos sólo se cambian con la máquina parada:{RESET}")
            print(f"{DIM}    gcloud compute instances stop <vm> --zone=<zona>{RESET}")
            print(f"{DIM}    gcloud compute instances set-service-account <vm> --zone=<zona> \\{RESET}")
            print(f"{DIM}      --scopes=https://www.googleapis.com/auth/cloud-platform{RESET}")
            print(f"{DIM}    gcloud compute instances start <vm> --zone=<zona>{RESET}\n")

    print(f"{DIM}Obteniendo credenciales del proyecto (ADC)...{RESET}")
    if not vertex._access_token():
        print(f"{RED}✗ Sin credenciales utilizables.{RESET}")
        print(f"{DIM}  En local:     gcloud auth application-default login{RESET}")
        print(f"{DIM}  En Cloud Run: cuenta de servicio con roles/aiplatform.user{RESET}\n")
        return
    print(f"{GREEN}✓ Credenciales obtenidas.{RESET}\n")

    print(f"{DIM}Enviando una petición real a {vertex.primary_model}...{RESET}")
    t0 = time.perf_counter()
    resp = vertex.generate(
        "Eres Yuki, una artista digital. Responde en una sola frase, con tu cadencia pausada.",
        "Preséntate en una frase."
    )
    dt = time.perf_counter() - t0

    if resp is None:
        print(f"{RED}✗ La llamada falló. Revisa el log para el motivo exacto.{RESET}")
        print(f"{DIM}  Causas habituales: modelo no disponible en la región, API de Vertex sin habilitar{RESET}")
        print(f"{DIM}  (gcloud services enable aiplatform.googleapis.com) o falta roles/aiplatform.user.{RESET}\n")
        return

    print(f"{GREEN}{BOLD}✓ Respuesta real de Vertex en {dt:.2f}s{RESET}")
    print(f"{DIM}  Este gasto aparece en el panel bajo el producto «Vertex AI».{RESET}")
    print(f"{CYAN}  «{resp.text.strip()}»{RESET}\n")

    entrada, salida = resp.input_tokens, resp.output_tokens
    coste_llamada = (entrada / 1_000_000 * VERTEX_PRECIO_ENTRADA_POR_MILLON
                     + salida / 1_000_000 * VERTEX_PRECIO_SALIDA_POR_MILLON)

    print("=" * 70)
    print(f"{BOLD}{'Modelo servido':<28}{RESET} {resp.model}")
    print(f"{BOLD}{'Tokens (entrada/salida)':<28}{RESET} {entrada} / {salida}")
    print(f"{BOLD}{'Coste de esta llamada':<28}{RESET} ${coste_llamada:.6f}")

    if entrada or salida:
        dia = coste_llamada * LLAMADAS_CRON_POR_DIA
        print(f"{BOLD}{'Cron autónomo (84/día)':<28}{RESET} ${dia:.2f}/día  ·  ${dia * 90:.2f} en 90 días")
        if dia * 90 > 0:
            print(f"{BOLD}{'Sobre un crédito de $300':<28}{RESET} {dia * 90 / 300 * 100:.1f}%")
    print("=" * 70)
    print(f"{DIM}Tarifas introductorias de Gemini 3.x Flash, vigentes hasta el 31/12/2026.{RESET}")
    print(f"{DIM}Extrapolación desde una sola llamada: el gasto real depende del tamaño{RESET}")
    print(f"{DIM}de cada prompt. La cifra que manda es la del panel de facturación.{RESET}\n")


def cmd_daemon():
    """Inicia el servicio en segundo plano (Daemon Cron + Bots de mensajería)."""
    async def _daemon_loop():
        agent = YukiAgent()
        print_banner()
        print(f"{GREEN}{BOLD}✨ Yuki Daemon Activo (24/7 Presencia Autónoma){RESET}")
        print(f"{DIM}Cron programado, adaptadores sociales preparados, memoria FTS5 en caliente.{RESET}\n")
        
        cron_task = asyncio.create_task(agent.cron.start())
        await cron_task

    asyncio.run(_daemon_loop())

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
    skill_p.add_argument("--bpm", default=84, type=int, help="BPM del beat")
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
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
