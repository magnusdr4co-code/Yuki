"""
Servidor Web Ligero y API del Canvas para Yuki.
Permite visualizar el Salón, interactuar con el agente y consultar la memoria en tiempo real.
Diseñado para funcionar sin dependencias externas obligatorias (basado en http.server).

Preparado para entornos gestionados (Cloud Run, Fly, Render): escucha en el
puerto indicado por la variable de entorno PORT, expone /health para las sondas
de arranque y atiende peticiones concurrentes.
"""

import hmac
import mimetypes
import os
import sys
import json
import time
import signal
import asyncio
import logging
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse, parse_qs, unquote

# Asegurar path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.core.agent import YukiAgent

logger = logging.getLogger("Yuki.WebServer")

DEFAULT_PORT = 8080

# Rutas que responden sin credencial: la sonda de la plataforma y la página.
# Todo lo demás toca memoria, perfil dialéctico o gasto de modelo.
RUTAS_ABIERTAS = ("/health", "/healthz", "/_ah/health", "/", "/index.html", "/salon")

# Las categorías de obra que el Salón sirve. Es una lista cerrada a propósito:
# `salida()` acepta cualquier nombre y un directorio de datos no es obra.
CATEGORIAS_DE_OBRA = ("music", "art", "voice", "posts", "video")

# `/metrics` NO está abierta: el gasto, la deriva de persona y los ritmos dicen
# bastante de la instancia. Una sonda externa se configura con el token.

# Techo de conversación por cliente. Existe aunque no haya credencial: quien
# alcance el puerto puede gastar crédito y, peor, escribir en la memoria de
# Yuki, que es lo único irremplazable. Es un freno, no una autorización.
LIMITE_PETICIONES = 20
VENTANA_LIMITE_SEGUNDOS = 300


def token_configurado() -> str:
    return (os.getenv("SALON_API_TOKEN") or "").strip()


