import sys
import os
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.core.inner_monologue import InnerMonologue

@pytest.fixture
def monologue():
    return InnerMonologue(memory_manager=MagicMock(), vital_state=MagicMock())

def test_should_think_true(monologue):
    monologue.vital_state.vulnerability = 0.6
    monologue.vital_state.curiosity = 0.5
    monologue.vital_state.energy = 0.3
    assert monologue.should_think() is True

def test_should_think_false_low_sum(monologue):
    monologue.vital_state.vulnerability = 0.4
    monologue.vital_state.curiosity = 0.4
    monologue.vital_state.energy = 0.3
    assert monologue.should_think() is False

def test_should_think_false_low_energy(monologue):
    monologue.vital_state.vulnerability = 0.6
    monologue.vital_state.curiosity = 0.6
    monologue.vital_state.energy = 0.1
    assert monologue.should_think() is False

@patch('src.core.inner_monologue.get_current_micro_season' if 'get_current_micro_season' in sys.modules else 'src.core.seasons.get_current_micro_season')
def test_generate_thought_prompt_contains_season(mock_season, monologue):
    mock_season.return_value = {"poetic_context": "Winter cold"}
    monologue.vital_state.vulnerability = 0.5
    monologue.vital_state.curiosity = 0.5
    monologue.vital_state.energy = 0.5
    monologue.memory_manager.engine.get_recent_inner_thoughts.return_value = []
    
    prompt = monologue.generate_thought_prompt()
    assert "Winter cold" in prompt

def test_record_thought_increases_inspiration(monologue):
    monologue.vital_state.inspiration = 0.5
    monologue.get_inspiration_fuel = MagicMock(return_value=0.05)
    monologue.record_thought("I am thinking.")
    assert monologue.vital_state.inspiration == 0.55

def test_get_inspiration_fuel_range(monologue):
    fuel = monologue.get_inspiration_fuel()
    assert 0.03 <= fuel <= 0.08
