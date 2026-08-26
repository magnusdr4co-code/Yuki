"""
Servidor Web Ligero y API del Canvas para Yuki.
Permite visualizar el Salón, interactuar con el agente y consultar la memoria en tiempo real.
Diseñado para funcionar sin dependencias externas obligatorias (basado en http.server).
"""

import os
import sys
import json
import time
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Asegurar path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.core.agent import YukiAgent

class SalonHTTPHandler(BaseHTTPRequestHandler):
    agent_instance = None

    @classmethod
    def get_agent(cls):
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
            limit = int(query_params.get("limit", [10])[0])
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
                        with open(skill_file, "r", encoding="utf-8") as f:
                            content = f.read()
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
            content_length = int(self.headers.get("Content-Length", 0))
            body_raw = self.rfile.read(content_length).decode("utf-8")
            try:
                data = json.loads(body_raw)
            except Exception:
                data = {}

            message = data.get("message", "")
            user_id = data.get("user_id", "producer_manager")
            user_name = data.get("user_name", "Productor")

            agent = self.get_agent()
            start_t = time.perf_counter()
            
            # Ejecución asíncrona dentro del handler síncrono
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                reply = loop.run_until_complete(
                    agent.generate_response(
                        user_id=user_id,
                        user_name=user_name,
                        message=message
                    )
                )
            finally:
                loop.close()

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

def run_web_server(port: int = 8080):
    server_address = ("", port)
    httpd = HTTPServer(server_address, SalonHTTPHandler)
    print(f"\n🌸 Salón de Yuki Web Dashboard activo en: http://localhost:{port}")
    print("   Presiona Ctrl+C para detener el servidor.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nDeteniendo servidor web...")
        httpd.server_close()

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    run_web_server(port=port)
