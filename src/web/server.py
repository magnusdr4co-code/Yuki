"""
Servidor Web Ligero y API del Canvas para Yuki.
Permite visualizar el Salón, interactuar con el agente y consultar la memoria en tiempo real.
Diseñado para funcionar sin dependencias externas obligatorias (basado en http.server).

Preparado para entornos gestionados (Cloud Run, Fly, Render): escucha en el
puerto indicado por la variable de entorno PORT, expone /health para las sondas
de arranque y atiende peticiones concurrentes.
"""

import os
import sys
import json
import time
import signal
import asyncio
import logging
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Asegurar path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.core.agent import YukiAgent

logger = logging.getLogger("Yuki.WebServer")

DEFAULT_PORT = 8080


class SalonHTTPHandler(BaseHTTPRequestHandler):
    agent_instance = None

    # El agente es caro de construir y tiene estado mutable compartido:
    # un candado evita que dos peticiones simultáneas lo dupliquen o lo corrompan.
    _agent_build_lock = threading.Lock()
    _agent_use_lock = threading.Lock()

    @classmethod
    def get_agent(cls):
        if cls.agent_instance is None:
            with cls._agent_build_lock:
                if cls.agent_instance is None:
                    cls.agent_instance = YukiAgent()
        return cls.agent_instance

    def _send_json(self, data: dict, status_code: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html_content: str, status_code: int = 200):
        body = html_content.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # 0. Sonda de vida: barata y sin construir el agente, para que la
        #    plataforma pueda comprobar el arranque antes de cargar la memoria.
        if path in ["/health", "/healthz", "/_ah/health"]:
            self._send_json({
                "status": "ok",
                "service": "yuki-salon",
                "agent_loaded": SalonHTTPHandler.agent_instance is not None
            })
            return

        # 1. Página principal del Salón
        if path in ["/", "/index.html", "/salon"]:
            template_path = os.path.join(os.path.dirname(__file__), "templates", "salon.html")
            if os.path.exists(template_path):
                with open(template_path, "r", encoding="utf-8") as f:
                    self._send_html(f.read())
            else:
                self._send_html("<h1>Salón de Yuki no encontrado</h1>", status_code=404)

        # 2. API: Lista de Recuerdos en SQLite FTS5
        elif path == "/api/memories":
            agent = self.get_agent()
            query_params = parse_qs(parsed.query)
            q = query_params.get("q", ["Yuki"])[0]
            try:
                limit = int(query_params.get("limit", [10])[0])
            except (TypeError, ValueError):
                self._send_json({"error": "El parámetro 'limit' debe ser un entero."}, status_code=400)
                return
            limit = max(1, min(limit, 100))
            results = agent.memory_manager.engine.search(query=q, limit=limit)
            self._send_json({"query": q, "count": len(results), "memories": results})

        # 3. API: Perfil Dialéctico Honcho
        elif path == "/api/honcho":
            agent = self.get_agent()
            self._send_json(agent.honcho._local_profile)

        # 4. API: Lista de Skills Disponibles
        elif path == "/api/skills":
            skills_dir = "skills"
            skills_list = []
            if os.path.exists(skills_dir):
                for item in sorted(os.listdir(skills_dir)):
                    skill_file = os.path.join(skills_dir, item, "SKILL.md")
                    if os.path.exists(skill_file):
                        skills_list.append({"name": item, "file": skill_file})
            self._send_json({"skills": skills_list})

        # 5. API: Archivos en Workspace Nativo ./output/
        elif path == "/api/outputs":
            outputs = {"music": [], "art": [], "voice": [], "posts": []}
            for cat in outputs.keys():
                dir_path = os.path.join("output", cat)
                if os.path.exists(dir_path):
                    for fname in os.listdir(dir_path):
                        if not fname.startswith("."):
                            outputs[cat].append(fname)
            self._send_json(outputs)

        else:
            self.send_error(404, "Ruta no encontrada")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/chat":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
            except (TypeError, ValueError):
                content_length = 0
            body_raw = self.rfile.read(content_length).decode("utf-8")
            try:
                data = json.loads(body_raw)
            except Exception:
                data = {}

            message = data.get("message", "")
            user_id = data.get("user_id", "producer_manager")
            user_name = data.get("user_name", "Productor")

            if not message:
                self._send_json({"error": "El campo 'message' es obligatorio."}, status_code=400)
                return

            agent = self.get_agent()
            start_t = time.perf_counter()

            # El agente muta estado vital y memoria: se atiende un turno cada vez.
            try:
                with SalonHTTPHandler._agent_use_lock:
                    reply = asyncio.run(
                        agent.generate_response(
                            user_id=user_id,
                            user_name=user_name,
                            message=message
                        )
                    )
            except Exception as e:
                logger.error(f"Error generando respuesta: {e}", exc_info=True)
                self._send_json({"error": "No se pudo generar la respuesta."}, status_code=500)
                return

            latency = round((time.perf_counter() - start_t) * 1000.0, 2)
            self._send_json({
                "reply": reply,
                "latency_ms": latency,
                "user_id": user_id
            })

        else:
            self.send_error(404, "Endpoint no encontrado")

    def log_message(self, format, *args):
        # Logging silencioso para no ensuciar consola
        pass


def resolve_port(port: int = None) -> int:
    """
    Puerto de escucha. La variable PORT del entorno manda: es el contrato de
    Cloud Run y de la mayoría de plataformas gestionadas.
    """
    env_port = os.getenv("PORT")
    if env_port:
        try:
            return int(env_port)
        except ValueError:
            logger.warning(f"PORT='{env_port}' no es un entero; se usará {port or DEFAULT_PORT}.")
    return port or DEFAULT_PORT


def run_web_server(port: int = None, host: str = "0.0.0.0"):
    port = resolve_port(port)
    httpd = ThreadingHTTPServer((host, port), SalonHTTPHandler)
    httpd.daemon_threads = True

    print(f"\n🌸 Salón de Yuki Web Dashboard activo en: http://{host}:{port}")
    print(f"   Sonda de vida: http://{host}:{port}/health")
    print("   Presiona Ctrl+C para detener el servidor.\n")

    # Cloud Run envía SIGTERM al retirar una instancia: cerrar sin traza de error.
    def _shutdown(signum, frame):
        print("\nSeñal de parada recibida. Cerrando el Salón...")
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _shutdown)
        except ValueError:
            # Fuera del hilo principal (por ejemplo en tests) no se pueden instalar señales.
            pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nDeteniendo servidor web...")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    cli_port = int(sys.argv[1]) if len(sys.argv) > 1 else None
    run_web_server(port=cli_port)
