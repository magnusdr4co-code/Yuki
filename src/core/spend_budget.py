"""
Presupuesto de gasto: se comprueba **antes** de generar, no después.

El limitador L8 de `docs/VIRTUALIZACION_Y_MEJORAS.md`: Veo se factura por
segundo de vídeo, así que el encargo estándar —cuatro clips de 8 s— son ~3,2 USD
y unas pocas órdenes seguidas se comen el crédito que sostiene todo lo demás. No
había ningún sitio donde constara lo gastado hoy: cada llamada estimaba su coste,
lo escribía en un log y nadie lo sumaba.

Aquí se suma. El libro vive en `data/spend_ledger.json` —el disco persistente de
la instancia— con un apunte por día y unidad, y la comprobación ocurre antes de
llamar al proveedor: una orden que excede el presupuesto se rechaza con la cifra
concreta («llevas 96 s de los 120 s de hoy»), que es lo que permite decidir, en
vez de gastar y avisar luego.

Sobre los precios: los de vídeo e imagen están documentados en
`src/tools/vertex_media.py` y los de texto en `cli.py`. Para música no hay precio
de referencia registrado en el repositorio, así que **no se inventa uno**: las
pistas se cuentan por unidades y por segundos, y la estimación en dólares declara
que las excluye. Un límite por unidades protege igual sin fingir precisión.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("Yuki.Presupuesto")

# Unidades contabilizadas. Cada una tiene su propio límite porque su coste y su
# razón de ser son distintos: un segundo de vídeo no se compara con un token.
VIDEO_SEGUNDOS = "video_segundos"
IMAGENES = "imagenes"
MUSICA_PISTAS = "musica_pistas"
MUSICA_SEGUNDOS = "musica_segundos"
VOZ_CARACTERES = "voz_caracteres"
TOKENS_ENTRADA = "tokens_entrada"
TOKENS_SALIDA = "tokens_salida"

# Precios de referencia, orientativos: la cifra que manda es la del panel de
# facturación. Música ausente a propósito (ver docstring).
PRECIO_VIDEO_POR_SEGUNDO = 0.10
PRECIO_IMAGEN = 0.04
PRECIO_TOKENS_ENTRADA_POR_MILLON = 0.75
PRECIO_TOKENS_SALIDA_POR_MILLON = 3.75

# Límites por defecto, deliberadamente conservadores: 120 s de vídeo son ~12 USD
# al día, tres encargos y medio. Se ajustan en `config.yaml`.
LIMITES_POR_DEFECTO: Dict[str, float] = {
    VIDEO_SEGUNDOS: 120,
    IMAGENES: 40,
    MUSICA_PISTAS: 12,
}

# Días de historial que se conservan. El disco de la instancia es pequeño y el
# valor de un apunte de hace un mes es nulo.
DIAS_RETENIDOS = 45


@dataclass
class BudgetDecision:
    """Veredicto de una comprobación previa al gasto."""

    allowed: bool
    reason: str = ""
    unit: str = ""
    used: float = 0.0
    limit: Optional[float] = None

    def __bool__(self) -> bool:
        return self.allowed


def coste_estimado(unit: str, amount: float) -> float:
    """Coste en USD de una unidad, o 0.0 si no hay precio de referencia."""
    if unit == VIDEO_SEGUNDOS:
        return amount * PRECIO_VIDEO_POR_SEGUNDO
    if unit == IMAGENES:
        return amount * PRECIO_IMAGEN
    if unit == TOKENS_ENTRADA:
        return amount / 1_000_000 * PRECIO_TOKENS_ENTRADA_POR_MILLON
    if unit == TOKENS_SALIDA:
        return amount / 1_000_000 * PRECIO_TOKENS_SALIDA_POR_MILLON
    # Música y voz: sin precio registrado. Se cuentan, no se cotizan.
    return 0.0


def _hoy(zona_horaria: str) -> str:
    """
    Fecha del apunte en la zona declarada por el planificador.

    Importa que sea la misma zona que la del cron: si el presupuesto se
    reiniciara a medianoche UTC y las rutinas corrieran en Europe/Madrid, habría
    dos horas cada día en que el día del gasto y el día de las tareas no
    coinciden, y el límite se aplicaría al día equivocado.
    """
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(zona_horaria)).strftime("%Y-%m-%d")
    except Exception:
        # Sin base de datos de zonas horarias: UTC es peor pero es determinista.
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class SpendLedger:
    """
    Libro de gasto diario, persistente y atómico.

    Un proceso escribe y otro lee (el daemon y el Salón comparten disco), así que
    cada actualización relee el fichero antes de sumar: dos apuntes simultáneos
    se suman en vez de pisarse. La sección crítica se cierra con un `flock` sobre
    un fichero aparte, porque un `threading.Lock` no dice nada al otro contenedor.

    La operación que de verdad importa es `reserve`: comprobar y anotar en el
    mismo tramo cerrado. Comprobar primero y anotar después del proveedor deja en
    medio toda la llamada —decenas de segundos en el caso de Veo—, y en ese hueco
    dos encargos simultáneos superan ambos un límite que ya estaba al borde. Si
    el proveedor luego falla, `refund` devuelve lo reservado: es preferible
    devolver que arriesgarse a gastar de más.
    """

    def __init__(self, path: Optional[str] = None, limits: Optional[Dict[str, float]] = None,
                 enabled: bool = True, timezone_name: str = "Europe/Madrid",
                 usd_per_day: Optional[float] = None):
        # `YUKI_SPEND_LEDGER_PATH` permite reubicar el libro sin tocar código —y
        # que las pruebas no escriban en el del repositorio.
        if path:
            destino = Path(path)
        elif os.getenv("YUKI_SPEND_LEDGER_PATH", "").strip():
            destino = Path(os.environ["YUKI_SPEND_LEDGER_PATH"].strip())
        else:
            db_path = os.getenv("DATABASE_PATH", "data/yuki_memory.db")
            destino = Path(db_path).parent / "spend_ledger.json"
        self.path = destino
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.limits = {**LIMITES_POR_DEFECTO, **(limits or {})}
        self.enabled = enabled
        self.timezone_name = timezone_name
        self.usd_per_day = usd_per_day
        self._lock = threading.Lock()

    # -- Configuración ---------------------------------------------------

    @classmethod
    def from_config(cls, config: Optional[Dict[str, Any]] = None, **overrides: Any) -> "SpendLedger":
        """Lee la sección `budget` de `config.yaml`; sin ella, límites por defecto."""
        config = config or {}
        presupuesto = config.get("budget", {}) or {}
        limites = {clave: valor for clave, valor in (presupuesto.get("daily_limits") or {}).items()
                   if isinstance(valor, (int, float))}
        parametros: Dict[str, Any] = {
            "enabled": presupuesto.get("enabled", True),
            "limits": limites,
            "usd_per_day": presupuesto.get("usd_per_day"),
            "timezone_name": (config.get("scheduler", {}) or {}).get("timezone", "Europe/Madrid"),
        }
        parametros.update(overrides)
        return cls(**parametros)

    # -- Estado ----------------------------------------------------------

    @contextlib.contextmanager
    def _exclusivo(self):
        """
        Sección crítica intra e inter proceso.

        `flock` es de POSIX; donde no exista, el candado de hilo sigue siendo
        correcto dentro del proceso y la operación no se bloquea por ello.
        """
        with self._lock:
            try:
                import fcntl
            except ImportError:
                yield
                return

            candado = self.path.with_name(self.path.name + ".lock")
            with open(candado, "w", encoding="utf-8") as descriptor:
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)

    def _leer(self) -> Dict[str, Any]:
        if not self.path.is_file():
            return {"dias": {}}
        try:
            datos = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(datos, dict) and isinstance(datos.get("dias"), dict):
                return datos
        except (json.JSONDecodeError, OSError, TypeError) as exc:
            logger.warning("Libro de gasto ilegible (%s); se empieza uno nuevo.", type(exc).__name__)
        return {"dias": {}}

    def _escribir(self, datos: Dict[str, Any]) -> None:
        temporal = self.path.with_suffix(".json.tmp")
        temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporal, self.path)

    def _podar(self, datos: Dict[str, Any]) -> None:
        limite = (datetime.now(timezone.utc) - timedelta(days=DIAS_RETENIDOS)).strftime("%Y-%m-%d")
        for dia in [d for d in datos["dias"] if d < limite]:
            datos["dias"].pop(dia, None)

    def today(self) -> Dict[str, float]:
        """Consumo acumulado de hoy, por unidad."""
        return dict(self._leer()["dias"].get(_hoy(self.timezone_name), {}))

    def usd_today(self) -> float:
        consumo = self.today()
        # Seis decimales: con precios por millón de tokens, redondear a cuatro
        # convierte una jornada de texto en cero.
        return round(sum(coste_estimado(unidad, cantidad) for unidad, cantidad in consumo.items()), 6)

    # -- Comprobación y registro ----------------------------------------

    def check(self, unit: str, amount: float) -> BudgetDecision:
        """
        Si cabe gastar `amount` de `unit` hoy. Se llama **antes** del proveedor.

        Un presupuesto deshabilitado o una unidad sin límite declarado autorizan:
        el objetivo es acotar lo caro, no impedir que Yuki trabaje.
        """
        if not self.enabled:
            return BudgetDecision(True, "presupuesto deshabilitado", unit)

        consumo = self.today()
        usado = float(consumo.get(unit, 0.0))
        limite = self.limits.get(unit)

        if limite is not None and usado + amount > limite:
            return BudgetDecision(
                False,
                f"presupuesto diario agotado para {unit}: llevas {usado:g} de {limite:g} "
                f"y esta operación pide {amount:g}",
                unit, usado, limite,
            )

        if self.usd_per_day is not None:
            gasto = round(sum(coste_estimado(u, c) for u, c in consumo.items()), 6)
            previsto = gasto + coste_estimado(unit, amount)
            if previsto > self.usd_per_day:
                return BudgetDecision(
                    False,
                    f"presupuesto diario agotado: llevas ${gasto:.2f} de ${self.usd_per_day:.2f} "
                    f"y esta operación suma ${coste_estimado(unit, amount):.2f} "
                    "(la estimación no incluye música, sin precio de referencia registrado)",
                    unit, gasto, self.usd_per_day,
                )

        return BudgetDecision(True, "dentro del presupuesto", unit, usado, limite)

    def _anotar(self, unit: str, amount: float) -> Dict[str, float]:
        """Suma dentro de una sección ya cerrada. No la abre por su cuenta."""
        datos = self._leer()
        dia = _hoy(self.timezone_name)
        consumo = datos["dias"].setdefault(dia, {})
        consumo[unit] = max(0.0, round(float(consumo.get(unit, 0.0)) + float(amount), 4))
        self._podar(datos)
        self._escribir(datos)
        return dict(consumo)

    def record(self, unit: str, amount: float) -> Dict[str, float]:
        """Anota lo gastado. Se llama sólo tras un resultado real y verificado."""
        with self._exclusivo():
            consumo = self._anotar(unit, amount)
        logger.info("Gasto anotado: %s +%g (hoy %g)", unit, amount, consumo.get(unit, 0.0))
        return consumo

    def reserve(self, unit: str, amount: float) -> BudgetDecision:
        """
        Comprueba y anota en la misma sección cerrada, antes de gastar.

        Es la forma correcta de usar el presupuesto: lo que se comprueba queda
        reservado, así que otro encargo simultáneo ve el consumo ya sumado y no
        puede colarse por el hueco de la llamada al proveedor.
        """
        with self._exclusivo():
            decision = self.check(unit, amount)
            if decision.allowed:
                self._anotar(unit, amount)
        if not decision.allowed:
            logger.warning("Reserva denegada: %s", decision.reason)
        return decision

    def refund(self, unit: str, amount: float) -> Dict[str, float]:
        """
        Devuelve una reserva que no llegó a gastarse.

        Un fallo del proveedor no se cobra: si Veo devuelve 503 no hay segundo
        de vídeo facturado que anotar.
        """
        with self._exclusivo():
            consumo = self._anotar(unit, -abs(amount))
        logger.info("Reserva devuelta: %s -%g", unit, amount)
        return consumo

    def record_llm(self, input_tokens: int, output_tokens: int) -> None:
        """Atajo para el consumo de texto, que llega en dos unidades a la vez."""
        if input_tokens:
            self.record(TOKENS_ENTRADA, input_tokens)
        if output_tokens:
            self.record(TOKENS_SALIDA, output_tokens)

    # -- Informe ---------------------------------------------------------

    def describe(self) -> str:
        """Resumen determinista de hoy, para el DM y el CLI."""
        consumo = self.today()
        if not consumo:
            return "Sin gasto registrado hoy."
        partes = []
        for unidad in sorted(consumo):
            limite = self.limits.get(unidad)
            usado = consumo[unidad]
            partes.append(f"{unidad}: {usado:g}" + (f"/{limite:g}" if limite is not None else ""))
        linea = " · ".join(partes)
        return f"{linea} · ≈${self.usd_today():.2f} (música no cotizada)"
