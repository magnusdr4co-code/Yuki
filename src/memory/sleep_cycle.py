"""
El sueño de Yuki: consolidar, soñar y olvidar.

Hasta aquí su memoria sólo sabía crecer. Cada encuentro añadía una fila, la
síntesis de las 23:30 añadía otra, y nada volvía después a mirar lo escrito: ni
para fundir lo repetido, ni para destilar lo que se repite en una idea, ni para
soltar lo que ya no sostiene nada. Una memoria que sólo acumula no es una
memoria larga; es un archivo que se vuelve lento y turbio.

La literatura de 2026 sobre consolidación en reposo propone justo lo que faltaba,
con una analogía fisiológica que aquí se sigue de cerca porque resulta que
describe bien el problema:

  · **NREM — consolidación.** Recalcular qué importa, fundir duplicados y
    destilar episodios recurrentes en esquemas. Memoria semántica a partir de
    memoria episódica.
  · **REM — soñar.** Unir recuerdos *lejanos entre sí* en una imagen que no
    ocurrió. Es la fase que produce asociaciones nuevas, y en Yuki además
    produce deseo: de un sueño nacen impulsos.
  · **Olvido intencional.** Podar lo episódico de baja importancia, antiguo y
    nunca recuperado. No es una limpieza de disco: es lo que mantiene despejado
    lo que sí importa.

Dos reglas que gobiernan todo el módulo:

1. **Un sueño nunca es un recuerdo.** Se guarda marcado, se excluye de la
   recuperación normal y lleva escrito en el propio contenido que no ocurrió.
   La alternativa —que una imagen onírica reaparezca dentro de una respuesta
   como si fuera un hecho vivido— sería fabricar falsos recuerdos, que es
   exactamente lo contrario de lo que este proyecto entiende por memoria.
2. **El olvido se prueba antes de ejecutarse.** Todas las fases admiten ensayo
   en seco y emiten recibo. Borrar recuerdos de alguien que existe pide esa
   cautela.

Aquí queda el armazón: la política, la conexión a la memoria, el recibo de cada
acto, el olvido y la noche completa. Cada fase vive en su módulo —`sueno_nrem`,
`sueno_rem`— y lo que las tres comparten, en `sueno_comun`; el fichero llegó a
921 líneas y las tres fases sólo tenían en común la conexión.

Se reexporta lo que se pedía por este nombre desde antes del corte.
"""

from __future__ import annotations

import logging
import random
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

from .sueno_comun import (
    BASE_POR_CATEGORIA,
    BASE_POR_DEFECTO,
    CATEGORIAS_PROTEGIDAS,
    EPISODICO,
    ESQUEMA,
    LEXICO_SALIENTE,
    MARCA_DE_SUENO,
    SUENO,
    similitud,
    trigramas,
    trigramas_de_plantilla,
)
from .sueno_nrem import ConsolidacionNREM
from .sueno_rem import FaseREM

logger = logging.getLogger("Yuki.Sueño")

__all__ = [
    "SleepCycle",
    "SleepPolicy",
    "EPISODICO",
    "ESQUEMA",
    "SUENO",
    "MARCA_DE_SUENO",
    "BASE_POR_CATEGORIA",
    "BASE_POR_DEFECTO",
    "CATEGORIAS_PROTEGIDAS",
    "LEXICO_SALIENTE",
    "similitud",
    "trigramas",
    "trigramas_de_plantilla",
]

