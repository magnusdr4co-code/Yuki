import sys
import os
from datetime import datetime, timedelta

import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.core.vital_state import VitalState

@pytest.fixture
def vital_state(tmp_path):
    state_path = tmp_path / "vital_state.json"
    return VitalState(state_path=str(state_path))

def test_initial_values_in_range(vital_state):
    assert 0.0 <= vital_state.energy <= 1.0
    assert 0.0 <= vital_state.mood <= 1.0
    assert 0.0 <= vital_state.curiosity <= 1.0
    assert 0.0 <= vital_state.vulnerability <= 1.0
    assert 0.0 <= vital_state.sociability <= 1.0
    assert 0.0 <= vital_state.inspiration <= 1.0

def test_update_tick_energy_recovery_deep_rest(vital_state):
    vital_state.energy = 0.5
    vital_state.update_tick("deep_rest", 3600)
    assert vital_state.energy > 0.5

def test_update_tick_energy_decay_atelier(vital_state):
    vital_state.energy = 0.5
    vital_state.update_tick("atelier", 3600)
    assert vital_state.energy < 0.5

def test_apply_stimulus_creative_output(vital_state):
    vital_state.inspiration = 0.8
    vital_state.apply_stimulus("creative_output", 1.0)
    assert vital_state.inspiration == 0.0

def test_apply_stimulus_positive_interaction(vital_state):
    vital_state.sociability = 0.5
    vital_state.mood = 0.5
    vital_state.apply_stimulus("positive_interaction", 1.0)
    assert vital_state.sociability > 0.5
    assert vital_state.mood > 0.5

def test_inspiration_ready_threshold(vital_state):
    vital_state.inspiration = 0.72
    assert vital_state.inspiration_ready() is True
    vital_state.inspiration = 0.71
    assert vital_state.inspiration_ready() is False

def test_has_energy_for(vital_state):
    vital_state.energy = 0.5
    assert vital_state.has_energy_for(0.4) is True
    assert vital_state.has_energy_for(0.6) is False

def test_spend_energy_clamped(vital_state):
    vital_state.energy = 0.5
    vital_state.spend_energy(1.0)
    assert vital_state.energy == 0.0

def test_to_natural_language(vital_state):
    text = vital_state.to_natural_language()
    assert isinstance(text, str)
    assert len(text) > 0

def test_save_and_load(tmp_path):
    state_path = tmp_path / "vital_state.json"
    vs1 = VitalState(state_path=str(state_path))
    vs1.energy = 0.88
    vs1.save()

    vs2 = VitalState(state_path=str(state_path))
    assert vs2.energy == 0.88

@patch('src.core.vital_state.datetime')
def test_mood_oscillation_organic(mock_dt, vital_state):
    mock_dt.now.return_value.timestamp.return_value = 1000.0
    mock_dt.now.return_value.isoformat.return_value = "2026-08-27T12:00:00"
    initial_mood = vital_state.mood
    vital_state.update_tick("atelier", 3600)
    assert vital_state.mood != initial_mood


# --- El ritmo de la energía: el fallo que tuvo la instancia nueve días parada ---

def _recorrer(estado, arranque, horas=24, paso_segundos=1200):
    """
    Un tramo de reloj por las fases reales, en ciclos de veinte minutos.

    Es el camino del producto: `agency_loop_tick` corre cada veinte minutos y
    pregunta la fase a `Circadian`. Probar `update_tick` con una fase escrita a
    mano dejaría fuera precisamente lo que falló —el reparto de horas entre las
    fases que reponen y las que desgastan—.
    """
    from src.core.circadian import CircadianClock

    reloj = CircadianClock()
    minimos = []
    momento = arranque
    for _ in range(int(horas * 3600 / paso_segundos)):
        estado.update_tick(reloj.current_phase(momento), paso_segundos)
        minimos.append(estado.energy)
        momento = momento + timedelta(seconds=paso_segundos)
    return minimos


