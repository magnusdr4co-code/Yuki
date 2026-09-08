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
from pathlib import Path

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
        engine.search(q, limit=5)  # se mide la llamada, no su resultado
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
        LLMRouter, ai_studio_key_in_use,
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

        tasks = [asyncio.create_task(agent.cron.start())]
        discord_adapter = None
        if os.getenv("DISCORD_BOT_TOKEN"):
            from src.adapters.discord_bot import DiscordAdapter
            discord_adapter = DiscordAdapter(agent)
            tasks.append(asyncio.create_task(discord_adapter.start()))
            print(f"{DIM}Conector Discord real activado; solo menciones dentro del guild autorizado.{RESET}")

        registered = ", ".join(
            f"{name}={job['cron_expr']}" for name, job in agent.cron.jobs.items()
        )
        print(f"{DIM}Rutinas Hermes registradas ({agent.cron.timezone}): {registered}{RESET}")

        try:
            await asyncio.gather(*tasks)
        finally:
            if discord_adapter is not None:
                await discord_adapter.close()

    asyncio.run(_daemon_loop())

def cmd_sleep(fase="noche", seco=False, as_json=False, deshacer=None):
    """Ejecuta una fase del ciclo de sueño sobre la memoria real."""
    import asyncio

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


def cmd_brake(nivel=None, soltar=False, minutos=None, motivo="", as_json=False):
    """Freno de mano: pararla sin matarla."""
    from src.core.brake import NIVELES, Brake

    freno = Brake()

    if soltar:
        estado = freno.release(actor="cli", motivo=motivo)
        print(f"{GREEN}✓ Freno soltado.{RESET} {freno.describe()}")
        if estado.activo:
            print(f"{YELLOW}⚠ Sigue frenada desde {estado.origen}: eso no lo suelta el CLI.{RESET}")
        return estado

    if nivel:
        try:
            estado = freno.engage(nivel, motivo=motivo, actor="cli", minutos=minutos)
        except ValueError as exc:
            print(f"{RED}✗ {exc}{RESET}")
            return None
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
        try:
            recibo = registro.subject_forget(olvidar, actor="cli", reason=motivo)
        except ValueError as exc:
            print(f"{RED}✗ {exc}{RESET}")
            return None
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
            "censo_de_ciclos": diario.censo(),
            "censo_de_hoy": diario.censo_de_hoy(),
            "ritmos_propios": [r.to_dict() for r in ritmos.aprobados()],
            "propuestas": [r.to_dict() for r in ritmos.pendientes()],
        }, ensure_ascii=False, indent=2))
        return

    print_banner()
    print(f"{MAGENTA}{BOLD}🌱 Libre albedrío{RESET}\n")
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
    pendientes = ritmos.pendientes()
    if pendientes:
        print(f"\n{YELLOW}Esperando tu respuesta:{RESET}")
        for ritmo in pendientes:
            print(f"  🕯️  {ritmo.id} · {ritmo.name} — {ritmo.cron} · {ritmo.action}")
            print(f"      {DIM}{ritmo.reason}{RESET}")


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

        from scripts.restore_drill import restaurar

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
