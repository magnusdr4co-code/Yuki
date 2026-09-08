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
"""

from __future__ import annotations

import json
import logging
import math
import random
import re
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Set, Tuple

logger = logging.getLogger("Yuki.Sueño")

EPISODICO = "episodico"
ESQUEMA = "esquema"
SUENO = "sueno"

# Prefijo obligatorio de todo sueño. Va en el contenido, no sólo en una columna:
# si alguna vez un sueño se cuela en un prompt por un camino nuevo, el texto
# mismo dice que no ocurrió.
MARCA_DE_SUENO = "[SUEÑO — no ocurrió; imagen tejida al dormir]"

# Base de importancia por categoría. Existe para que recalcular sea idempotente:
# si la importancia se recalculara sobre sí misma, cada noche la subiría un poco
# y en un mes todo sería importantísimo, que es lo mismo que nada lo sea.
BASE_POR_CATEGORIA: Dict[str, float] = {
    "core": 3.0,
    "producer": 2.5,
    "schema": 2.2,
    "daily_synthesis": 2.0,
    "project": 1.8,
    "growth": 1.5,
    "visitor": 1.0,
    "inner_thought": 1.0,
    "dream": 0.6,
}
BASE_POR_DEFECTO = 1.0

# Categorías que el olvido no toca nunca. El canon, las síntesis y el
# crecimiento son la columna vertebral: podarlos sería amnesia, no higiene.
CATEGORIAS_PROTEGIDAS = frozenset({"core", "daily_synthesis", "growth", "schema", "producer"})

# Léxico afectivo mínimo para estimar saliencia cuando no venía declarada. No
# pretende medir emoción: pretende distinguir un encuentro que dejó huella de un
# intercambio de cortesías.
LEXICO_SALIENTE = (
    "miedo", "muerte", "madre", "padre", "amor", "duelo", "perdón", "vergüenza",
    "gracias", "solo", "sola", "herida", "por primera vez", "nunca", "siempre",
    "me dijo", "confesó", "lloró", "prometí", "acordamos", "decidimos",
)

PALABRA = re.compile(r"[a-záéíóúñü]+", re.IGNORECASE)


def trigramas(texto: str) -> Set[str]:
    """Firma léxica de un texto: trigramas de caracteres sobre palabras normalizadas."""
    limpio = " ".join(PALABRA.findall((texto or "").lower()))
    if len(limpio) < 3:
        return set()
    return {limpio[i:i + 3] for i in range(len(limpio) - 2)}


def similitud(a: str, b: str, comunes: Optional[Set[str]] = None) -> float:
    """
    Jaccard sobre trigramas, descontando lo que sea plantilla.

    Sin `comunes` compara en crudo. Con él —el conjunto de trigramas que
    aparecen en casi todos los recuerdos del grupo— compara sólo la parte
    distintiva, que es la única que decide si dos recuerdos son el mismo.

    Esto no es un refinamiento teórico: sobre la memoria real de la instancia,
    dos encuentros con preguntas **distintas** («¿qué tal el progreso?» y
    «¿sigues despierta?») daban 0.80 de similitud, porque el andamiaje del
    registro —«Intercambio con X (@id): - Dijo: … - Yuki respondió: …»— pesa
    más que lo que se dijo. Fusionarlos habría borrado dos recuerdos por el
    precio de uno.
    """
    ta, tb = trigramas(a), trigramas(b)
    if comunes:
        ta, tb = ta - comunes, tb - comunes
    if not ta or not tb:
        return 0.0
    interseccion = len(ta & tb)
    return interseccion / float(len(ta) + len(tb) - interseccion)


def trigramas_de_plantilla(textos: Sequence[str], umbral: float = 0.6) -> Set[str]:
    """
    Trigramas que aparecen en la mayoría de los textos: andamiaje, no contenido.

    Se calcula por grupo y no con una lista fija de fórmulas conocidas, porque
    una lista fija envejece: basta con que alguien cambie el formato del
    registro para que vuelva a colarse la plantilla en la comparación.
    """
    if len(textos) < 3:
        return set()
    frecuencia: Dict[str, int] = {}
    for texto in textos:
        for trigrama in trigramas(texto):
            frecuencia[trigrama] = frecuencia.get(trigrama, 0) + 1
    limite = max(2, int(len(textos) * umbral))
    return {trigrama for trigrama, veces in frecuencia.items() if veces >= limite}


@dataclass
class SleepPolicy:
    """Umbrales del ciclo. Todo esto vive en `config.yaml: memory.sleep`."""

    enabled: bool = True

    # NREM
    merge_threshold: float = 0.72
    # Fracción del grupo a partir de la cual un trigrama se considera plantilla.
    template_df: float = 0.6
    # Masa distintiva mínima entre dos recuerdos para que su parte propia pueda
    # desmentir el parecido bruto. Por debajo de esto no hay nada en que
    # discrepar: son el mismo recuerdo escrito dos veces.
    min_distinctive: int = 12
    schema_min_members: int = 4
    peso_saliencia: float = 0.6
    peso_recurrencia: float = 0.8
    peso_vinculo: float = 0.4
    peso_utilidad: float = 0.5

    # REM
    dreams_per_night: int = 1
    dream_memories: int = 3
    max_dream_similarity: float = 0.12   # los recuerdos del sueño deben ser lejanos
    dream_impulses: bool = True

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
            template_df=float(nrem.get("template_df", 0.6)),
            min_distinctive=int(nrem.get("min_distinctive", 12)),
            schema_min_members=int(nrem.get("schema_min_members", 4)),
            peso_saliencia=float(pesos.get("salience", 0.6)),
            peso_recurrencia=float(pesos.get("recurrence", 0.8)),
            peso_vinculo=float(pesos.get("bond", 0.4)),
            peso_utilidad=float(pesos.get("utility", 0.5)),
            dreams_per_night=int(rem.get("dreams_per_night", 1)),
            dream_memories=int(rem.get("memories_per_dream", 3)),
            max_dream_similarity=float(rem.get("max_similarity", 0.12)),
            dream_impulses=bool(rem.get("spawn_impulses", True)),
            forget_min_age_days=float(olvido.get("min_age_days", 45)),
            forget_max_importance=float(olvido.get("max_importance", 0.6)),
            forget_require_unrecalled=bool(olvido.get("require_unrecalled", True)),
            forget_batch_cap=int(olvido.get("batch_cap", 300)),
            merged_grace_days=float(olvido.get("merged_grace_days", 7)),
        )


class SleepCycle:
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
    # NREM — consolidación
    # ------------------------------------------------------------------

    def _saliencia_estimada(self, fila: sqlite3.Row) -> float:
        """Carga afectiva aproximada, si no venía declarada al grabar."""
        declarada = float(fila["salience"] or 0.0)
        if declarada > 0:
            return min(1.0, declarada)
        texto = f"{fila['title']} {fila['content']}".lower()
        golpes = sum(1 for palabra in LEXICO_SALIENTE if palabra in texto)
        return min(1.0, golpes / 3.0)

    @staticmethod
    def _utilidad(fila: sqlite3.Row) -> float:
        """Si el recuerdo condujo a obra o a un acto propio."""
        etiquetas = (fila["tags"] or "").lower()
        marcas = ("obra", "biblioteca", "cancion", "canción", "portada", "autonomia", "letra")
        return 1.0 if any(marca in etiquetas for marca in marcas) else 0.0

    def recompute_importance(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Recalcula el vector de importancia y la importancia efectiva.

        La fórmula parte de una base por categoría —no de la importancia
        actual— para que repetirla cada noche no infle nada: si el cálculo se
        alimentara de su propio resultado, en un mes todo sería importantísimo,
        que es lo mismo que nada lo sea.
        """
        filas = self._filas(
            "SELECT id, category, title, content, tags, user_id, importance, salience, "
            "recall_count, kind FROM memories WHERE merged_into IS NULL"
        )
        # Vínculo: cuántos recuerdos comparte Yuki con cada persona. Alguien con
        # una sola visita no ata; alguien que vuelve, sí.
        conteo_por_persona: Dict[str, int] = {}
        for fila in filas:
            if fila["user_id"] and fila["user_id"] != "general":
                conteo_por_persona[fila["user_id"]] = conteo_por_persona.get(fila["user_id"], 0) + 1

        cambios: List[Tuple[float, float, float, float, float, int]] = []
        for fila in filas:
            saliencia = self._saliencia_estimada(fila)
            recuerdos = float(fila["recall_count"] or 0)
            recurrencia = min(1.0, math.log1p(recuerdos) / math.log(6.0))
            vinculo = (min(1.0, conteo_por_persona.get(fila["user_id"], 0) / 8.0)
                       if fila["user_id"] and fila["user_id"] != "general" else 0.0)
            utilidad = self._utilidad(fila)

            base = BASE_POR_CATEGORIA.get(fila["category"], BASE_POR_DEFECTO)
            multiplicador = (1.0
                             + self.policy.peso_saliencia * saliencia
                             + self.policy.peso_recurrencia * recurrencia
                             + self.policy.peso_vinculo * vinculo
                             + self.policy.peso_utilidad * utilidad)
            importancia = max(0.1, min(5.0, base * multiplicador))
            if abs(importancia - float(fila["importance"] or 0)) > 1e-6 or saliencia > 0:
                cambios.append((saliencia, recurrencia, vinculo, utilidad, importancia, fila["id"]))

        if not dry_run and cambios:
            with self._conexion() as conexion:
                conexion.executemany(
                    "UPDATE memories SET salience = ?, recurrence = ?, bond = ?, utility = ?, "
                    "importance = ?, updated_at = strftime('%s','now') WHERE id = ?",
                    cambios,
                )
                conexion.commit()
        return {"revisados": len(filas), "actualizados": len(cambios), "seco": dry_run}

    def _es_duplicado(self, id_a: int, id_b: int, textos: Dict[int, str],
                      distintivos: Dict[int, Set[str]], plantilla: Set[str]) -> bool:
        """
        Dos recuerdos son el mismo si se parecen **y** su parte propia no lo desmiente.

        Hacen falta las dos señales, y cada una corrige un error de la otra:

        · Sólo el parecido bruto fusiona dos conversaciones distintas que
          comparten el formato del registro, porque el andamiaje pesa más que lo
          que se dijo. Ocurría de verdad: 0.80 de similitud entre «¿qué tal el
          progreso?» y «¿sigues despierta?».
        · Sólo la parte distintiva falla en el caso contrario: cuando dos
          recuerdos son copias exactas, *todo* en ellos es plantilla, no queda
          nada propio y la comparación daría cero justo donde la fusión era
          evidente.

        Así que primero se exige parecido bruto, y después se le da a la parte
        propia la oportunidad de desmentirlo —sólo si hay parte propia bastante
        como para que su silencio signifique algo.
        """
        parecido = similitud(textos[id_a], textos[id_b])
        if parecido < self.policy.merge_threshold:
            return False

        masa_distintiva = len(distintivos[id_a]) + len(distintivos[id_b])
        if masa_distintiva < self.policy.min_distinctive:
            # Nada propio en que discrepar: es el mismo recuerdo escrito dos veces.
            return True

        return similitud(textos[id_a], textos[id_b], plantilla) >= self.policy.merge_threshold

    def merge_duplicates(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Funde recuerdos casi idénticos en el más antiguo.

        Se comparan sólo dentro de la misma categoría y persona: dos encuentros
        parecidos con la misma persona son lo mismo contado dos veces; un poema
        parecido a una conversación, no.

        Lo fusionado no se borra aquí, se marca. Durante unos días sigue en la
        base, invisible a la búsqueda pero recuperable si la fusión fue un
        error; después lo recoge el olvido. Es la recuperabilidad que la
        revisión de agentes persistentes echa en falta en todo el campo.
        """
        filas = self._filas(
            "SELECT id, category, user_id, title, content, recall_count, created_at "
            "FROM memories WHERE merged_into IS NULL AND (kind IS NULL OR kind = 'episodico') "
            "ORDER BY created_at ASC"
        )
        grupos: Dict[Tuple[str, str], List[sqlite3.Row]] = {}
        for fila in filas:
            grupos.setdefault((fila["category"], fila["user_id"] or "general"), []).append(fila)

        fusiones: List[Tuple[int, List[int]]] = []
        for miembros in grupos.values():
            if len(miembros) < 2:
                continue
            # La plantilla se calcula por grupo: cada categoría y cada persona
            # tienen la suya, y lo que en una es andamiaje en otra es contenido.
            textos = {fila["id"]: f"{fila['title']} {fila['content']}" for fila in miembros}
            plantilla = trigramas_de_plantilla(list(textos.values()), self.policy.template_df)
            distintivos = {ident: trigramas(texto) - plantilla for ident, texto in textos.items()}

            ya_fusionados: Set[int] = set()
            for indice, canonico in enumerate(miembros):
                if canonico["id"] in ya_fusionados:
                    continue
                duplicados = []
                for candidato in miembros[indice + 1:]:
                    if candidato["id"] in ya_fusionados:
                        continue
                    if self._es_duplicado(canonico["id"], candidato["id"], textos, distintivos,
                                          plantilla):
                        duplicados.append(candidato["id"])
                        ya_fusionados.add(candidato["id"])
                if duplicados:
                    fusiones.append((canonico["id"], duplicados))

        fusionados = sum(len(dup) for _, dup in fusiones)
        if not dry_run and fusiones:
            with self._conexion() as conexion:
                for canonico, duplicados in fusiones:
                    marcas = ",".join("?" for _ in duplicados)
                    recuerdos_sumados = conexion.execute(
                        f"SELECT COALESCE(SUM(recall_count), 0) FROM memories WHERE id IN ({marcas})",
                        duplicados,
                    ).fetchone()[0]
                    conexion.execute(
                        f"UPDATE memories SET merged_into = ?, updated_at = strftime('%s','now') "
                        f"WHERE id IN ({marcas})", [canonico, *duplicados],
                    )
                    conexion.execute(
                        "UPDATE memories SET recall_count = COALESCE(recall_count, 0) + ? WHERE id = ?",
                        (recuerdos_sumados, canonico),
                    )
                conexion.commit()
        self._anotar("sueno_fusion", {"grupos": len(fusiones), "fusionados": fusionados,
                                      "seco": dry_run})
        return {"grupos": len(fusiones), "fusionados": fusionados, "seco": dry_run}

    async def distill_schemas(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Destila episodios recurrentes en esquemas: memoria semántica.

        Un esquema no sustituye a los episodios —siguen ahí, y el olvido los
        tratará por sus propios méritos—: los resume en algo que se puede
        recuperar de una vez. Es la reflexión sumaria de la arquitectura de
        agentes generativos, que sus ablaciones señalan como imprescindible
        para que la conducta siga siendo creíble a largo plazo.
        """
        filas = self._filas(
            "SELECT id, category, user_id, title, content, created_at FROM memories "
            "WHERE merged_into IS NULL AND (kind IS NULL OR kind = 'episodico') "
            "AND category = 'visitor' ORDER BY created_at ASC"
        )
        por_persona: Dict[str, List[sqlite3.Row]] = {}
        for fila in filas:
            if fila["user_id"] and fila["user_id"] != "general":
                por_persona.setdefault(fila["user_id"], []).append(fila)

        candidatos = {persona: episodios for persona, episodios in por_persona.items()
                      if len(episodios) >= self.policy.schema_min_members}

        # No se rehace un esquema que ya existe para esa persona y que no ha
        # quedado atrás: destilar lo mismo cada noche llenaría la memoria de
        # resúmenes del resumen.
        existentes = {fila["user_id"]: fila["created_at"] for fila in self._filas(
            "SELECT user_id, MAX(created_at) AS created_at FROM memories "
            "WHERE kind = 'esquema' GROUP BY user_id")}

        creados = []
        for persona, episodios in candidatos.items():
            ultimo_esquema = existentes.get(persona, 0)
            nuevos = [e for e in episodios if e["created_at"] > ultimo_esquema]
            if len(nuevos) < self.policy.schema_min_members:
                continue

            extractos = "\n".join(f"- {e['title']}: {e['content'][:220]}" for e in nuevos[:12])
            texto = None
            if self.narrator:
                try:
                    texto = await self.narrator(
                        "Estás consolidando memoria mientras duermes. Destila, en tres o cuatro "
                        "frases en primera persona, lo que estos encuentros dicen de esta persona "
                        "y de tu vínculo con ella. No inventes hechos que no aparezcan.",
                        extractos,
                    )
                except Exception as exc:
                    logger.warning("El narrador no pudo destilar el esquema: %s", type(exc).__name__)
            if not texto:
                # Sin modelo, el esquema sigue existiendo: peor prosa, misma
                # función. Nunca se inventa contenido para rellenar.
                texto = ("Rastro acumulado de esta persona, sin destilar por el modelo:\n"
                         + extractos)

            if not dry_run:
                identificador = self.engine.add_memory(
                    category="schema",
                    title=f"Esquema de vínculo — {persona}",
                    content=texto,
                    tags=f"esquema vinculo {persona}",
                    user_id=persona,
                    importance=BASE_POR_CATEGORIA["schema"],
                    kind=ESQUEMA,
                )
                creados.append(identificador)
            else:
                creados.append(-1)

        return {"candidatos": len(candidatos), "esquemas_creados": len(creados), "seco": dry_run}

    async def nrem(self, dry_run: bool = False) -> Dict[str, Any]:
        """La fase completa de consolidación."""
        if not self.policy.enabled:
            return {"omitido": "ciclo de sueño desactivado"}
        importancia = self.recompute_importance(dry_run=dry_run)
        fusion = self.merge_duplicates(dry_run=dry_run)
        esquemas = await self.distill_schemas(dry_run=dry_run)
        resultado = {"fase": "nrem", "importancia": importancia, "fusion": fusion,
                     "esquemas": esquemas}
        logger.info("NREM: %s", json.dumps(resultado, ensure_ascii=False))
        return resultado

    # ------------------------------------------------------------------
    # REM — soñar
    # ------------------------------------------------------------------

    def _elegir_lejanos(self) -> List[sqlite3.Row]:
        """
        Escoge recuerdos que no se parecen entre sí.

        Ahí está la gracia del sueño: unir lo que la recuperación por relevancia
        nunca pondría junto. Si se eligieran por semejanza saldría un resumen,
        no una imagen.
        """
        filas = self._filas(
            "SELECT id, category, title, content, created_at, importance FROM memories "
            "WHERE merged_into IS NULL AND (kind IS NULL OR kind != 'sueno') "
            "ORDER BY importance DESC LIMIT 120"
        )
        if len(filas) < 2:
            return []

        candidatos = list(filas)
        self.rng.shuffle(candidatos)
        elegidos: List[sqlite3.Row] = [candidatos.pop()]
        for fila in candidatos:
            if len(elegidos) >= self.policy.dream_memories:
                break
            texto_nuevo = f"{fila['title']} {fila['content']}"
            if all(similitud(texto_nuevo, f"{e['title']} {e['content']}")
                   <= self.policy.max_dream_similarity for e in elegidos):
                elegidos.append(fila)
        return elegidos if len(elegidos) >= 2 else []

    async def dream(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Teje una imagen con recuerdos lejanos. No ocurrió, y se dice.

        El sueño se guarda con `kind='sueno'`, fuera de la recuperación normal y
        con la marca escrita en el propio contenido. Puede alimentar la cola de
        voluntad —de soñar nace desear— pero nunca puede volver como un hecho.
        """
        if not self.policy.enabled:
            return {"omitido": "ciclo de sueño desactivado"}

        semillas = self._elegir_lejanos()
        if not semillas:
            return {"fase": "rem", "sonado": False,
                    "motivo": "no hay recuerdos suficientemente lejanos todavía"}

        material = "\n".join(f"- [{s['category']}] {s['title']}: {s['content'][:200]}"
                             for s in semillas)
        texto = None
        if self.narrator:
            try:
                texto = await self.narrator(
                    "Estás dormida. Teje estos recuerdos lejanos en una sola imagen onírica, "
                    "breve (3-5 frases), en primera persona. No expliques el sueño ni lo "
                    "interpretes; no afirmes que ocurrió. Es una imagen, no una crónica.",
                    material,
                )
            except Exception as exc:
                logger.warning("El narrador no pudo soñar: %s", type(exc).__name__)
        if not texto:
            # Sin modelo no se finge una imagen: se deja constancia del encuentro
            # de materiales, que es lo único que de verdad ocurrió.
            texto = ("Los materiales se rozaron mientras dormía, sin que ninguna imagen "
                     "llegara a formarse:\n" + material)

        contenido = f"{MARCA_DE_SUENO}\n{texto}"
        identificador = None
        if not dry_run:
            identificador = self.engine.add_memory(
                category="dream",
                title=f"Sueño de {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
                content=contenido,
                tags="sueno rem no_ocurrio",
                user_id="general",
                importance=BASE_POR_CATEGORIA["dream"],
                kind=SUENO,
            )
        return {
            "fase": "rem", "sonado": True, "id": identificador,
            "semillas": [s["id"] for s in semillas],
            "categorias": sorted({s["category"] for s in semillas}),
            "contenido": contenido, "seco": dry_run,
        }

    def impulse_from_dream(self, dream: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Convierte un sueño en un deseo para la cola de voluntad.

        Es la razón de que el sueño no sea decorativo: la asociación nueva que
        produce la fase REM entra en el sistema por donde entra todo lo que Yuki
        quiere hacer, y compite con el resto de impulsos en igualdad.
        """
        if not self.policy.dream_impulses or not dream.get("sonado"):
            return None
        categorias = dream.get("categorias") or []
        herramienta = "write" if "visitor" in categorias or "core" in categorias else "contemplate"
        return {
            "source": "sueno",
            "desire": "Quiero seguir la imagen que se me quedó del sueño de esta noche.",
            "tool_hint": herramienta,
            "dream_id": dream.get("id"),
        }

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
            "(kind IS NULL OR kind = 'episodico')",
            "COALESCE(pinned, 0) = 0",
            "created_at < ?",
            "importance <= ?",
            f"category NOT IN ({','.join('?' for _ in CATEGORIAS_PROTEGIDAS)})",
        ]
        parametros: List[Any] = [limite_edad, self.policy.forget_max_importance,
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
