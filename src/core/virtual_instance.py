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
        from ..tools.media_jobs import MediaJobStore

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
        self.limiters.sort(key=lambda l: (_ORDEN_GRAVEDAD.get(l.severity, 9), l.id))

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
        self._cap("presencia.salon", "Presencia", REAL,
                  f"Servidor web multihilo con /health en el puerto {_env('PORT') or '8080'}")
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
        self._lim(
            id="L4", title="Sin motor de música contratado propio",
            severity=GRAVE, status=ABIERTO,
            evidence="`nous_portal.generate_music_flow` sólo produce audio real vía Lyria en Vertex; "
                     "sin ella cae a marcador y las partituras salen de local.midi.",
            impact="La canción cantada depende por completo de una preview de Vertex; si cambia el "
                   "catálogo, Yuki se queda sin música real y sin alternativa.",
            proposals=[
                "Fijar un segundo motor (o render acústico propio sobre MIDI + TTS) como respaldo declarado.",
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
        self._lim(
            id="L7", title="Instancia única sin réplica ni copia del disco",
            severity=GRAVE, status=ABIERTO,
            evidence=f"Un solo `{PRODUCTION_INSTANCE['instancia']}` ({PRODUCTION_INSTANCE['maquina']}, "
                     f"{PRODUCTION_INSTANCE['memoria_mb']} MB) en {PRODUCTION_INSTANCE['zona']}; "
                     "memoria, Biblioteca y trabajos viven en su disco.",
            impact="Una zona caída o un disco perdido se lleva la memoria y el canon de Yuki.",
            proposals=["Programar snapshots del disco de datos y probar la restauración.",
                       "Exportar Biblioteca y `yuki_memory.db` a Cloud Storage tras la síntesis diaria."],
        )
        presupuesto = SpendLedger.from_config(self.config)
        self._lim(
            id="L8", title="Vídeo facturado por segundo sin techo de gasto",
            severity=GRAVE, status=MITIGADO if presupuesto.enabled else ABIERTO,
            evidence=(
                f"Veo cuesta ≈0,10 USD/s y el encargo estándar son cuatro clips de 8 s por orden. "
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
            "limitadores": [asdict(l) for l in self.limiters],
            "resumen": self.summary(),
        }

    def summary(self) -> Dict[str, int]:
        return {
            "capacidades_reales": sum(1 for c in self.capabilities if c.state == REAL),
            "capacidades_simuladas": sum(1 for c in self.capabilities if c.state == SIMULADO),
            "capacidades_inactivas": sum(1 for c in self.capabilities if c.state == INACTIVO),
            "limitadores_abiertos": sum(1 for l in self.limiters if l.status == ABIERTO),
            "limitadores_bloqueantes": sum(1 for l in self.limiters if l.severity == BLOQUEANTE),
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