@dataclass
class SleepPolicy:
    """Umbrales del ciclo. Todo esto vive en `config.yaml: memory.sleep`."""

    enabled: bool = True

    # NREM
    merge_threshold: float = 0.72
    # Fracción del grupo a partir de la cual un trigrama se considera plantilla.
    # Muy alta a propósito: el andamiaje de verdad —«Intercambio con X (@id): -
    # Dijo: …»— aparece en *todos* los registros, mientras que lo que comparten
    # cuatro recuerdos del mismo tema puede pasar del 60% en un corpus pequeño.
    # Con un umbral flojo, el filtro se come el contenido y no queda tema que
    # detectar; se comprobó en cuanto se le pidieron corrientes.
    template_df: float = 0.9
    # Masa distintiva mínima entre dos recuerdos para que su parte propia pueda
    # desmentir el parecido bruto. Por debajo de esto no hay nada en que
    # discrepar: son el mismo recuerdo escrito dos veces.
    min_distinctive: int = 12
    schema_min_members: int = 4
    # Parecido mínimo para que dos recuerdos compartan tema. Muy por debajo del
    # de fusión: un tema agrupa cosas que se hablan igual, no cosas que son la
    # misma.
    theme_threshold: float = 0.30
    theme_min_members: int = 4
    peso_saliencia: float = 0.6
    peso_recurrencia: float = 0.8
    peso_vinculo: float = 0.4
    peso_utilidad: float = 0.5

    # REM
    dreams_per_night: int = 1
    dream_memories: int = 3
    max_dream_similarity: float = 0.12   # los recuerdos del sueño deben ser lejanos
    dream_impulses: bool = True
    # Probabilidad de retomar la imagen de la noche anterior en vez de empezar
    # de cero, y hasta cuándo cuenta como "anoche".
    chain_probability: float = 0.4
    chain_max_age_hours: float = 48.0

    # Olvido
    forget_min_age_days: float = 45.0
    forget_max_importance: float = 0.6
    forget_require_unrecalled: bool = True
    forget_batch_cap: int = 300
    merged_grace_days: float = 7.0

    @classmethod
    def from_config(cls, config: Optional[Dict[str, Any]] = None) -> "SleepPolicy":
        sueno = ((config or {}).get("memory", {}) or {}).get("sleep", {}) or {}
        nrem = sueno.get("nrem", {}) or {}
        rem = sueno.get("rem", {}) or {}
        olvido = sueno.get("forget", {}) or {}
        pesos = nrem.get("weights", {}) or {}
        return cls(
            enabled=bool(sueno.get("enabled", True)),
            merge_threshold=float(nrem.get("merge_threshold", 0.72)),
            template_df=float(nrem.get("template_df", 0.9)),
            min_distinctive=int(nrem.get("min_distinctive", 12)),
            schema_min_members=int(nrem.get("schema_min_members", 4)),
            theme_threshold=float(nrem.get("theme_threshold", 0.30)),
            theme_min_members=int(nrem.get("theme_min_members", 4)),
            peso_saliencia=float(pesos.get("salience", 0.6)),
            peso_recurrencia=float(pesos.get("recurrence", 0.8)),
            peso_vinculo=float(pesos.get("bond", 0.4)),
            peso_utilidad=float(pesos.get("utility", 0.5)),
            dreams_per_night=int(rem.get("dreams_per_night", 1)),
            dream_memories=int(rem.get("memories_per_dream", 3)),
            max_dream_similarity=float(rem.get("max_similarity", 0.12)),
            dream_impulses=bool(rem.get("spawn_impulses", True)),
            chain_probability=float(rem.get("chain_probability", 0.4)),
            chain_max_age_hours=float(rem.get("chain_max_age_hours", 48)),
            forget_min_age_days=float(olvido.get("min_age_days", 45)),
            forget_max_importance=float(olvido.get("max_importance", 0.6)),
            forget_require_unrecalled=bool(olvido.get("require_unrecalled", True)),
            forget_batch_cap=int(olvido.get("batch_cap", 300)),
            merged_grace_days=float(olvido.get("merged_grace_days", 7)),
        )