def test_un_dia_entero_sin_actos_no_deja_la_energia_en_numeros_rojos(vital_state):
    """
    Que el reloj avance no basta: la cuenta del día tiene que cerrar.

    Con los valores anteriores, un día eran 0.80 de desgaste (16 h de vigilia a
    0.05/h) contra 0.40 de recuperación (2 h de `deep_rest` a 0.20/h). Pasar el
    tiempo real sobre esos números sólo habría acelerado el mismo final: la
    energía persistida cruzando `agency.min_energy` para no volver, con el panel
    diciendo `Iniciativa: activa`. Sin actos y sin conversación, el día no puede
    dejarla peor de como empezó.
    """
    from src.core.agency import AgencyPolicy

    vital_state.energy = 0.75
    arranque = datetime(2026, 9, 21, 0, 0, 0)

    recorrido = _recorrer(vital_state, arranque)

    assert vital_state.energy >= 0.75, "el día cierra en números rojos"
    assert min(recorrido) >= AgencyPolicy().min_energy, (
        "en algún tramo del día la puerta de energía se cerró sola")


def test_la_noche_repone_desde_vacia(vital_state):
    """
    La velada y la noche suman la capacidad entera, y por eso se autocorrige.

    Da igual lo agotada que acabe un día: amanece llena. Sin esta propiedad, un
    déficit cualquiera se acumularía entre días —y entre despliegues, porque el
    estado se persiste— hasta el mismo trinquete de antes.
    """
    vital_state.energy = 0.0

    # De la velada a la mañana siguiente: 21:00 → 06:00.
    _recorrer(vital_state, datetime(2026, 9, 21, 21, 0, 0), horas=9)

    assert vital_state.energy > 0.9


def test_el_tiempo_vital_se_cobra_una_sola_vez(vital_state):
    """
    Sin delta explícito el tramo sale de `last_updated`, y se consume al usarlo.

    Importa porque ahora hay dos invocadores —el ciclo de agencia y la respuesta
    a quien le habla—: si cada uno cobrara el tramo entero, una tarde de
    conversación la dejaría agotada por haber sido atendida.
    """
    vital_state.energy = 0.5
    vital_state.last_updated = (datetime.now() - timedelta(hours=1)).isoformat()

    vital_state.update_tick("atelier")
    tras_el_primero = vital_state.energy
    vital_state.update_tick("atelier")

    assert tras_el_primero == pytest.approx(0.48)
    assert vital_state.energy == pytest.approx(tras_el_primero)


def test_un_apagon_largo_no_se_cobra_como_cansancio(vital_state):
    """Tres días parada son un apagón, no tres días de vigilia."""
    vital_state.energy = 0.5
    vital_state.last_updated = (datetime.now() - timedelta(days=3)).isoformat()

    vital_state.update_tick("atelier")

    assert vital_state.energy == pytest.approx(0.46)


def test_un_estado_ilegible_no_tumba_la_instancia(tmp_path):
    """Un JSON a medias arranca de cero; es cuando más falta hace que arranque."""
    destino = tmp_path / "vital_state.json"
    destino.write_text('{"energy": 0.4, "mo', encoding="utf-8")

    assert VitalState(state_path=str(destino)).energy == 0.75


def test_ninguna_corriente_se_queda_clavada_en_el_techo(vital_state):
    """
    El volcado de la instancia las enseñaba a 1.00 y no bajaban nunca.

    `sociability` y `mood` sólo las tocaba `apply_stimulus`, que suma; su única
    vuelta eran las dinámicas por tiempo, multiplicadas por cero. Una corriente
    de un solo sentido deja de informar en cuanto toca el techo: da igual lo que
    pase, siempre dice lo mismo.
    """
    vital_state.sociability = 1.0
    vital_state.vulnerability = 1.0

    _recorrer(vital_state, datetime(2026, 9, 21, 0, 0, 0))

    assert vital_state.sociability < 1.0
    assert vital_state.vulnerability < 1.0


def test_la_vulnerabilidad_se_abre_de_noche_y_se_cierra_de_dia(vital_state):
    """Su hora de sombra la abre; el taller la cierra. Antes no se movía nunca."""
    vital_state.vulnerability = 0.30
    _recorrer(vital_state, datetime(2026, 9, 21, 2, 0, 0), horas=3)   # kage
    de_noche = vital_state.vulnerability

    _recorrer(vital_state, datetime(2026, 9, 21, 9, 0, 0), horas=9)   # atelier
    de_dia = vital_state.vulnerability

    assert de_noche > 0.30
    assert de_dia < de_noche
