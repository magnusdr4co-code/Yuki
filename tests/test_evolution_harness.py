"""
Pruebas del arnés de evolución.

Es el único módulo que puede **cambiar la configuración de Yuki sin que nadie se
lo pida**, y estaba cubierto al 17%. Lo que se prueba aquí no es que funcione
—eso es lo de menos— sino que sus barandillas aguanten: que no se ajuste sin
evidencia, que no se salte el límite de variación, que Model Armor pueda vetarlo
en tres puntos distintos y que una respuesta rara del modelo no acabe en un
cambio de configuración.

Un módulo que se concede permisos a sí mismo tiene que fallar hacia el lado
seguro siempre, y eso sólo se sabe rompiéndolo a propósito.
"""

import asyncio
import os
import sys
import types
from typing import Any, Dict, List

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.evolution_harness import EvolutionHarness  # noqa: E402


class ArmorPermisivo:
    def sanitize_user_prompt(self, texto):
        return types.SimpleNamespace(allowed=True, text=texto)

    def sanitize_model_response(self, texto, user_prompt=""):
        return types.SimpleNamespace(allowed=True, text=texto)


class ArmorQueVeta:
    """Veta en el punto que se le diga: prompt, respuesta o argumentos."""

    def __init__(self, veta_en: str):
        self.veta_en = veta_en
        self.prompts_vistos = 0

    def sanitize_user_prompt(self, texto):
        self.prompts_vistos += 1
        # El primer prompt es el de revisión de crecimiento; el segundo, el de
        # ajuste; el tercero, los argumentos de la herramienta.
        veta = ((self.veta_en == "crecimiento" and self.prompts_vistos == 1)
                or (self.veta_en == "revision" and self.prompts_vistos == 2)
                or (self.veta_en == "argumentos" and self.prompts_vistos == 3))
        return types.SimpleNamespace(allowed=not veta, text=texto)

    def sanitize_model_response(self, texto, user_prompt=""):
        return types.SimpleNamespace(allowed=self.veta_en != "respuesta", text=texto)


class MotorFalso:
    def __init__(self, eventos: List[Dict[str, Any]]):
        self._eventos = eventos

    def get_recent_growth(self, limit=5):
        return self._eventos[:limit]


class DiarioFalso:
    def __init__(self, eventos, parseados=()):
        self.engine = MotorFalso(eventos)
        self._parseados = list(parseados)
        self.registrados = []

    def generate_review_prompt(self):
        return "revisa el crecimiento"

    def parse_llm_growth_response(self, texto):
        return self._parseados

    def record_growth_event(self, dominio, desde, hasta, disparadores, confianza):
        self.registrados.append((dominio, desde, hasta, confianza))


def _agente(*, eventos=(), parseados=(), armor=None, turno=None, interacciones=10,
            evolucion=None, valores=None):
    reconfiguraciones = []

    agente = types.SimpleNamespace(
        config={"runtime_harness": {"self_evolution": evolucion if evolucion is not None
                                    else {"enabled": True, "min_interactions": 5,
                                          "min_confidence": 0.80, "max_temperature_delta": 0.15}}},
        vital_state=types.SimpleNamespace(accumulated_interactions_today=interacciones),
        growth_journal=DiarioFalso(list(eventos), parseados),
        model_armor=armor or ArmorPermisivo(),
        llm_router=types.SimpleNamespace(generate_with_tools=lambda mensajes, herramientas: turno or {}),
        _call_llm_inference=lambda sistema, usuario, ruta=None: "análisis de crecimiento",
        runtime_config_get=lambda: {"values": valores or {"agent.model.temperature": 0.72}},
    )
    agente.reconfigure_runtime = lambda ruta, valor, actor="", reason="": (
        reconfiguraciones.append((ruta, valor, actor, reason))
        or {"path": ruta, "value": valor})
    agente.reconfiguraciones = reconfiguraciones
    return agente


def _llamada(argumentos: str, nombre: str = "adjust_runtime_temperature"):
    return {"tool_calls": [{"function": {"name": nombre, "arguments": argumentos}}]}


EVENTO_SOLIDO = {"domain": "music", "from_position": "shamisen puro",
                 "to_position": "shamisen con sub-bajo", "confidence": 0.9}


# --- Barandillas previas ---

def test_desactivado_no_toca_nada():
    agente = _agente(evolucion={"enabled": False})

    resultado = asyncio.run(EvolutionHarness(agente).review_and_adjust())

    assert resultado == {"changed": False, "reason": "disabled"}
    assert agente.reconfiguraciones == []


def test_sin_interacciones_suficientes_no_se_evoluciona():
    """Un día en silencio no es evidencia de nada."""
    agente = _agente(interacciones=2)

    resultado = asyncio.run(EvolutionHarness(agente).review_and_adjust())

    assert resultado["reason"] == "insufficient_interactions"


def test_sin_crecimiento_verificado_no_hay_ajuste():
    agente = _agente(eventos=[])

    resultado = asyncio.run(EvolutionHarness(agente).review_and_adjust())

    assert resultado["reason"] == "no_verified_growth"
    assert agente.reconfiguraciones == []


def test_el_crecimiento_poco_seguro_no_cuenta():
    """Por debajo del umbral de confianza, un hallazgo es una impresión."""
    agente = _agente(eventos=[{**EVENTO_SOLIDO, "confidence": 0.4}])

    resultado = asyncio.run(EvolutionHarness(agente).review_and_adjust())

    assert resultado["reason"] == "no_verified_growth"


# --- Model Armor puede vetar en tres puntos ---

