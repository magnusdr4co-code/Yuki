import sys
import os
import pytest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.core.circadian import CircadianClock

@pytest.fixture
def clock():
    return CircadianClock(tz_name="UTC", jitter_minutes=0)

def test_current_phase_deep_rest(clock):
    dt = datetime(2026, 8, 27, 1, 0, tzinfo=timezone.utc)
    assert clock.current_phase(dt) == 'deep_rest'

def test_current_phase_kage(clock):
    dt = datetime(2026, 8, 27, 3, 0, tzinfo=timezone.utc)
    assert clock.current_phase(dt) == 'kage'

def test_current_phase_dawn(clock):
    dt = datetime(2026, 8, 27, 7, 0, tzinfo=timezone.utc)
    assert clock.current_phase(dt) == 'dawn'

def test_current_phase_atelier(clock):
    dt = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    assert clock.current_phase(dt) == 'atelier'

def test_current_phase_twilight(clock):
    dt = datetime(2026, 8, 27, 19, 0, tzinfo=timezone.utc)
    assert clock.current_phase(dt) == 'twilight'

def test_current_phase_consolidation(clock):
    dt = datetime(2026, 8, 27, 22, 0, tzinfo=timezone.utc)
    assert clock.current_phase(dt) == 'consolidation'

def test_phase_progress_range(clock):
    dt = datetime(2026, 8, 27, 12, 30, tzinfo=timezone.utc)
    progress = clock.phase_progress(dt)
    assert 0.0 <= progress <= 1.0

def test_is_responsive_false_deep_rest(clock):
    dt = datetime(2026, 8, 27, 1, 0, tzinfo=timezone.utc)
    assert clock.is_responsive(dt) is False

def test_is_responsive_true_atelier(clock):
    dt = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    assert clock.is_responsive(dt) is True

def test_get_tts_mode_night(clock):
    dt = datetime(2026, 8, 27, 3, 0, tzinfo=timezone.utc)
    mode = clock.get_tts_mode(dt)
    assert mode["rate"] < 1.0

def test_jitter_deterministic():
    clock = CircadianClock(tz_name="UTC", jitter_minutes=30)
    dt1 = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    dt2 = datetime(2026, 8, 27, 15, 0, tzinfo=timezone.utc)
    assert clock._get_jitter(dt1) == clock._get_jitter(dt2)

def test_jitter_varies_by_day():
    clock = CircadianClock(tz_name="UTC", jitter_minutes=30)
    dt1 = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    dt2 = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
    assert clock._get_jitter(dt1) != clock._get_jitter(dt2)
