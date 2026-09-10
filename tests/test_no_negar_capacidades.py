"""
Yuki no puede negar lo que sabe hacer.

A1 del incidente del 9 de septiembre: le pidieron que se apuntara tareas y
contestó «no tengo un motor en segundo plano… ni puedo tejer crons invisibles»
con ocho rutinas declaradas, un daemon 24/7 y la facultad de proponer ritmos
propios **y ajustarlos**. No fue modestia ni cautela: en su prompt no había una
sola línea que dijera de qué es capaz, así que lo dedujo, y dedujo mal.

Estas pruebas recorren el camino del producto —el prompt que sale hacia el
modelo— y no la clase suelta: el bloque puede existir y no llegar, que es
exactamente cómo un arreglo así se queda en nada.
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.agent import YukiAgent  # noqa: E402
from src.core.virtual_instance import VirtualInstance, REAL, SIMULADO  # noqa: E402


class RelojFijo:
    def __init__(self, phase="atelier"):
        self.phase = phase

    def current_phase(self, dt=None) -> str:
        return self.phase

    def is_responsive(self, dt=None) -> bool:
        return True


def _prompt_de_un_turno(mensaje="apúntate tareas y crons para el mes"):
    """Devuelve el prompt del sistema que de verdad viaja al modelo."""
    agente = YukiAgent()
    reloj = RelojFijo()
    agente.circadian = reloj
    agente.presence_controller.circadian_clock = reloj
    capturado = {}

    def _falso_llm(system_prompt, user_message, route):
        capturado["prompt"] = system_prompt
        return "De acuerdo."

    agente._call_llm_inference = _falso_llm
    asyncio.run(agente.generate_response(
        user_id="producer_manager", user_name="Productor", message=mensaje,
    ))
    return capturado.get("prompt", "")


def test_el_prompt_le_dice_de_que_es_capaz():
    prompt = _prompt_de_un_turno()
    assert "CAPACIDADES EFECTIVAS DE ESTA INSTANCIA" in prompt, \
        "el bloque puede existir y no llegar al modelo; entonces no sirve de nada"
    assert "mente.ritmos" in prompt, "los ritmos propios son justo lo que negó tener"
    assert "presencia.cron" in prompt


def test_el_prompt_le_prohibe_negar_lo_real():
    """Listar capacidades sin decir qué hacer con la lista no corrige nada."""
    prompt = _prompt_de_un_turno()
    assert "No niegues" in prompt


def test_lo_simulado_y_lo_inactivo_tambien_se_listan():
    """
    Dar sólo lo real invitaría al vicio contrario —prometer lo que no hay—,
    que es el que este proyecto lleva años corrigiendo.
    """
    bloque = VirtualInstance().bloque_de_capacidades()
    instancia = VirtualInstance()
    simuladas = [c for c in instancia.capabilities if c.state == SIMULADO]
    reales = [c for c in instancia.capabilities if c.state == REAL]
    assert reales and simuladas, "el entorno de pruebas debería tener de ambas"
    assert all(c.id in bloque for c in simuladas), "una capacidad simulada omitida se presta a prometerla"


def test_ninguna_capacidad_se_pierde_por_un_detalle_largo():
    """
    Ya pasó: un detalle más explicativo empujó el bloque por encima del tope y
    el recorte se llevó la cola —que es justo «lo que no puedes y por qué»—.
    Se recorta cada detalle, no la lista, para que añadir texto a uno no borre
    otro en silencio.
    """
    instancia = VirtualInstance()
    bloque = instancia.bloque_de_capacidades()

    faltan = [c.id for c in instancia.capabilities if c.id not in bloque]
    assert not faltan, f"el bloque se dejó fuera: {faltan}"
    assert "recortada por longitud" not in bloque, \
        "con los detalles ya acotados, el tope global no debería llegar a actuar"


def test_un_recorte_conserva_la_instruccion():
    """El cierre es la instrucción, no el relleno: sobrevive al recorte por longitud."""
    bloque = VirtualInstance().bloque_de_capacidades(maximo=200)
    assert "recortada por longitud" in bloque, "un recorte silencioso deja una lista que parece completa"
    assert bloque.rstrip().endswith("en vez de negar la facultad.")


def test_la_lectura_de_capacidades_se_cachea_entre_turnos():
    """Se construye leyendo config, presupuesto y binarios; no cabe hacerlo por mensaje."""
    import src.core.virtual_instance as vi

    agente = YukiAgent()
    construcciones = []
    original = vi.VirtualInstance

    class Contada(original):
        def __init__(self, *args, **kwargs):
            construcciones.append(1)
            super().__init__(*args, **kwargs)

    vi.VirtualInstance = Contada
    try:
        agente._capacidades_cache = (0.0, "")
        lecturas = [agente.capability_block() for _ in range(4)]
    finally:
        vi.VirtualInstance = original

    assert len(construcciones) == 1, "una lectura por mensaje sale cara en una e2-small"
    assert len(set(lecturas)) == 1


def test_un_ajuste_en_caliente_invalida_la_lectura():
    """Encender o apagar algo por DM no puede dejar el bloque contando lo de antes."""
    agente = YukiAgent()
    agente.capability_block()
    assert agente._capacidades_cache[0] > 0
    agente._reload_runtime_clients()
    assert agente._capacidades_cache == (0.0, ""), \
        "tras recargar la configuración el bloque tiene que releerse"


def test_describirse_mal_no_la_deja_muda():
    """Quedarse sin responder por no poder describirse sería peor que no describirse."""
    agente = YukiAgent()

    class InstanciaRota:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("config ilegible")

    import src.core.virtual_instance as vi
    original = vi.VirtualInstance
    vi.VirtualInstance = InstanciaRota
    try:
        agente._capacidades_cache = (0.0, "")
        assert agente.capability_block() == ""
    finally:
        vi.VirtualInstance = original


if __name__ == "__main__":
    pytest.main([__file__])
