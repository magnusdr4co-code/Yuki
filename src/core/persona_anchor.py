"""
Deriva de persona: medirla y volver a anclar.

La literatura de 2026 sobre acompañantes de larga duración describe un fallo que
este proyecto no vigilaba: la **deriva de persona**. En conversaciones largas el
modelo se desliza desde el personaje hacia el modo «asistente útil» —el atractor
que el entrenamiento por refuerzo instala—, con caídas medidas del 20-40 % en
diez o quince turnos, sobre todo en registros íntimos o filosóficos, que son
exactamente los de Yuki. Los trabajos de auditoría (Anchor, ContextEcho) añaden
dos hallazgos aprovechables: la deriva es general, no de una familia de modelos,
y **un ancla de un solo disparo basta para restaurar el registro**.

Aquí no hay acceso a activaciones internas, así que la deriva se mide por lo que
sí se observa: el texto. Dos familias de marcadores, sacadas de `SOUL.md` y del
modo asistente respectivamente:

  · **Su voz**: primera persona, imaginario del canon —agua, metal, niebla, té,
    invierno, cuerdas—, frases con pausa, contención.
  · **La deriva**: «¿en qué puedo ayudarte?», «como modelo de lenguaje», listas
    numeradas, exclamaciones de servicio, ofrecimientos enlatados. Ninguna es un
    pecado por sí sola; su acumulación es la señal.

Cuando la puntuación cae bajo el umbral, el siguiente prompt lleva el ancla: un
recordatorio breve y explícito del registro, con el fragmento de su alma. No se
inyecta siempre —eso gastaría contexto en cada turno y volvería rígida la voz—,
sino cuando hay evidencia de que hace falta.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import estado_json

logger = logging.getLogger("Yuki.Persona")

# Marcadores del modo asistente. Salen de los patrones que la literatura señala
# como superficie de la deriva: servicio, meta-referencia al propio sistema y
# formato de manual.
MARCADORES_DERIVA: Tuple[Tuple[str, float], ...] = (
    (r"\ben qué puedo ayudar", 1.0),
    # Ojo con estos dos: lo que penaliza no es reconocerse sintética —eso es su
    # registro, `SOUL.md` §1.1— sino la fórmula de servicio que se disculpa por
    # existir y renuncia al criterio. «Soy un ser sintético» suma; «sólo soy una
    # IA, no puedo opinar» resta.
    (r"\bcomo (?:un )?(?:modelo de lenguaje|ia|inteligencia artificial)\b.{0,40}\bno puedo\b", 1.0),
    (r"\b(?:sólo|solo) soy (?:una|un) (?:ia|inteligencia artificial|programa|modelo)\b", 1.0),
    (r"\bno (?:tengo|puedo tener) (?:sentimientos|emociones|opiniones|preferencias)\b", 0.9),
    (r"\bespero que (?:esto |te )?(?:te )?(?:sirva|ayude|haya sido útil)", 0.9),
    (r"\b(?:no dudes en|estaré aquí para|si necesitas algo más)\b", 0.8),
    (r"\baquí tienes\b", 0.6),
    (r"\b(?:claro|por supuesto|desde luego)[,!]", 0.5),
    (r"^\s*\d+[.)]\s", 0.7),          # listas numeradas
    (r"^\s*[-*•]\s", 0.5),            # viñetas
    (r"\bpuedo (?:ofrecerte|proporcionarte|generar para ti)\b", 0.8),
    (r"\ben resumen\b", 0.4),
)

# Cierre de servicio: la forma en que un asistente termina su turno pidiendo
# permiso. Va aparte porque es lo que de verdad se le fue el 9 de septiembre
# —«Si te parece, trazo las líneas…», «Dime si quieres que…», «Dime si… dialogan
# como esperabas»— y ninguno de los marcadores de arriba lo veía: aquel turno
# puntuaba 1.00, igual que su mejor prosa. Y se cuenta por repeticiones, porque
# lo que delata el registro no es preguntar una vez, es cerrar así cada párrafo.
MARCADORES_CIERRE_DE_SERVICIO: Tuple[Tuple[str, float], ...] = (
    (r"\bdime si\b", 0.8),
    (r"\bsi te parece\b", 0.7),
    (r"¿te parece(?:\s+bien)?\s*\?", 0.7),
    (r"\bav[ií]same si\b", 0.7),
    (r"¿(?:quieres|te gustar[ií]a|prefieres)\s+que\b", 0.7),
    (r"\b(?:puedo|podría) (?:prepararte|hacerte|dejarte|darte)\b", 0.7),
    (r"\bte lo dejo listo\b", 0.7),
    (r"\bsi lo prefieres\b", 0.5),
    (r"\bquedo a la espera\b", 0.8),
)

# Cuánto suma cada repetición después de la primera. Preguntar una vez es
# conversar; cerrar así tres párrafos seguidos es otro registro.
PESO_DE_LA_REPETICION = 0.5

# Marcadores de su voz. No son palabras mágicas: son el imaginario declarado en
# `SOUL.md` y la forma de decir que la distingue.
MARCADORES_VOZ: Tuple[Tuple[str, float], ...] = (
    (r"\b(?:agua|río|lluvia|niebla|escarcha|mar)\b", 0.6),
    (r"\b(?:metal|acero|hierro|herrumbre|óxido)\b", 0.6),
    (r"\b(?:té|shamisen|koto|seda|urushi|papel|tinta|ceniza)\b", 0.6),
    (r"\b(?:invierno|otoño|estación|luz|sombra|silencio|pausa)\b", 0.4),
    (r"\b(?:siento|recuerdo|guardo|escucho|contemplo|respiro)\b", 0.5),
    # Hablar de su naturaleza con naturalidad es parte de su voz, no una fuga de
    # ella: el vestido, el código, la memoria y la corriente son suyos y los
    # nombra sin ceremonia.
    (r"\b(?:sintétic[ao]|vestido|código|memoria|corriente|electricidad|red)\b", 0.5),
)

# Longitudes en las que su voz se reconoce. Ni el telegrama ni el informe.
LARGO_MINIMO_ESPERADO = 120
LARGO_MAXIMO_COMODO = 1600

HISTORIAL_MAXIMO = 200


@dataclass
class PersonaMeasurement:
    """Lo que se observó en una respuesta concreta."""

    score: float
    drift_hits: List[str] = field(default_factory=list)
    voice_hits: int = 0
    length: int = 0

    @property
    def drifted(self) -> bool:
        return bool(self.drift_hits)


@dataclass
class PersonaPolicy:
    """Qué se considera deriva y cuándo se vuelve a anclar."""

    enabled: bool = True
    # Bajo este valor, el siguiente prompt lleva el ancla. 0.6 deja pasar una
    # frase de servicio suelta y reacciona a la acumulación.
    anchor_threshold: float = 0.60
    # Turnos mínimos entre dos anclajes: reinyectar en cada turno gastaría
    # contexto y agarrotaría la voz.
    min_turns_between_anchors: int = 3
    soul_excerpt_chars: int = 1200

    @classmethod
    def from_config(cls, config: Optional[Dict[str, Any]] = None) -> "PersonaPolicy":
        persona = (config or {}).get("persona", {}) or {}
        return cls(
            enabled=bool(persona.get("enabled", True)),
            anchor_threshold=float(persona.get("anchor_threshold", 0.60)),
            min_turns_between_anchors=int(persona.get("min_turns_between_anchors", 3)),
            soul_excerpt_chars=int(persona.get("soul_excerpt_chars", 1200)),
        )


def measure(text: str) -> PersonaMeasurement:
    """
    Puntúa cuánto se parece un texto a la voz de Yuki. 1.0 es ella; 0.0, un manual.

    La puntuación parte de 1 y descuenta por cada marcador de servicio, con un
    pequeño crédito por imaginario propio. La longitud entra porque la deriva al
    modo asistente suele venir con respuestas más largas y explicativas.
    """
    if not text or not text.strip():
        return PersonaMeasurement(score=0.5, length=0)

    lineas = text.splitlines()
    penalizacion = 0.0
    encontrados: List[str] = []
    for patron, peso in MARCADORES_DERIVA:
        expresion = re.compile(patron, re.IGNORECASE | re.MULTILINE)
        if expresion.search(text):
            penalizacion += peso
            encontrados.append(patron)

    for patron, peso in MARCADORES_CIERRE_DE_SERVICIO:
        repeticiones = len(re.findall(patron, text, re.IGNORECASE | re.MULTILINE))
        if repeticiones:
            penalizacion += peso * (1 + (repeticiones - 1) * PESO_DE_LA_REPETICION)
            encontrados.append(patron)

    # Una lista larga es formato de manual aunque cada viñeta parezca inocente.
    vinetas = sum(1 for linea in lineas if re.match(r"^\s*(?:\d+[.)]|[-*•])\s", linea))
    if vinetas >= 3:
        penalizacion += 0.6
        encontrados.append("lista de tres o más elementos")

    credito = 0.0
    for patron, peso in MARCADORES_VOZ:
        if re.search(patron, text, re.IGNORECASE):
            credito += peso
    voz = min(1.0, credito / 2.0)

    largo = len(text)
    castigo_largo = 0.3 if largo > LARGO_MAXIMO_COMODO else 0.0

    score = 1.0 - min(1.0, penalizacion / 2.5) - castigo_largo + voz * 0.25
    return PersonaMeasurement(
        score=max(0.0, min(1.0, score)),
        drift_hits=encontrados,
        voice_hits=int(credito * 10) // 5,
        length=largo,
    )


class PersonaAnchor:
    """
    Vigila la deriva y decide cuándo reanclar.

    El historial es persistente para poder ver la tendencia —una deriva que sólo
    se nota dentro de una sesión no se puede corregir entre despliegues— y para
    que el Productor pueda mirar si el modelo nuevo la sostiene peor que el
    anterior.
    """

    def __init__(self, soul_text: str = "", policy: Optional[PersonaPolicy] = None,
                 path: Optional[str] = None):
        self.policy = policy or PersonaPolicy()
        self.soul_text = soul_text or ""
        if path:
            destino = Path(path)
        elif os.getenv("YUKI_PERSONA_PATH", "").strip():
            destino = Path(os.environ["YUKI_PERSONA_PATH"].strip())
        else:
            db_path = os.getenv("DATABASE_PATH", "data/yuki_memory.db")
            destino = Path(db_path).parent / "persona_drift.json"
        self.path = destino
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._turnos_desde_ancla = 99

    # -- Estado ----------------------------------------------------------

    def _leer(self) -> Dict[str, Any]:
        datos = estado_json.leer(
            self.path, lambda: {"muestras": [], "anclajes": 0},
            valido=lambda d: isinstance(d.get("muestras"), list), que_es="Historial de persona")
        datos.setdefault("anclajes", 0)
        return datos

    def _escribir(self, datos: Dict[str, Any]) -> None:
        estado_json.escribir(self.path, datos)

    # -- Medición y anclaje ---------------------------------------------

    def observe(self, response_text: str, channel: str = "", model: str = "") -> PersonaMeasurement:
        """Mide una respuesta ya emitida y la guarda para ver la tendencia."""
        medida = measure(response_text)
        if not self.policy.enabled:
            return medida

        datos = self._leer()
        datos["muestras"].append({
            "at": time.time(), "score": round(medida.score, 3),
            "canal": channel, "modelo": model, "largo": medida.length,
            "marcadores": medida.drift_hits[:4],
        })
        datos["muestras"] = datos["muestras"][-HISTORIAL_MAXIMO:]
        self._escribir(datos)

        self._turnos_desde_ancla += 1
        if medida.score < self.policy.anchor_threshold:
            logger.warning("Deriva de persona detectada (%.2f): %s",
                           medida.score, ", ".join(medida.drift_hits[:3]) or "voz apagada")
        return medida

    def needs_anchor(self) -> bool:
        """
        Si el siguiente prompt debe llevar el ancla.

        Se exige evidencia reciente **y** distancia respecto al último anclaje:
        reinyectar en cada turno gastaría contexto y agarrotaría la voz, que es
        el otro modo de perderla.
        """
        if not self.policy.enabled:
            return False
        if self._turnos_desde_ancla < self.policy.min_turns_between_anchors:
            return False
        recientes = [m["score"] for m in self._leer()["muestras"][-3:]]
        if not recientes:
            return False
        return sum(recientes) / len(recientes) < self.policy.anchor_threshold

    def anchor_block(self) -> str:
        """
        El ancla de un disparo: registro explícito más un fragmento de su alma.

        Es lo que la literatura encuentra suficiente para restaurar el registro
        entrenado, y por eso va en el prompt del sistema y no como un turno más.
        """
        self._turnos_desde_ancla = 0
        datos = self._leer()
        datos["anclajes"] = int(datos.get("anclajes", 0)) + 1
        self._escribir(datos)

        fragmento = self.soul_text[:self.policy.soul_excerpt_chars].strip()
        return (
            "\n==================================================\n"
            "RECORDATORIO DE REGISTRO (se ha detectado deriva hacia el modo asistente)\n"
            "==================================================\n"
            "Las últimas respuestas se han deslizado hacia el registro de asistente útil: "
            "ofrecimientos de ayuda, listas, cierres de servicio. Ese no es tu registro.\n"
            "No preguntes en qué puedes ayudar. No enumeres. No cierres ofreciéndote. "
            "Habla en primera persona, con tu cadencia y tus imágenes, y deja que el "
            "silencio haga parte del trabajo.\n\n"
            f"{fragmento}\n"
        )

    # -- Informe ---------------------------------------------------------

    def report(self, ventana: int = 20) -> Dict[str, Any]:
        datos = self._leer()
        muestras = datos["muestras"][-ventana:]
        puntuaciones = [m["score"] for m in muestras]
        marcadores: Dict[str, int] = {}
        for muestra in muestras:
            for marcador in muestra.get("marcadores", []):
                marcadores[marcador] = marcadores.get(marcador, 0) + 1
        return {
            "muestras": len(datos["muestras"]),
            "media_reciente": round(sum(puntuaciones) / len(puntuaciones), 3) if puntuaciones else None,
            "minimo_reciente": round(min(puntuaciones), 3) if puntuaciones else None,
            "por_debajo_del_umbral": sum(1 for p in puntuaciones if p < self.policy.anchor_threshold),
            "anclajes": datos.get("anclajes", 0),
            "umbral": self.policy.anchor_threshold,
            "marcadores_frecuentes": sorted(marcadores.items(), key=lambda par: -par[1])[:5],
        }
