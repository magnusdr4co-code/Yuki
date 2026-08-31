import sys
import os
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
