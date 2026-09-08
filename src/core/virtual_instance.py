"""
Gemelo virtual de la instancia de producción.

Sirve para dos cosas que hasta ahora había que hacer entrando por IAP a la VM y
leyendo logs: ver de un vistazo **qué capacidad es real y cuál es andamiaje** en
el entorno donde se ejecuta, y tener escrita la lista de limitadores con su
gravedad y su vía de salida.

Es deterministra y no toca la red: mira configuración, entorno y disco. Por eso
puede correr en la propia VM, en la réplica local
(`deploy/virtual/docker-compose.virtual.yml`) o en CI, y las tres respuestas son
comparables. No imprime secretos: de una credencial sólo se dice si está puesta
y si es un marcador de `.env.example`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..tools.backup import BackupManager
from ..tools.media_jobs import MediaJobStore
from ..tools.music_fallback import LocalMusicEngine
from .agency import AgencyLedger, AgencyPolicy
from .rituals import RitualStore
from .transparency import TransparencyPolicy, audit_directory
from .llm_router import is_usable_key, build_routes
from .spend_budget import SpendLedger

# Ficha de la instancia de producción, tomada de `docs/PRODUCTION_STATUS.md` y
# `deploy/gce-startup.sh`. Está aquí para que la réplica local pueda
# contrastarse contra ella sin abrir la consola de Google Cloud.
PRODUCTION_INSTANCE = {
    "proyecto": "yuki-prod",
    "instancia": "yuki-agent",
    "maquina": "e2-small",
    "vcpu": 2,
    "memoria_mb": 2048,
    "zona": "europe-southwest1-a",
    "contenedores": ("yuki-salon", "yuki-daemon"),
    "disco_datos": "/var/lib/yuki/data",
    "registro": "europe-southwest1-docker.pkg.dev/yuki-prod/yuki/yuki-agent",
    "secretos": ("yuki-openrouter-api-key", "yuki-discord-bot-token"),
}

REAL = "real"
SIMULADO = "simulado"
INACTIVO = "inactivo"

BLOQUEANTE = "bloqueante"
GRAVE = "grave"
MODERADO = "moderado"

ABIERTO = "abierto"
MITIGADO = "mitigado"
RESUELTO = "resuelto"

_ORDEN_GRAVEDAD = {BLOQUEANTE: 0, GRAVE: 1, MODERADO: 2}


@dataclass
class Capability:
    """Una capacidad declarada y lo que de verdad hace en este entorno."""

    id: str
    pillar: str
    state: str
    detail: str

    @property
    def icon(self) -> str:
        return {REAL: "✅", SIMULADO: "⚠️", INACTIVO: "⭕"}.get(self.state, "•")


@dataclass
class Limiter:
    """Un limitador real, con su evidencia y su salida propuesta."""

    id: str
    title: str
    severity: str
    status: str
    evidence: str
    impact: str
    proposals: List[str] = field(default_factory=list)


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def _clave_util(name: str) -> bool:
    return is_usable_key(_env(name))


class VirtualInstance:
    """Instantánea de la instancia: capacidades efectivas y limitadores."""

    def __init__(self, config: Optional[Dict[str, Any]] = None,
                 root: Optional[Path] = None):
        self.config = config or {}
        self.root = Path(root) if root else Path.cwd()
        self.data_dir = Path(_env("DATABASE_PATH") or "data/yuki_memory.db").parent
        self.capabilities: List[Capability] = []
        self.limiters: List[Limiter] = []
        self._build()

    # -- Entorno ---------------------------------------------------------

    @property
    def vertex_project(self) -> str:
        return _env("VERTEX_PROJECT_ID") or str(
            (self.config.get("vertex_ai", {}) or {}).get("project_id", "") or ""
        )

    @property
    def is_production_vm(self) -> bool:
        """Si este proceso corre en la instancia real y no en la réplica."""
        return _env("ENVIRONMENT") == "production" and not _env("YUKI_VIRTUAL_INSTANCE")

    def pending_media_jobs(self) -> int:
        directorio = self.data_dir / "media_jobs"
        if not directorio.is_dir():
            return 0
        return len(MediaJobStore(str(directorio)).resumable())

    # -- Construcción ----------------------------------------------------

    def _cap(self, cap_id: str, pillar: str, state: str, detail: str) -> None:
        self.capabilities.append(Capability(cap_id, pillar, state, detail))

    def _lim(self, **kwargs: Any) -> None:
        self.limiters.append(Limiter(**kwargs))

    def _build(self) -> None:
        self._build_texto()
        self._build_medios()
        self._build_presencia()
        self._build_mente()
        self._build_limitadores()
        self.limiters.sort(key=lambda lim: (_ORDEN_GRAVEDAD.get(lim.severity, 9), lim.id))

    def _build_texto(self) -> None:
        vertex = bool(self.vertex_project) and (self.config.get("vertex_ai", {}) or {}).get("enabled", True)
        self._cap(
            "texto.vertex", "Lenguaje", REAL if vertex else INACTIVO,
            f"Vertex AI con proyecto '{self.vertex_project}' (consume crédito)" if vertex
            else "Sin VERTEX_PROJECT_ID: la cadena sale por OpenRouter y el crédito no se toca",
        )
        self._cap(
            "texto.openrouter", "Lenguaje", REAL if _clave_util("OPENROUTER_API_KEY") else INACTIVO,
            "Agregador con clave utilizable" if _clave_util("OPENROUTER_API_KEY")
            else "Sin OPENROUTER_API_KEY utilizable",
        )
        modo_portal = (_env("NOUS_PORTAL_MODE") or "disabled").lower()
        self._cap(
            "texto.nous_portal", "Lenguaje",
            SIMULADO if modo_portal == "mock" else INACTIVO,
            f"Modo '{modo_portal}': el endpoint remoto no existe y `_call_remote` sigue sin implementar",
        )
        self._cap("texto.voz_local", "Lenguaje", SIMULADO,
                  "Último recurso sin red; garantiza que Yuki no quede muda")
        rutas = build_routes(self.config)
        self._cap(
            "texto.tiers", "Lenguaje", REAL if rutas else INACTIVO,
            f"{len(rutas)} rutas por tarea aplicadas ({', '.join(sorted(rutas))})" if rutas
            else "provider_routing deshabilitado: toda petición usa agent.model",
        )
        transparencia = TransparencyPolicy.from_config(self.config)
        auditoria = audit_directory(str(self.root / "output"))
        self._cap(
            "cumplimiento.transparencia", "Seguridad",
            REAL if transparencia.enabled else INACTIVO,
            (f"Artículo 50: declaración cada {transparencia.reminder_days} días y marcado "
             f"de origen sintético; {len(auditoria['marcados'])} fichero(s) marcados, "
             f"{len(auditoria['sin_marcar'])} sin marcar"
             if transparencia.enabled else
             "Transparencia DESACTIVADA: se incumple el Artículo 50, en vigor desde 2026-08-02"),
        )
        self._cap(
            "texto.model_armor", "Seguridad",
            REAL if (self.config.get("model_armor", {}) or {}).get("enabled") and self.vertex_project else INACTIVO,
            "Inspección de prompt, argumentos y respuesta" if self.vertex_project
            else "Sin proyecto: Model Armor no puede inspeccionar",
        )

    def _build_medios(self) -> None:
        medios = ((self.config.get("vertex_ai", {}) or {}).get("media", {}) or {})
        vertex = bool(self.vertex_project)
        for cap_id, modelo_key, etiqueta in (
            ("medios.imagen", "image_model", "Portadas"),
            ("medios.video", "video_model", "Vídeo"),
            ("medios.musica", "music_model", "Música"),
            ("medios.voz", "tts_model", "Voz"),
        ):
            modelo = medios.get(modelo_key, "—")
            self._cap(
                cap_id, "Medios", REAL if vertex else SIMULADO,
                f"{etiqueta} vía {modelo}" if vertex
                else f"{etiqueta}: marcador declarado como simulado (sin VERTEX_PROJECT_ID)",
            )
        libro = SpendLedger.from_config(self.config)
        self._cap(
            "medios.presupuesto", "Medios", REAL if libro.enabled else INACTIVO,
            (f"Límites diarios {libro.limits}, comprobados antes de generar; hoy: {libro.describe()}"
             if libro.enabled else "Sección `budget` deshabilitada: nada acota el gasto de medios"),
        )
        respaldo_musical = LocalMusicEngine()
        faltan = respaldo_musical.missing_requirements()
        self._cap(
            "medios.musica_local", "Medios", REAL if not faltan else INACTIVO,
            ("Respaldo propio: partitura, FluidSynth y ffmpeg dentro de la imagen; "
             "maqueta instrumental o letra recitada, nunca canto"
             if not faltan else f"Respaldo musical local indisponible: falta {', '.join(faltan)}"),
        )
        self._cap("medios.midi", "Medios", REAL,
                  "Partituras locales por `src/tools/midi_generator.py`, sin proveedor")
        pendientes = self.pending_media_jobs()
        self._cap(
            "medios.cola", "Medios", REAL,
            f"Cola durable en {self.data_dir / 'media_jobs'}; "
            f"{pendientes} trabajo(s) reanudable(s) ahora mismo",
        )

    def _build_presencia(self) -> None:
        self._cap(
            "presencia.discord", "Presencia",
            REAL if _clave_util("DISCORD_BOT_TOKEN") else INACTIVO,
            f"Guilds autorizados: {_env('DISCORD_ALLOWED_GUILD_ID') or 'ninguno declarado'}",
        )
        self._cap("presencia.telegram", "Presencia", SIMULADO,
                  "El adaptador registra en log; no usa `python-telegram-bot`")
        salon_protegido = bool(_env("SALON_API_TOKEN"))
        self._cap(
            "presencia.salon", "Presencia", REAL,
            f"Servidor web multihilo con /health en el puerto {_env('PORT') or '8080'}; "
            + ("rutas /api con credencial" if salon_protegido else
               "rutas /api ABIERTAS (sin SALON_API_TOKEN), con techo de 20 peticiones/5 min"),
        )
        trabajos = (self.config.get("scheduler", {}) or {}).get("cron_jobs", []) or []
        activos = [j for j in trabajos if j.get("enabled")]
        self._cap("presencia.cron", "Presencia", REAL,
                  f"{len(activos)} de {len(trabajos)} rutinas activas en "
                  f"{(self.config.get('scheduler', {}) or {}).get('timezone', 'UTC')}")

    def _build_mente(self) -> None:
        db = Path(_env("DATABASE_PATH") or (self.config.get("memory", {}) or {}).get(
            "database_path", "data/yuki_memory.db"))
        self._cap("mente.memoria", "Mente", REAL,
                  f"SQLite FTS5 en {db} ({'presente' if db.is_file() else 'aún sin crear'})")
        self._cap(
            "mente.honcho", "Mente",
            REAL if _clave_util("HONCHO_API_KEY") else SIMULADO,
            "Perfil dialéctico sincronizado" if _clave_util("HONCHO_API_KEY")
            else "Perfil sólo en JSON local; sin sincronización remota",
        )
        self._cap(
            "mente.web", "Mente",
            REAL if _clave_util("FIRECRAWL_API_KEY") else SIMULADO,
            "Firecrawl con clave: búsqueda real, resultados con URL verificable"
            if _clave_util("FIRECRAWL_API_KEY")
            else "Sin clave: pistas de introspección declaradas como simuladas, sin URL inventada",
        )
        respaldo = BackupManager.from_config(self.config)
        copias = respaldo.list_backups()
        self._cap(
            "mente.respaldo", "Mente", REAL if respaldo.bucket else SIMULADO,
            (f"Copia diaria verificada a gs://{respaldo.bucket}; {len(copias)} local(es)"
             if respaldo.bucket else
             f"{len(copias)} copia(s) local(es), sin bucket: no salen del disco de la instancia"),
        )

        politica = AgencyPolicy.from_config(self.config)
        diario = AgencyLedger(timezone_name=politica.timezone)
        ritmos = RitualStore()
        self._cap(
            "mente.albedrio", "Mente", REAL if politica.enabled else INACTIVO,
            (f"Iniciativa propia: espontaneidad {politica.spontaneity:g}, audacia "
             f"{politica.audacity:g}, hasta {politica.max_actions_per_day} actos/día; "
             f"hoy {diario.acciones_hoy()}, aburrimiento {diario.boredom():.2f}"
             if politica.enabled else "Agencia desactivada: Yuki sólo responde, no propone"),
        )
        self._cap(
            "mente.ritmos", "Mente", REAL,
            f"{len(ritmos.aprobados())} ritmo(s) propio(s) activo(s), "
            f"{len(ritmos.pendientes())} propuesta(s) esperando al Productor",
        )

        # El gemelo dice lo que la instancia puede saber de sí misma. Que sepa
        # distinguir «el proceso corre» de «Yuki hace cosas» es una capacidad,
        # no un adorno: sin ella, el fallo más silencioso queda invisible.
        try:
            from .pulse import Pulse

            lectura = Pulse(self.config).read()
            self._cap("mente.pulso", "Mente", REAL,
                      f"Signos vitales: {lectura.estado} — {lectura.motivo}")
        except Exception as exc:
            self._cap("mente.pulso", "Mente", INACTIVO,
                      f"La sonda de signos vitales no responde: {type(exc).__name__}")

        biblioteca = self.root / "output" / "Biblioteca"
        self._cap("mente.biblioteca", "Mente", REAL,
                  f"Canon en {biblioteca} ({'presente' if biblioteca.is_dir() else 'vacía en este entorno'})")

    # -- Limitadores -----------------------------------------------------

    def _build_limitadores(self) -> None:
        pendientes = self.pending_media_jobs()
        self._lim(
            id="L1", title="Producción multimedia interrumpible por reinicio",
            severity=GRAVE, status=MITIGADO,
            evidence=("Los pasos se persisten en data/media_jobs y el adaptador los reanuda al "
                      f"conectar el gateway; {pendientes} trabajo(s) reanudable(s) en este entorno. "
                      "La reanudación sigue dependiendo de que el proceso vuelva a arrancar."),
            impact="Un despliegue a mitad de un encargo ya no pierde la canción ni los clips pagados.",
            proposals=[
                "Sacar la ejecución del daemon a un worker aparte (Cloud Run Job) con reintento gestionado.",
                "Publicar el estado del trabajo en el Salón para que el Productor lo consulte sin DM.",
            ],
        )
        if not self.vertex_project:
            self._lim(
                id="L2", title="Sin proyecto Vertex: medios y crédito inactivos",
                severity=BLOQUEANTE, status=ABIERTO,
                evidence="VERTEX_PROJECT_ID vacío en el entorno y en config.yaml.",
                impact=("Imagen, vídeo, música y voz devuelven marcadores simulados, y el crédito de "
                        "Google Cloud no se consume: el texto sale por OpenRouter."),
                proposals=["Declarar VERTEX_PROJECT_ID y verificar con `python3 cli.py vertex-check`."],
            )
        if _env("GEMINI_API_KEY") or _env("GOOGLE_API_KEY"):
            self._lim(
                id="L3", title="Clave de AI Studio presente en el entorno",
                severity=GRAVE, status=ABIERTO,
                evidence="GEMINI_API_KEY/GOOGLE_API_KEY definida.",
                impact="El Gemini API de AI Studio se factura fuera del crédito de prueba.",
                proposals=["Retirarla del entorno; la ruta de producción se autentica con ADC."],
            )
        respaldo_ok = not LocalMusicEngine().missing_requirements()
        self._lim(
            id="L4", title="El canto depende de una preview; hay respaldo instrumental",
            severity=GRAVE, status=MITIGADO if respaldo_ok else ABIERTO,
            evidence=("`generate_music_flow` intenta Lyria y, si falla, "
                      + ("cae al respaldo local (partitura propia + FluidSynth + ffmpeg), que sí "
                         "produce audio real y se declara no cantado."
                         if respaldo_ok else
                         "no puede caer al respaldo local: faltan binarios en esta imagen "
                         f"({', '.join(LocalMusicEngine().missing_requirements())}).")),
            impact=("Si la preview se retira, Yuki sigue teniendo música propia que entregar, "
                    "declarada como maqueta. El canto con letra sigue dependiendo de Lyria."
                    if respaldo_ok else
                    "Si la preview se retira, Yuki se queda sin música real y sin alternativa."),
            proposals=[
                "Contratar un segundo motor que cante, para no depender de una sola preview.",
                "Archivar en Biblioteca el prompt y los parámetros de cada pista para poder rehacerla.",
            ],
        )
        self._lim(
            id="L5", title="Nous Portal sigue sin endpoint",
            severity=MODERADO, status=ABIERTO,
            evidence="`NousPortalProvider._call_remote` no existe; el modo por defecto es `disabled`.",
            impact="El primer eslabón de la cadena declarada nunca sirve tráfico real.",
            proposals=["Implementar `_call_remote` cuando exista el endpoint, o retirar la pasarela del "
                       "diagrama para que la arquitectura documentada sea la que corre."],
        )
        buscador_real = _clave_util("FIRECRAWL_API_KEY")
        self._lim(
            id="L6", title="Telegram sin conectar; búsqueda web sujeta a clave",
            severity=MODERADO, status=ABIERTO,
            evidence=("El adaptador de Telegram registra en log. La búsqueda ya es un cliente real de "
                      + ("Firecrawl, activo con la clave declarada."
                         if buscador_real else
                         "Firecrawl, pero sin FIRECRAWL_API_KEY devuelve pistas marcadas como "
                         "simuladas, sin URL: la reflexión nocturna sabe que no vienen del mundo.")),
            impact=("Telegram, uno de los canales de presencia declarados, no llega a ningún seguidor real."
                    + ("" if buscador_real else
                       " Sin clave, Yuki piensa desde su memoria en vez de desde el mundo, y lo dice.")),
            proposals=["Conectar `python-telegram-bot` con el webhook ya declarado en config.yaml.",
                       "Declarar FIRECRAWL_API_KEY para que las corrientes nocturnas vengan del mundo."],
        )
        gestor = BackupManager.from_config(self.config)
        fuera = bool(gestor.bucket)
        self._lim(
            id="L7", title="Instancia única sin réplica; copia fuera sujeta a bucket",
            severity=GRAVE, status=MITIGADO if fuera else ABIERTO,
            evidence=(f"Un solo `{PRODUCTION_INSTANCE['instancia']}` ({PRODUCTION_INSTANCE['maquina']}, "
                      f"{PRODUCTION_INSTANCE['memoria_mb']} MB) en {PRODUCTION_INSTANCE['zona']}. "
                      + (f"La copia diaria, verificada con integrity_check, sube a gs://{gestor.bucket}."
                         if fuera else
                         "La copia diaria existe y se verifica, pero sin BACKUP_GCS_BUCKET queda en el "
                         "mismo disco que el original.")),
            impact=("Perder el disco ya no se lleva la memoria ni el canon: la copia del día vive fuera."
                    if fuera else
                    "Una zona caída o un disco perdido se lleva la memoria y el canon de Yuki, que es "
                    "lo único irremplazable: los medios se regeneran."),
            proposals=(["Probar una restauración completa al menos una vez: una copia sin restaurar "
                        "no está comprobada.",
                        "Añadir snapshots del disco como segunda línea."]
                       if fuera else
                       ["Declarar BACKUP_GCS_BUCKET para que la copia diaria salga de la instancia.",
                        "Programar snapshots del disco de datos y probar la restauración."]),
        )
        presupuesto = SpendLedger.from_config(self.config)
        self._lim(
            id="L8", title="Vídeo facturado por segundo sin techo de gasto",
            severity=GRAVE, status=MITIGADO if presupuesto.enabled else ABIERTO,
            evidence=(
                "Veo cuesta ≈0,10 USD/s y el encargo estándar son cuatro clips de 8 s por orden. "
                + (f"El presupuesto diario ({presupuesto.limits}) se comprueba antes de llamar al "
                   f"proveedor; hoy: {presupuesto.describe()}"
                   if presupuesto.enabled else
                   "La sección `budget` está deshabilitada: nada acota el gasto.")
            ),
            impact=("Un encargo que exceda el límite se rechaza con la cifra concreta en vez de "
                    "gastar y avisar después. La música se cuenta por unidades: no hay precio de "
                    "referencia registrado que aplicarle."
                    if presupuesto.enabled else
                    "Unas pocas órdenes seguidas consumen el crédito que sostiene todo lo demás."),
            proposals=["Alerta de facturación en el proyecto, que es lo único que ve el gasto real.",
                       "Registrar el precio de Lyria cuando esté publicado para cotizar la música.",
                       "Exponer el consumo del día en el Salón junto al estado de los trabajos."],
        )
        if not _env("SALON_API_TOKEN"):
            self._lim(
                id="L10", title="API del Salón sin credencial",
                severity=GRAVE, status=ABIERTO,
                evidence="SALON_API_TOKEN no declarado: /api/chat, /api/memories y /api/honcho "
                         "responden a cualquiera que alcance el puerto. Sólo las frena el techo "
                         "de 20 peticiones cada 5 minutos por cliente.",
                impact="Quien llegue al puerto puede gastar crédito y escribir en la memoria de "
                       "Yuki, que es lo único irremplazable; el perfil dialéctico del Productor "
                       "queda además a la vista.",
                proposals=["Declarar SALON_API_TOKEN en el entorno de la instancia.",
                           "Restringir el puerto 8080 en el cortafuegos a IAP o a la red autorizada."],
            )

        transparencia_cfg = TransparencyPolicy.from_config(self.config)
        pendientes_marca = audit_directory(str(self.root / "output"))["sin_marcar"]
        if not transparencia_cfg.enabled or pendientes_marca:
            self._lim(
                id="L11", title="Material sintético sin marcar o transparencia desactivada",
                severity=BLOQUEANTE if not transparencia_cfg.enabled else GRAVE,
                status=ABIERTO,
                evidence=("La sección `transparency` está desactivada."
                          if not transparencia_cfg.enabled else
                          f"{len(pendientes_marca)} fichero(s) generados siguen sin marca de origen "
                          "sintético en `output/`."),
                impact=("El Artículo 50 del Reglamento europeo de IA es aplicable desde el "
                        "2 de agosto de 2026 y exige declarar la naturaleza del sistema ante las "
                        "personas y marcar las salidas de forma legible por máquina. Las sanciones "
                        "llegan a 15 M€ o el 3% del volumen de negocio."),
                proposals=["Marcar lo pendiente: `python3 cli.py transparency --marcar`.",
                           "Mantener `transparency.enabled: true`; no es un rasgo de carácter."],
            )

        self._lim(
            id="L9", title="Honcho dialéctico sin servicio remoto",
            severity=MODERADO, status=ABIERTO,
            evidence="El perfil vive en JSON local; no hay sincronización.",
            impact="El modelado con el Productor no sobrevive a la pérdida del disco ni se comparte "
                   "entre entornos.",
            proposals=["Sincronizar con el servicio, o declarar el JSON local como la implementación real."],
        )

    # -- Salidas ---------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "instancia_produccion": dict(PRODUCTION_INSTANCE),
            "entorno": {
                "es_vm_produccion": self.is_production_vm,
                "replica_virtual": bool(_env("YUKI_VIRTUAL_INSTANCE")),
                "proyecto_vertex": self.vertex_project or None,
                "directorio_datos": str(self.data_dir),
            },
            "capacidades": [asdict(c) for c in self.capabilities],
            "limitadores": [asdict(lim) for lim in self.limiters],
            "resumen": self.summary(),
        }

    def summary(self) -> Dict[str, int]:
        return {
            "capacidades_reales": sum(1 for c in self.capabilities if c.state == REAL),
            "capacidades_simuladas": sum(1 for c in self.capabilities if c.state == SIMULADO),
            "capacidades_inactivas": sum(1 for c in self.capabilities if c.state == INACTIVO),
            "limitadores_abiertos": sum(1 for lim in self.limiters if lim.status == ABIERTO),
            "limitadores_bloqueantes": sum(1 for lim in self.limiters if lim.severity == BLOQUEANTE),
        }

    def render_markdown(self) -> str:
        resumen = self.summary()
        lineas = [
            "# Gemelo virtual de la instancia de Yuki",
            "",
            f"Entorno: {'VM de producción' if self.is_production_vm else 'réplica o desarrollo'} · "
            f"proyecto Vertex: `{self.vertex_project or 'sin declarar'}` · datos en `{self.data_dir}`",
            "",
            f"Instancia declarada: `{PRODUCTION_INSTANCE['instancia']}` "
            f"({PRODUCTION_INSTANCE['maquina']}, {PRODUCTION_INSTANCE['memoria_mb']} MB, "
            f"{PRODUCTION_INSTANCE['zona']}) con `{'` y `'.join(PRODUCTION_INSTANCE['contenedores'])}`.",
            "",
            "## Capacidades efectivas",
            "",
            "| Pilar | Capacidad | Estado | Detalle |",
            "|---|---|---|---|",
        ]
        for cap in self.capabilities:
            lineas.append(f"| {cap.pillar} | `{cap.id}` | {cap.icon} {cap.state} | {cap.detail} |")
        lineas += [
            "",
            f"Reales: {resumen['capacidades_reales']} · simuladas: {resumen['capacidades_simuladas']} · "
            f"inactivas: {resumen['capacidades_inactivas']}.",
            "",
            "## Limitadores",
            "",
        ]
        for lim in self.limiters:
            lineas += [
                f"### {lim.id} · {lim.title}",
                "",
                f"- **Gravedad:** {lim.severity} · **Estado:** {lim.status}",
                f"- **Evidencia:** {lim.evidence}",
                f"- **Impacto:** {lim.impact}",
                "- **Salidas propuestas:**",
            ]
            lineas += [f"  - {p}" for p in lim.proposals]
            lineas.append("")
        lineas.append(
            f"Abiertos: {resumen['limitadores_abiertos']} · bloqueantes: "
            f"{resumen['limitadores_bloqueantes']}."
        )
        return "\n".join(lineas)