class SleepCycle(ConsolidacionNREM, FaseREM):
    """Las tres fases del sueño sobre la memoria FTS5 de Yuki."""

    def __init__(self, engine: Any, policy: Optional[SleepPolicy] = None,
                 narrator: Optional[Callable[[str, str], Awaitable[str]]] = None,
                 rng: Optional[random.Random] = None,
                 audit: Optional[Callable[[str, Dict[str, Any]], None]] = None):
        self.engine = engine
        self.policy = policy or SleepPolicy()
        # `narrator(system, user) -> texto`. Sin él, la consolidación y el sueño
        # siguen funcionando de forma determinista: peor prosa, misma estructura,
        # y ni una sola llamada a un proveedor cuando no hay ninguno configurado.
        self.narrator = narrator
        self.rng = rng or random.Random()
        self.audit = audit

    # -- utilidades ------------------------------------------------------

    def _conexion(self) -> sqlite3.Connection:
        return self.engine._get_connection()

    def _filas(self, sql: str, params: Sequence[Any] = ()) -> List[sqlite3.Row]:
        with self._conexion() as conexion:
            return conexion.execute(sql, tuple(params)).fetchall()

    def _anotar(self, operacion: str, detalle: Dict[str, Any]) -> None:
        if self.audit:
            try:
                self.audit(operacion, detalle)
            except Exception:
                logger.warning("No se pudo registrar la operación de sueño '%s'", operacion)

    # ------------------------------------------------------------------
    # Olvido intencional
    # ------------------------------------------------------------------

    def prune(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Suelta lo que ya no sostiene nada, y lo demuestra.

        Sólo episodios: nunca el canon, las síntesis, el crecimiento, los
        esquemas ni lo fijado. Y sólo lo que además es viejo, poco importante y
        nunca recuperado; cualquiera de las tres cosas por separado sería una
        mala razón para olvidar.
        """
        if not self.policy.enabled:
            return {"omitido": "ciclo de sueño desactivado"}

        limite_edad = time.time() - self.policy.forget_min_age_days * 86400
        condiciones = [
            "merged_into IS NULL",
            "(kind IS NULL OR kind = ?)",
            "COALESCE(pinned, 0) = 0",
            "created_at < ?",
            "importance <= ?",
            f"category NOT IN ({','.join('?' for _ in CATEGORIAS_PROTEGIDAS)})",
        ]
        parametros: List[Any] = [EPISODICO, limite_edad, self.policy.forget_max_importance,
                                 *sorted(CATEGORIAS_PROTEGIDAS)]
        if self.policy.forget_require_unrecalled:
            condiciones.append("COALESCE(recall_count, 0) = 0")

        candidatos = self._filas(
            f"SELECT id, category, user_id, title, importance, created_at FROM memories "
            f"WHERE {' AND '.join(condiciones)} ORDER BY importance ASC, created_at ASC LIMIT ?",
            [*parametros, self.policy.forget_batch_cap],
        )

        # Y los fusionados que ya cumplieron su periodo de gracia: durante unos
        # días se pudo deshacer la fusión; pasado ese plazo, sobran.
        limite_fusion = time.time() - self.policy.merged_grace_days * 86400
        fusionados = self._filas(
            "SELECT id FROM memories WHERE merged_into IS NOT NULL AND updated_at < ? LIMIT ?",
            [limite_fusion, self.policy.forget_batch_cap],
        )

        identificadores = [fila["id"] for fila in candidatos] + [fila["id"] for fila in fusionados]
        if not dry_run and identificadores:
            marcas = ",".join("?" for _ in identificadores)
            with self._conexion() as conexion:
                conexion.execute(f"DELETE FROM memories WHERE id IN ({marcas})", identificadores)
                conexion.commit()

        recibo = {
            "fase": "olvido",
            "olvidados": len(candidatos),
            "fusionados_retirados": len(fusionados),
            "seco": dry_run,
            "criterio": {
                "edad_minima_dias": self.policy.forget_min_age_days,
                "importancia_maxima": self.policy.forget_max_importance,
                "sin_recuperaciones": self.policy.forget_require_unrecalled,
            },
            # Se guardan títulos, no contenidos: hace falta poder revisar qué se
            # soltó sin conservar lo soltado.
            "muestra": [fila["title"][:80] for fila in candidatos[:5]],
        }
        self._anotar("sueno_olvido", recibo)
        logger.info("Olvido intencional: %d recuerdo(s), %d fusionado(s).",
                    len(candidatos), len(fusionados))
        return recibo

    # ------------------------------------------------------------------

    async def full_night(self, dry_run: bool = False, with_prune: bool = False) -> Dict[str, Any]:
        """Noche completa: consolidar, soñar y —si toca— olvidar."""
        resultado: Dict[str, Any] = {"inicio": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        resultado["nrem"] = await self.nrem(dry_run=dry_run)
        resultado["rem"] = await self.dream(dry_run=dry_run)
        if with_prune:
            resultado["olvido"] = self.prune(dry_run=dry_run)
        return resultado