@pytest.mark.parametrize("punto,motivo", [
    ("revision", "armor_rejected_review"),
    ("argumentos", "armor_rejected_arguments"),
])
def test_el_arnes_de_seguridad_puede_vetar(punto, motivo):
    agente = _agente(eventos=[EVENTO_SOLIDO], armor=ArmorQueVeta(punto),
                     turno=_llamada('{"path": "agent.model.temperature", "value": 0.8, '
                                    '"reason": "más audacia"}'))

    resultado = asyncio.run(EvolutionHarness(agente).review_and_adjust())

    assert resultado["reason"] == motivo
    assert agente.reconfiguraciones == []


def test_una_respuesta_vetada_no_registra_crecimiento():
    agente = _agente(eventos=[EVENTO_SOLIDO], armor=ArmorQueVeta("respuesta"),
                     parseados=[{"domain": "music", "from_position": "a",
                                 "to_position": "b", "confidence": 0.95}])

    asyncio.run(EvolutionHarness(agente).review_and_adjust())

    assert agente.growth_journal.registrados == []


# --- Lo que el modelo devuelve no manda ---

def test_sin_llamada_a_la_herramienta_no_pasa_nada():
    agente = _agente(eventos=[EVENTO_SOLIDO], turno={"content": "creo que deberías subirla"})

    resultado = asyncio.run(EvolutionHarness(agente).review_and_adjust())

    assert resultado["reason"] == "no_safe_adjustment"
    assert agente.reconfiguraciones == []


def test_dos_llamadas_a_la_vez_se_rechazan():
    """Un turno con varias herramientas es un turno que no se entiende."""
    turno = {"tool_calls": [
        {"function": {"name": "adjust_runtime_temperature", "arguments": "{}"}},
        {"function": {"name": "adjust_runtime_temperature", "arguments": "{}"}},
    ]}
    agente = _agente(eventos=[EVENTO_SOLIDO], turno=turno)

    assert asyncio.run(EvolutionHarness(agente).review_and_adjust())["reason"] == "no_safe_adjustment"


def test_otra_herramienta_no_cuela():
    agente = _agente(eventos=[EVENTO_SOLIDO],
                     turno=_llamada('{"path": "x", "value": 1}', nombre="borrar_memoria"))

    assert asyncio.run(EvolutionHarness(agente).review_and_adjust())["reason"] == "no_safe_adjustment"


def test_argumentos_ilegibles_no_acaban_en_un_cambio():
    agente = _agente(eventos=[EVENTO_SOLIDO], turno=_llamada("{esto no es json"))

    resultado = asyncio.run(EvolutionHarness(agente).review_and_adjust())

    assert resultado["reason"] == "invalid_adjustment"
    assert agente.reconfiguraciones == []


# --- El límite de variación ---

def test_un_salto_mayor_del_permitido_se_rechaza():
    """0.72 → 1.40 sería otra Yuki, no una evolución."""
    agente = _agente(eventos=[EVENTO_SOLIDO],
                     turno=_llamada('{"path": "agent.model.temperature", "value": 1.4, '
                                    '"reason": "mucha más audacia"}'))

    resultado = asyncio.run(EvolutionHarness(agente).review_and_adjust())

    assert resultado["reason"] == "delta_exceeds_limit"
    assert agente.reconfiguraciones == []


def test_un_ajuste_prudente_con_evidencia_si_se_aplica():
    agente = _agente(eventos=[EVENTO_SOLIDO],
                     turno=_llamada('{"path": "agent.model.temperature", "value": 0.80, '
                                    '"reason": "el crecimiento musical pide algo más de riesgo"}'))

    resultado = asyncio.run(EvolutionHarness(agente).review_and_adjust())

    assert resultado["changed"] is True
    assert agente.reconfiguraciones == [
        ("agent.model.temperature", 0.80, "evolution",
         "el crecimiento musical pide algo más de riesgo")]


def test_el_ajuste_se_atribuye_a_la_evolucion_y_no_al_productor():
    """La autoría importa: el overlay limita a la evolución más que al Productor."""
    agente = _agente(eventos=[EVENTO_SOLIDO],
                     turno=_llamada('{"path": "agent.model.temperature", "value": 0.75, '
                                    '"reason": "leve"}'))

    asyncio.run(EvolutionHarness(agente).review_and_adjust())

    assert agente.reconfiguraciones[0][2] == "evolution"


# --- Registro de crecimiento ---

def test_solo_se_registran_dominios_conocidos_y_seguros():
    parseados = [
        {"domain": "music", "from_position": "a", "to_position": "b", "confidence": 0.95},
        {"domain": "hackear", "from_position": "a", "to_position": "b", "confidence": 0.99},
        {"domain": "aesthetics", "from_position": "c", "to_position": "d", "confidence": 0.5},
    ]
    agente = _agente(eventos=[EVENTO_SOLIDO], parseados=parseados,
                     turno={"content": "sin cambios"})

    asyncio.run(EvolutionHarness(agente).review_and_adjust())

    registrados = agente.growth_journal.registrados
    assert [r[0] for r in registrados] == ["music"], "ni dominio inventado ni baja confianza"


def test_no_se_duplica_un_crecimiento_ya_registrado():
    repetido = {"domain": "music", "from_position": "shamisen puro",
                "to_position": "shamisen con sub-bajo", "confidence": 0.95}
    agente = _agente(eventos=[EVENTO_SOLIDO], parseados=[repetido],
                     turno={"content": "sin cambios"})

    asyncio.run(EvolutionHarness(agente).review_and_adjust())

    assert agente.growth_journal.registrados == []
