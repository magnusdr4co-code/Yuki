import sys
import os
import pytest
import time
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.core.spark import Impulse, WillQueue, EchoRitual, AgencyLoop

def test_impulse_current_intensity_decays():
    impulse = Impulse("source", "desire", "hint", 1.0, time.time() - 3600, 2.0)
    assert impulse.current_intensity < 1.0
    assert impulse.current_intensity > 0.0

def test_impulse_is_expired():
    impulse = Impulse("source", "desire", "hint", 1.0, time.time() - 10000, 2.0)
    assert impulse.is_expired is True

def test_impulse_serialization():
    impulse1 = Impulse("source", "desire", "hint", 0.8, 100.0, 2.0, True)
    data = impulse1.to_dict()
    impulse2 = Impulse.from_dict(data)
    assert impulse1.source == impulse2.source
    assert impulse1.fulfilled == impulse2.fulfilled

def test_will_queue_add_and_get_strongest():
    queue = WillQueue()
    queue.add(Impulse("s1", "d1", "h1", 0.5, time.time(), 2.0))
    queue.add(Impulse("s2", "d2", "h2", 0.9, time.time(), 2.0))
    strongest = queue.get_strongest()
    assert strongest.source == "s2"

def test_will_queue_prune_expired():
    queue = WillQueue()
    queue.add(Impulse("s1", "d1", "h1", 0.5, time.time() - 10000, 2.0))
    queue.prune_expired()
    assert queue.active_count() == 0

def test_will_queue_max_size_enforced():
    queue = WillQueue(max_size=2)
    queue.add(Impulse("s1", "d1", "h1", 0.3, time.time(), 2.0))
    queue.add(Impulse("s2", "d2", "h2", 0.5, time.time(), 2.0))
    queue.add(Impulse("s3", "d3", "h3", 0.9, time.time(), 2.0))
    assert queue.active_count() == 2
    assert queue.get_strongest().source == "s3"

def test_will_queue_fulfill():
    queue = WillQueue()
    imp = Impulse("s1", "d1", "h1", 0.9, time.time(), 2.0)
    queue.add(imp)
    queue.fulfill(imp)
    assert queue.get_strongest() is None

def test_will_queue_serialization():
    queue = WillQueue()
    queue.add(Impulse("s1", "d1", "h1", 0.9, time.time(), 2.0))
    data = queue.to_list()
    queue2 = WillQueue.from_list(data)
    assert queue2.active_count() == 1
    assert queue2.get_strongest().source == "s1"

def test_echo_ritual_extract_impulses_music():
    ritual = EchoRitual(MagicMock(), MagicMock())
    state = MagicMock(inspiration=0.5, energy=0.5)
    impulses = ritual.extract_impulses_from_echo("Quiero hacer música y componer una melodía", state)
    assert any(i.tool_hint == "compose" for i in impulses)

def test_echo_ritual_extract_impulses_paint():
    ritual = EchoRitual(MagicMock(), MagicMock())
    state = MagicMock(inspiration=0.5, energy=0.5)
    impulses = ritual.extract_impulses_from_echo("Deseo pintar con color y luz", state)
    assert any(i.tool_hint == "paint" for i in impulses)

def test_echo_ritual_extract_impulses_default():
    ritual = EchoRitual(MagicMock(), MagicMock())
    state = MagicMock(inspiration=0.5, energy=0.5)
    impulses = ritual.extract_impulses_from_echo("Solo quiero estar", state)
    assert any(i.tool_hint == "contemplate" for i in impulses)

def test_agency_loop_evaluate_returns_impulse():
    queue = WillQueue()
    imp = Impulse("s1", "d1", "h1", 0.9, time.time(), 2.0)
    queue.add(imp)
    state = MagicMock()
    state.has_energy_for.return_value = True
    loop = AgencyLoop(queue, state)
    assert loop.evaluate() == imp

def test_agency_loop_evaluate_no_energy():
    queue = WillQueue()
    imp = Impulse("s1", "d1", "h1", 0.9, time.time(), 2.0)
    queue.add(imp)
    state = MagicMock()
    state.has_energy_for.return_value = False
    loop = AgencyLoop(queue, state)
    assert loop.evaluate() is None

def test_agency_loop_record_action():
    queue = WillQueue()
    imp = Impulse("s1", "d1", "h1", 0.9, time.time(), 2.0)
    queue.add(imp)
    state = MagicMock()
    loop = AgencyLoop(queue, state)
    loop.record_action(imp, {"status": "ok"})
    assert imp.fulfilled is True
    assert len(loop.actions_log) == 1
