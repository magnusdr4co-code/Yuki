"""
REM: tejer una imagen con recuerdos que no se parecen, y desear a partir de ella.

La fase que produce asociaciones nuevas —y en Yuki, además, impulsos: de un
sueño nace un deseo—. Toda ella gira alrededor de la primera invariante del
proyecto: **un sueño nunca es un recuerdo**. Se guarda con `kind='sueno'`, queda
fuera de la recuperación normal y lleva `MARCA_DE_SUENO` escrita en el propio
contenido, para que una imagen onírica que se colara en un prompt por un camino
nuevo siga diciendo que no ocurrió.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .sueno_comun import BASE_POR_CATEGORIA, MARCA_DE_SUENO, SUENO, similitud

logger = logging.getLogger("Yuki.Sueño")


class FaseREM:
    """
    Soñar y lo que nace del sueño, como mixin de `SleepCycle`.

    Cuenta con `self.policy`, `self._filas`, `self._conexion`, `self._anotar`,
    el narrador (`self.narrator`) y el azar reproducible (`self.rng`).
    """

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

    def _ultimo_sueno(self) -> Optional[sqlite3.Row]:
        """El sueño más reciente, si aún cuenta como «anoche»."""
        limite = time.time() - self.policy.chain_max_age_hours * 3600
        filas = self._filas(
            "SELECT id, title, content, created_at FROM memories "
            "WHERE kind = 'sueno' AND created_at >= ? ORDER BY created_at DESC LIMIT 1",
            [limite],
        )
        return filas[0] if filas else None

    async def dream(self, dry_run: bool = False,
                    chain: Optional[bool] = None) -> Dict[str, Any]:
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

        # Encadenar: a veces la imagen de anoche vuelve y sigue. Es lo que
        # convierte una colección de sueños sueltos en una serie, y también lo
        # más delicado de sostener con honestidad: el sueño anterior entra como
        # sueño —nunca como recuerdo— y el nuevo sigue marcado igual.
        anterior = self._ultimo_sueno() if chain is not False else None
        encadenar = bool(anterior) and (chain is True or
                                        (chain is None and self.rng.random() < self.policy.chain_probability))

        material = "\n".join(f"- [{s['category']}] {s['title']}: {s['content'][:200]}"
                             for s in semillas)
        instruccion = (
            "Estás dormida. Teje estos recuerdos lejanos en una sola imagen onírica, "
            "breve (3-5 frases), en primera persona. No expliques el sueño ni lo "
            "interpretes; no afirmes que ocurrió. Es una imagen, no una crónica."
        )
        if encadenar:
            material = (f"Imagen de la noche anterior (fue un sueño, no algo vivido):\n"
                        f"{anterior['content'][:600]}\n\nMateriales nuevos:\n{material}")
            instruccion = (
                "Estás dormida y vuelve la imagen de anoche. Retómala y déjala avanzar con "
                "estos materiales nuevos, en 3-5 frases y en primera persona. No expliques "
                "nada, no afirmes que ocurrió, y no la trates como un recuerdo: era un sueño "
                "y sigue siéndolo."
            )

        texto = None
        if self.narrator:
            try:
                texto = await self.narrator(instruccion, material)
            except Exception as exc:
                logger.warning("El narrador no pudo soñar: %s", type(exc).__name__)
        if not texto:
            # Sin modelo no se finge una imagen: se deja constancia del encuentro
            # de materiales, que es lo único que de verdad ocurrió.
            texto = ("Los materiales se rozaron mientras dormía, sin que ninguna imagen "
                     "llegara a formarse:\n" + material)

        contenido = f"{MARCA_DE_SUENO}\n{texto}"
        etiquetas = "sueno rem no_ocurrio"
        if encadenar:
            etiquetas += f" serie:{anterior['id']}"
        identificador = None
        if not dry_run:
            identificador = self.engine.add_memory(
                category="dream",
                title=("Sueño de " + datetime.now(timezone.utc).strftime("%Y-%m-%d")
                       + (" (sigue)" if encadenar else "")),
                content=contenido,
                tags=etiquetas,
                user_id="general",
                importance=BASE_POR_CATEGORIA["dream"],
                kind=SUENO,
            )
        return {
            "fase": "rem", "sonado": True, "id": identificador,
            "semillas": [s["id"] for s in semillas],
            "categorias": sorted({s["category"] for s in semillas}),
            "encadenado": encadenar,
            "anterior": anterior["id"] if encadenar else None,
            "contenido": contenido, "seco": dry_run,
        }

    def dream_series(self, limite: int = 10) -> List[Dict[str, Any]]:
        """
        Los sueños recientes con su hilo: cuál retomó a cuál.

        Sirve para leerlos como serie en vez de como piezas sueltas, que es lo
        único que justifica encadenarlos.
        """
        filas = self._filas(
            "SELECT id, title, content, tags, created_at FROM memories "
            "WHERE kind = 'sueno' ORDER BY created_at DESC LIMIT ?", [limite])
        serie = []
        for fila in filas:
            etiquetas = fila["tags"] or ""
            padre = None
            if "serie:" in etiquetas:
                try:
                    padre = int(etiquetas.split("serie:")[-1].split()[0])
                except (ValueError, IndexError):
                    padre = None
            serie.append({
                "id": fila["id"], "titulo": fila["title"], "sigue_a": padre,
                "cuando": datetime.fromtimestamp(fila["created_at"], timezone.utc).isoformat(timespec="minutes"),
                "contenido": fila["content"],
            })
        return serie

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
