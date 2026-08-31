import sys
import os
import pytest
from unittest.mock import MagicMock
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.core.growth_journal import GrowthJournal

class MockConnectionContext:
    def __init__(self, conn):
        self.conn = conn
    def __enter__(self):
        return self.conn
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

class MockMemoryEngine:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('''CREATE TABLE memories 
                            (id INTEGER PRIMARY KEY, content TEXT, category TEXT, created_at REAL)''')
        self.events = []
    
    def _get_connection(self):
        return MockConnectionContext(self.conn)
        
    def add_growth_event(self, **kwargs):
        # Map kwargs to match real SQLite column names
        event = {
            "domain": kwargs.get("domain", ""),
            "from_position": kwargs.get("from_pos", kwargs.get("from_position", "")),
            "to_position": kwargs.get("to_pos", kwargs.get("to_position", "")),
            "confidence": kwargs.get("confidence", 0.5),
            "date": kwargs.get("date", ""),
            "trigger_memory_ids": kwargs.get("trigger_ids", "[]"),
        }
        self.events.append(event)
        
    def get_recent_growth(self, limit):
        return self.events[-limit:] if self.events else []

@pytest.fixture
def journal():
    return GrowthJournal(memory_engine=MockMemoryEngine())

def test_parse_llm_growth_response_single(journal):
    response = """
    DOMAIN: music
    FROM: Inseguridad
    TO: Aceptación
    CONFIDENCE: 0.8
    """
    events = journal.parse_llm_growth_response(response)
    assert len(events) == 1
    assert events[0]["domain"] == "music"
    assert events[0]["from_position"] == "Inseguridad"
    assert events[0]["to_position"] == "Aceptación"
    assert events[0]["confidence"] == 0.8

def test_parse_llm_growth_response_multiple(journal):
    response = """
    DOMAIN: music
    FROM: a
    TO: b
    CONFIDENCE: 0.8
    
    DOMAIN: aesthetics
    FROM: c
    TO: d
    CONFIDENCE: 0.9
    """
    events = journal.parse_llm_growth_response(response)
    assert len(events) == 2

def test_parse_llm_growth_response_empty(journal):
    response = "No hay cambios"
    events = journal.parse_llm_growth_response(response)
    assert len(events) == 0

def test_get_evolution_context_empty(journal):
    context = journal.get_evolution_context()
    assert "No hay evolución reciente registrada" in context

def test_record_and_retrieve_growth_event(journal):
    journal.record_growth_event("music", "old", "new", [1, 2], 0.9)
    events = journal.engine.get_recent_growth(3)
    assert len(events) == 1
    assert events[0]["domain"] == "music"
    
    context = journal.get_evolution_context()
    assert "old" in context
    assert "new" in context
