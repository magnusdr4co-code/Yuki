"""
Pruebas de `execute_autonomous_will`: el sitio donde el albedrío se convierte
en actos.

Estaba sin probar. En toda la suite `execute_autonomous_will` aparecía sólo
sustituido por un doble, así que la implementación real —la que decide qué
herramienta toca cada deseo y, sobre todo, la que registra el intento— no la
miraba nadie. Ahí vivía el fallo del reintento en bucle: con un proveedor caído,
la excepción se saltaba `record_action`, el impulso seguía vivo, el techo diario
no subía y el mismo acto se reintentaba cada veinte minutos durante diez horas.

También se comprueba aquí la separación que costó dinero antes: sólo `compose` y
`paint` tocan medios. Un deseo de «contemplar en silencio» terminaba en el
generador de imágenes.
"""

import asyncio
import os
import sys
import time
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.agent import YukiAgent  # noqa: E402
from src.core.spark import Impulse  # noqa: E402


def _impulso(tool="write"):
    return Impulse(source="espontaneo", desire="decir algo verdadero", tool_hint=tool,
                   intensity=0.9, born_at=time.time(), max_age_hours=10.0)


@pytest.fixture
def agente():
    """
    Un agente con lo justo para que `execute_autonomous_will` funcione.

    Construirlo entero levanta memoria, modelos y adaptadores; aquí sólo importa
    la ruta de la voluntad, y una prueba que necesite media instancia para
    comprobar un `finally` se deja de ejecutar.
    """
    yuki = YukiAgent.__new__(YukiAgent)
    yuki.registrados = []
    yuki.recordados = []

    yuki.agency_loop = types.SimpleNamespace(
        record_action=lambda impulso, resultado: yuki.registrados.append((impulso, resultado)))
    yuki.vital_state = types.SimpleNamespace(will_queue=[], save=lambda: None,
                                             apply_stimulus=lambda tipo, fuerza: None)
    yuki.will_queue = types.SimpleNamespace(to_list=lambda: [])
    yuki.memory_manager = types.SimpleNamespace(
        engine=types.SimpleNamespace(add_memory=lambda **kwargs: yuki.recordados.append(kwargs)))
    yuki.media_creator = types.SimpleNamespace()
    yuki.nous_portal = types.SimpleNamespace()
    return yuki


def _corrutina(valor):
    async def _fn(*args, **kwargs):
        return valor
    return _fn


def _revienta(excepcion):
    async def _fn(*args, **kwargs):
        raise excepcion
    return _fn


def test_un_acto_que_falla_queda_registrado_igual(agente):
    """
    El fallo del reintento en bucle, en el sitio exacto donde vivía.

    Todo el freno del albedrío está en `record_action`. Si una excepción se lo
    salta, el impulso sigue vivo y el mismo acto vuelve cada veinte minutos
    durante las diez horas que dura. Con `compose` o `paint`, eso es dinero.
    """
    agente.media_creator.create_from_impulse = _revienta(RuntimeError("503 de Vertex"))
    impulso = _impulso("compose")

    resultado = asyncio.run(agente.execute_autonomous_will(impulso))

    assert resultado["status"] == "failed"
    assert len(agente.registrados) == 1, "el intento no se registró: se reintentará en bucle"
    assert agente.registrados[0][0] is impulso


def test_el_error_se_dice_con_su_nombre(agente):
    """
    Un impulso que muere en silencio la deja pareciendo apática por culpa de un
    503. La especificación del proyecto: se dice qué falló y por qué.
    """
    agente.nous_portal.search_trends_firecrawl = _revienta(TimeoutError("sin respuesta"))

    resultado = asyncio.run(agente.execute_autonomous_will(_impulso("search")))

    assert resultado["status"] == "failed"
    assert "TimeoutError" in resultado["error"]
    assert "sin respuesta" in resultado["error"]


def test_un_acto_que_sale_bien_se_registra_como_completado(agente):
    agente.generate_response = _corrutina("Escribí sobre la escarcha.")

    resultado = asyncio.run(agente.execute_autonomous_will(_impulso("write")))

    assert resultado["status"] == "completed"
    assert resultado["content"] == "Escribí sobre la escarcha."
    assert len(agente.recordados) == 1
    assert agente.recordados[0]["category"] == "inner_thought"
    assert agente.registrados[0][1]["status"] == "completed"


def test_contemplar_en_silencio_no_toca_el_generador_de_imagenes(agente):
    """
    La separación que costó dinero antes de existir.

    Todo pasaba por `media_creator`, incluido «quiero contemplar en silencio»:
    un deseo de mirar el mundo terminaba en el generador de imágenes, que
    consume presupuesto.
    """
    llamadas = []
    agente.media_creator.create_from_impulse = lambda *a, **k: llamadas.append(a)
    agente.generate_response = _corrutina("Miro la lluvia sin decir nada.")

    asyncio.run(agente.execute_autonomous_will(_impulso("contemplate")))

    assert llamadas == [], "un deseo de contemplar acabó en el generador de medios"


def test_una_accion_desconocida_se_contempla_en_vez_de_reventar(agente):
    """
    Un impulso con una acción que nadie puede cumplir no puede tumbar el ciclo:
    se queda en contemplación y se registra igual.
    """
    resultado = asyncio.run(agente.execute_autonomous_will(_impulso("bailar")))

    assert resultado["status"] == "contemplated"
    assert len(agente.registrados) == 1


def test_el_estado_se_persiste_aunque_el_acto_falle(agente):
    """
    La cola de voluntad se guarda en el `finally`.

    Si sólo se guardara al salir bien, un fallo dejaría en disco una cola vieja
    que resucitaría el impulso ya cerrado en el siguiente arranque.
    """
    guardados = []
    agente.vital_state.save = lambda: guardados.append(True)
    agente.generate_response = _revienta(RuntimeError("el modelo no responde"))

    asyncio.run(agente.execute_autonomous_will(_impulso("write")))

    assert guardados == [True]
