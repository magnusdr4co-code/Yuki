"""
NREM: recalcular qué importa, fundir lo repetido y destilar esquemas.

Es la fase que convierte memoria episódica en semántica, y la que más cuidado
pide: fundir dos recuerdos que no eran el mismo es perder uno, así que la
fusión es reversible durante los días de gracia de la política y `undo_merge`
existe de verdad —la documentación lo prometió antes de que existiera y ése es
justo el fallo que este proyecto no repite—.

Vive fuera de `sleep_cycle.py` porque sus 400 líneas no las comparte con nadie:
el olvido y el sueño sólo necesitan la conexión y el recibo.
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
import time
from typing import Any, Dict, List, Sequence, Set, Tuple

from .sueno_comun import (
    BASE_POR_CATEGORIA,
    BASE_POR_DEFECTO,
    EPISODICO,
    ESQUEMA,
    LEXICO_SALIENTE,
    PALABRA,
    VACIAS,
    similitud,
    trigramas,
    trigramas_de_plantilla,
)

logger = logging.getLogger("Yuki.Sueño")


class ConsolidacionNREM:
    """
    La consolidación del sueño, como mixin de `SleepCycle`.

    Cuenta con `self.policy`, `self._filas`, `self._conexion` y `self._anotar`:
    el acceso a la memoria y la bitácora los pone la clase que la compone, que
    es la única que sabe de qué motor se trata.
    """

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
            "FROM memories WHERE merged_into IS NULL AND (kind IS NULL OR kind = ?) "
            "ORDER BY created_at ASC",
            (EPISODICO,),
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

    def pending_merges(self) -> List[Dict[str, Any]]:
        """
        Fusiones que todavía se pueden deshacer, agrupadas por su canónico.

        La documentación prometía que una fusión es recuperable durante el
        periodo de gracia; sin esta consulta y sin `undo_merge`, esa promesa era
        una intención. Aquí está lo que queda dentro del plazo, con lo que se
        absorbió, para poder mirarlo antes de decidir.
        """
        limite = time.time() - self.policy.merged_grace_days * 86400
        filas = self._filas(
            "SELECT m.id, m.merged_into, m.title, m.updated_at, "
            "       c.title AS titulo_canonico "
            "FROM memories m LEFT JOIN memories c ON c.id = m.merged_into "
            "WHERE m.merged_into IS NOT NULL AND m.updated_at >= ? "
            "ORDER BY m.merged_into, m.id", [limite],
        )
        grupos: Dict[int, Dict[str, Any]] = {}
        for fila in filas:
            grupo = grupos.setdefault(fila["merged_into"], {
                "canonico": fila["merged_into"],
                "titulo": fila["titulo_canonico"],
                "absorbidos": [],
                "expira_en_dias": round(
                    self.policy.merged_grace_days - (time.time() - fila["updated_at"]) / 86400.0, 1),
            })
            grupo["absorbidos"].append({"id": fila["id"], "titulo": fila["title"][:80]})
        return list(grupos.values())

    def undo_merge(self, canonical_id: int) -> Dict[str, Any]:
        """
        Deshace una fusión: los recuerdos absorbidos vuelven a existir por su cuenta.

        Devolver también las recuperaciones que se sumaron al canónico importa
        más de lo que parece: si se quedaran allí, el recuerdo que absorbió a los
        demás arrastraría para siempre una recurrencia que no era suya y el
        siguiente recálculo de importancia lo trataría como más vivo de lo que
        es. Deshacer tiene que devolver el estado, no sólo las filas.

        Pasado el periodo de gracia los absorbidos ya no están: entonces esto no
        puede hacer nada y lo dice, en vez de fingir que restauró algo.
        """
        absorbidos = self._filas(
            "SELECT id, recall_count FROM memories WHERE merged_into = ?", [canonical_id])
        if not absorbidos:
            return {"restaurados": 0,
                    "motivo": f"no hay recuerdos absorbidos por {canonical_id} "
                              "(o su periodo de gracia ya pasó y se olvidaron)"}

        devueltos = sum(int(fila["recall_count"] or 0) for fila in absorbidos)
        with self._conexion() as conexion:
            conexion.execute(
                "UPDATE memories SET merged_into = NULL, updated_at = strftime('%s','now') "
                "WHERE merged_into = ?", (canonical_id,))
            conexion.execute(
                "UPDATE memories SET recall_count = MAX(0, COALESCE(recall_count, 0) - ?) "
                "WHERE id = ?", (devueltos, canonical_id))
            conexion.commit()

        recibo = {"canonico": canonical_id, "restaurados": len(absorbidos),
                  "recuperaciones_devueltas": devueltos}
        self._anotar("sueno_fusion_deshecha", recibo)
        logger.warning("Fusión deshecha sobre %s: %d recuerdo(s) vuelven.",
                       canonical_id, len(absorbidos))
        return recibo

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

    def _etiqueta_de_tema(self, textos: Sequence[str]) -> str:
        """Nombre del tema: las palabras que se repiten y significan algo."""
        frecuencia: Dict[str, int] = {}
        for texto in textos:
            for palabra in set(PALABRA.findall(texto.lower())):
                if len(palabra) > 3 and palabra not in VACIAS:
                    frecuencia[palabra] = frecuencia.get(palabra, 0) + 1
        mejores = sorted(frecuencia.items(), key=lambda par: (-par[1], par[0]))[:3]
        return ", ".join(palabra for palabra, _ in mejores) or "sin nombre"

    async def distill_themes(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Destila corrientes: lo que se repite a través de personas y categorías.

        El esquema de vínculo responde a «quién es esta persona para mí». Este
        responde a otra cosa: «qué me está ocupando». Son agrupaciones flojas
        —el umbral es la mitad del de fusión— porque un tema junta cosas que se
        hablan parecido, no cosas que son la misma; con el umbral de fusión no
        saldría ningún tema, y con uno más bajo saldría uno solo que lo abarca
        todo y no dice nada.

        La plantilla del corpus se descuenta igual que en la fusión: sin eso, el
        único tema que emergería sería el formato del registro.
        """
        filas = self._filas(
            "SELECT id, category, user_id, title, content, created_at FROM memories "
            "WHERE merged_into IS NULL AND (kind IS NULL OR kind = ?) "
            "AND category NOT IN ('dream') ORDER BY created_at ASC LIMIT 400",
            (EPISODICO,),
        )
        if len(filas) < self.policy.theme_min_members:
            return {"temas": 0, "seco": dry_run}

        textos = {fila["id"]: f"{fila['title']} {fila['content']}" for fila in filas}
        plantilla = trigramas_de_plantilla(list(textos.values()), self.policy.template_df)

        # Agrupación voraz: cada recuerdo se une al primer grupo con el que se
        # parece bastante. No es el mejor algoritmo posible; es determinista,
        # barato y explicable, que aquí vale más.
        grupos: List[List[int]] = []
        for fila in filas:
            identificador = fila["id"]
            for grupo in grupos:
                if similitud(textos[identificador], textos[grupo[0]], plantilla) >= self.policy.theme_threshold:
                    grupo.append(identificador)
                    break
            else:
                grupos.append([identificador])

        candidatos = [g for g in grupos if len(g) >= self.policy.theme_min_members]

        etiquetas_vivas = {
            (fila["tags"] or "").split("tema:")[-1].strip()
            for fila in self._filas("SELECT tags FROM memories WHERE kind = 'esquema' "
                                    "AND tags LIKE '%tema:%'")
        }

        creados = 0
        for grupo in candidatos:
            etiqueta = self._etiqueta_de_tema([textos[i] for i in grupo])
            if etiqueta in etiquetas_vivas:
                continue
            extractos = "\n".join(f"- {textos[i][:200]}" for i in grupo[:10])
            texto = None
            if self.narrator:
                try:
                    texto = await self.narrator(
                        "Estás consolidando memoria mientras duermes. Estos fragmentos vuelven "
                        "una y otra vez en tu vida reciente. Nombra en dos o tres frases, en "
                        "primera persona, qué corriente los atraviesa. No inventes hechos.",
                        extractos,
                    )
                except Exception as exc:
                    logger.warning("El narrador no pudo nombrar el tema: %s", type(exc).__name__)
            if not texto:
                texto = f"Corriente recurrente sin destilar por el modelo:\n{extractos}"

            if not dry_run:
                self.engine.add_memory(
                    category="schema",
                    title=f"Corriente — {etiqueta}",
                    content=texto,
                    tags=f"esquema corriente tema:{etiqueta}",
                    user_id="general",
                    importance=BASE_POR_CATEGORIA["schema"],
                    kind=ESQUEMA,
                )
            etiquetas_vivas.add(etiqueta)
            creados += 1

        return {"grupos_detectados": len(candidatos), "temas": creados, "seco": dry_run}

    async def nrem(self, dry_run: bool = False) -> Dict[str, Any]:
        """La fase completa de consolidación."""
        if not self.policy.enabled:
            return {"omitido": "ciclo de sueño desactivado"}
        importancia = self.recompute_importance(dry_run=dry_run)
        fusion = self.merge_duplicates(dry_run=dry_run)
        esquemas = await self.distill_schemas(dry_run=dry_run)
        temas = await self.distill_themes(dry_run=dry_run)
        resultado = {"fase": "nrem", "importancia": importancia, "fusion": fusion,
                     "esquemas": esquemas, "temas": temas}
        logger.info("NREM: %s", json.dumps(resultado, ensure_ascii=False))
        return resultado