class SalonHTTPHandler(BaseHTTPRequestHandler):
    agent_instance = None

    # El agente es caro de construir y tiene estado mutable compartido:
    # un candado evita que dos peticiones simultáneas lo dupliquen o lo corrompan.
    _agent_build_lock = threading.Lock()
    _agent_use_lock = threading.Lock()

    # Peticiones recientes por cliente, para el techo de conversación.
    _historial_peticiones: dict = {}
    _historial_lock = threading.Lock()

    @classmethod
    def get_agent(cls):
        if cls.agent_instance is None:
            with cls._agent_build_lock:
                if cls.agent_instance is None:
                    cls.agent_instance = YukiAgent()
        return cls.agent_instance

    # --- Puerta de entrada -------------------------------------------------

    def _autorizado(self, path: str) -> bool:
        """
        Credencial requerida sólo si el operador declara `SALON_API_TOKEN`.

        Sin token declarado se conserva el comportamiento anterior —abierto— para
        no romper un despliegue en marcha, pero se avisa al arrancar. Con token,
        se admite en la cabecera `Authorization: Bearer` o en `?token=`, que es
        lo que puede usar la propia página del Salón.
        """
        esperado = token_configurado()
        if not esperado or path in RUTAS_ABIERTAS:
            return True

        cabecera = (self.headers.get("Authorization") or "").strip()
        if cabecera.lower().startswith("bearer "):
            recibido = cabecera[7:].strip()
        else:
            recibido = parse_qs(urlparse(self.path).query).get("token", [""])[0]

        # Comparación en tiempo constante: un token no se adivina midiendo.
        return hmac.compare_digest(recibido, esperado)

    def _dentro_del_limite(self) -> bool:
        """Techo por cliente en la ventana declarada; el resto recibe 429."""
        cliente = self.client_address[0] if self.client_address else "desconocido"
        ahora = time.monotonic()
        with SalonHTTPHandler._historial_lock:
            recientes = [t for t in SalonHTTPHandler._historial_peticiones.get(cliente, [])
                         if ahora - t < VENTANA_LIMITE_SEGUNDOS]
            if len(recientes) >= LIMITE_PETICIONES:
                SalonHTTPHandler._historial_peticiones[cliente] = recientes
                return False
            recientes.append(ahora)
            SalonHTTPHandler._historial_peticiones[cliente] = recientes
        return True

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

    def _metricas(self) -> str:
        """
        Estado de Yuki en formato de exposición de Prometheus.

        Se construye leyendo ficheros y configuración, sin tocar el agente: una
        sonda de métricas que despertara la memoria FTS5 o el modelo cambiaría
        lo que mide, y además convertiría al scraper en una fuente de gasto.
        """
        import yaml

        from ..core.agency import AgencyLedger, AgencyPolicy
        from ..core.blackbox import BlackBox
        from ..core.brake import NIVELES, Brake
        from ..core.persona_anchor import PersonaAnchor, PersonaPolicy
        from ..core.pulse import GRAVEDAD, Pulse
        from ..core.spark import MOTIVOS
        from ..core.rituals import RitualStore
        from ..core.spend_budget import (
            IMAGENES, MUSICA_PISTAS, MUSICA_SEGUNDOS, TOKENS_ENTRADA, TOKENS_SALIDA,
            VIDEO_SEGUNDOS, VOZ_CARACTERES, SpendLedger,
        )
        from ..core.transparency import audit_directory

        try:
            with open("config.yaml", "r", encoding="utf-8") as fichero:
                config = yaml.safe_load(fichero) or {}
        except OSError:
            config = {}

        # Las familias se acumulan y se vuelcan al final: el formato de
        # exposición exige `# HELP` y `# TYPE` **una vez por familia**, antes de
        # todas sus muestras. Repetirlos por muestra —lo natural al escribir el
        # bucle— hace que un parser estricto rechace la página entera.
        familias: Dict[str, Dict[str, Any]] = {}

        def metrica(nombre: str, ayuda: str, valor: Any, tipo: str = "gauge",
                    etiquetas: str = "") -> None:
            familia = familias.setdefault(nombre, {"ayuda": ayuda, "tipo": tipo, "muestras": []})
            sufijo = "{" + etiquetas + "}" if etiquetas else ""
            familia["muestras"].append(f"yuki_{nombre}{sufijo} {valor}")

        # Gasto: lo que de verdad puede dejar a Yuki sin crédito.
        libro = SpendLedger.from_config(config)
        consumo = libro.today()
        # Se emiten todas las unidades conocidas aunque hoy valgan cero. Una
        # familia que desaparece cuando no hay consumo deja al scraper sin poder
        # distinguir «no ha gastado nada» de «la sonda está rota», que es
        # justamente la diferencia que uno quiere ver a las cuatro de la mañana.
        unidades = (VIDEO_SEGUNDOS, IMAGENES, MUSICA_PISTAS, MUSICA_SEGUNDOS,
                    VOZ_CARACTERES, TOKENS_ENTRADA, TOKENS_SALIDA)
        for unidad in sorted(set(unidades) | set(consumo) | set(libro.limits)):
            metrica("gasto_hoy", "Consumo del día por unidad", consumo.get(unidad, 0),
                    etiquetas=f'unidad="{unidad}"')
        for unidad, limite in sorted(libro.limits.items()):
            metrica("gasto_limite", "Límite diario por unidad", limite,
                    etiquetas=f'unidad="{unidad}"')
        metrica("gasto_usd_estimado", "Coste estimado de hoy en USD (música no cotizada)",
                libro.usd_today())

        # Albedrío: cuánta iniciativa está teniendo, y con cuánta tensión.
        politica = AgencyPolicy.from_config(config)
        diario = AgencyLedger(timezone_name=politica.timezone)
        datos = diario.snapshot()
        metrica("agencia_actos_hoy", "Actos autónomos ejecutados hoy", diario.acciones_hoy())
        metrica("agencia_actos_limite", "Techo diario de actos autónomos",
                politica.max_actions_per_day)
        metrica("agencia_aburrimiento", "Tensión acumulada sin actuar (0-1)",
                round(float(datos.get("boredom", 0.0)), 4))
        metrica("agencia_esperando_eco", "Actos autónomos aún sin respuesta",
                len(datos.get("pendientes", [])))

        # Persona: si su voz se está yendo hacia el registro de asistente.
        vigia = PersonaAnchor(policy=PersonaPolicy.from_config(config))
        informe = vigia.report()
        # -1 significa «aún no hay muestras»: un valor imposible en el rango real
        # (0-1) que el panel puede filtrar, en vez de una serie que aparece y
        # desaparece según haya hablado o no.
        metrica("persona_registro", "Fidelidad reciente a su registro (0-1; -1 sin muestras)",
                informe["media_reciente"] if informe["media_reciente"] is not None else -1)
        metrica("persona_reanclajes", "Veces que hubo que reanclar la persona",
                informe["anclajes"], tipo="counter")

        # Cumplimiento: material sintético sin marcar.
        auditoria = audit_directory()
        metrica("material_marcado", "Ficheros generados con marca de origen sintético",
                len(auditoria["marcados"]))
        metrica("material_sin_marcar", "Ficheros generados sin marca (incumplimiento)",
                len(auditoria["sin_marcar"]))

        # Ritmos y bitácora.
        ritmos = RitualStore()
        metrica("ritmos_propios", "Ritmos propios activos", len(ritmos.aprobados()))
        metrica("ritmos_propuestos", "Propuestas esperando al Productor", len(ritmos.pendientes()))
        # El freno como número: un panel tiene que poder enseñar que Yuki está
        # parada a propósito, o media hora de silencio parece una avería.
        freno = Brake()
        estado_freno = freno.state()
        metrica("freno_nivel",
                "Freno de mano (0 ninguno, 1 publicación, 2 medios, 3 todo)",
                NIVELES.get(estado_freno.nivel, 0))
        for accion in ("publicar", "medios", "iniciativa"):
            metrica("freno_permite", "1 si el freno deja pasar ese tipo de acto",
                    1 if freno.permits(accion) else 0, etiquetas=f'accion="{accion}"')

        # Por qué no actuó, en números. Sin esto, `yuki_agencia_actos_hoy == 0`
        # sólo dice que no hizo nada: no si es fase de silencio, freno, techo
        # diario o que el bucle ni siquiera está corriendo.
        censo = diario.censo()
        for motivo in MOTIVOS:
            metrica("albedrio_ciclos", "Ciclos de evaluación por motivo, últimos días",
                    censo.get(motivo, 0), tipo="counter", etiquetas=f'motivo="{motivo}"')

        # Signos vitales. La métrica que faltaba: `up` y `/health` sólo dicen que
        # el proceso contesta, y el fallo más silencioso de esta instancia es
        # justamente que conteste mientras ella no hace absolutamente nada.
        lectura = Pulse(config).read()
        metrica("pulso_gravedad",
                "0 viva o nueva, 1 letargo o freno, 2 catatónica, 3 ausente",
                lectura.gravedad)
        for nombre_estado in GRAVEDAD:
            metrica("pulso_estado", "1 en el estado diagnosticado ahora mismo",
                    1 if lectura.estado == nombre_estado else 0,
                    etiquetas=f'estado="{nombre_estado}"')
        for signo in lectura.signos:
            # -1 y no cero para «nunca»: un cero aquí se leería como
            # «acaba de ocurrir», que es exactamente lo contrario.
            metrica("signo_edad_segundos",
                    "Tiempo desde la última vez que se vio ese signo (-1 si nunca)",
                    int(signo.edad) if signo.edad is not None else -1,
                    etiquetas=f'signo="{signo.id}",tipo="{signo.tipo}"')

        cadena = BlackBox().verify()
        metrica("bitacora_entradas", "Anotaciones en la bitácora encadenada",
                cadena["entradas"], tipo="counter")
        metrica("bitacora_integra", "1 si la cadena de auditoría no ha sido manipulada",
                1 if cadena["integra"] else 0)

        lineas: List[str] = []
        for nombre, familia in familias.items():
            lineas.append(f"# HELP yuki_{nombre} {familia['ayuda']}")
            lineas.append(f"# TYPE yuki_{nombre} {familia['tipo']}")
            lineas.extend(familia["muestras"])
        return "\n".join(lineas) + "\n"

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if not self._autorizado(path):
            self._send_json({"error": "Credencial requerida para esta ruta."}, status_code=401)
            return

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

        # 1.5. Métricas para la sonda externa. Va detrás de la credencial como
        #      el resto de /api: el consumo, la deriva y los ritmos dicen
        #      bastante de la instancia como para dejarlos abiertos.
        elif path in ("/metrics", "/api/metrics"):
            try:
                cuerpo = self._metricas().encode("utf-8")
            except Exception:
                logger.exception("Fallo componiendo las métricas")
                self._send_json({"error": "no se pudieron componer las métricas"},
                                status_code=500)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

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
            from ..core.rutas import salida

            outputs = {cat: [] for cat in CATEGORIAS_DE_OBRA}
            for cat in outputs.keys():
                dir_path = str(salida(cat))
                if os.path.exists(dir_path):
                    for fname in os.listdir(dir_path):
                        if not fname.startswith("."):
                            outputs[cat].append(fname)
            # Enumerar sin decir cómo traerse el fichero es lo que había, y por
            # eso «envíamelo por el Salón» no llevaba a ninguna parte.
            self._send_json({
                **outputs,
                "descarga": ("/api/outputs/<categoria>/<nombre>" if token_configurado()
                             else None),
                "nota": ("Descarga con credencial." if token_configurado() else
                         "Descarga desactivada: sin SALON_API_TOKEN sólo se enumeran nombres."),
            })

        # 6. Descarga de una obra concreta. `/api/outputs` enumeraba nombres y no
        #    había forma de traerse el fichero, así que «envíamelo por el Salón»
        #    no era posible y nadie lo decía. Exige credencial **siempre**, aun
        #    cuando el resto de `/api` esté abierto: enumerar nombres es una
        #    fuga menor; servir los bytes de la obra a quien alcance el puerto
        #    es otra cosa, y encenderla en silencio sería cambiar la exposición
        #    de una instancia en marcha.
        elif path.startswith("/api/outputs/"):
            self._servir_obra(path[len("/api/outputs/"):])

        else:
            self.send_error(404, "Ruta no encontrada")

    def _servir_obra(self, resto: str) -> None:
        from ..core.rutas import salida

        if not token_configurado():
            self._send_json({"error": "Descarga desactivada: declara SALON_API_TOKEN para servir obra."},
                            status_code=403)
            return
        partes = unquote(resto).split("/")
        if len(partes) != 2:
            self._send_json({"error": "Ruta de obra no válida."}, status_code=404)
            return
        categoria, nombre = partes
        if categoria not in CATEGORIAS_DE_OBRA:
            self._send_json({"error": "Categoría no servida."}, status_code=404)
            return
        raiz = Path(str(salida(categoria))).resolve()
        try:
            destino = (raiz / nombre).resolve()
        except OSError:
            self._send_json({"error": "Ruta de obra no válida."}, status_code=404)
            return
        # `..` en el nombre saldría del directorio de obra. Se comprueba sobre
        # la ruta ya resuelta, que es lo único que no se puede disfrazar.
        if not destino.is_relative_to(raiz) or not destino.is_file():
            self._send_json({"error": "Esa obra no existe."}, status_code=404)
            return
        datos = destino.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(destino.name)[0]
                         or "application/octet-stream")
        self.send_header("Content-Length", str(len(datos)))
        # Artículo 50: quien se lleve el fichero se lleva la declaración de
        # origen con él, sin tener que abrirlo. En ASCII a propósito: las
        # cabeceras HTTP se codifican en latin-1 y una raya larga aquí reventaba
        # la descarga entera con `UnicodeEncodeError`.
        self.send_header("X-Generated-By", "IA (Yuki): contenido sintetico")
        self.send_header("Content-Disposition", f'attachment; filename="{destino.name}"')
        self.end_headers()
        self.wfile.write(datos)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if not self._autorizado(path):
            self._send_json({"error": "Credencial requerida para esta ruta."}, status_code=401)
            return

        if path == "/api/chat":
            if not self._dentro_del_limite():
                self._send_json(
                    {"error": f"Demasiadas peticiones: máximo {LIMITE_PETICIONES} cada "
                              f"{VENTANA_LIMITE_SEGUNDOS // 60} minutos desde un mismo cliente."},
                    status_code=429,
                )
                return
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

    if token_configurado():
        print("   🔒 API protegida por SALON_API_TOKEN (Authorization: Bearer o ?token=).")
    else:
        # Decirlo alto: quien alcance el puerto puede escribir en la memoria de
        # Yuki y gastar crédito. No se cierra por defecto para no romper un
        # despliegue en marcha, pero nadie debería enterarse por sorpresa.
        logger.warning(
            "SALON_API_TOKEN no está definido: las rutas /api quedan abiertas a "
            "cualquiera que alcance el puerto %s. Declara el token o restringe el acceso "
            "en el cortafuegos.", port,
        )

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
