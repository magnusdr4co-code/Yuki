"""
Aislamiento común de la suite.

Sin esto, cualquier prueba que construya el cliente de medios anota gasto en el
libro real del repositorio (`data/spend_ledger.json`) y contamina el
presupuesto del día siguiente a quien ejecute los tests. Lo mismo vale para el
diario de agencia, que además guarda el techo diario de acciones autónomas.

Y para la memoria, que es lo único irremplazable: sin aislarla, una prueba que
construya el agente entero escribe recuerdos reales en la base de la instancia.
"""

import pytest


@pytest.fixture(autouse=True)
def libro_de_gasto_aislado(tmp_path, monkeypatch):
    monkeypatch.setenv("YUKI_SPEND_LEDGER_PATH", str(tmp_path / "spend_ledger.json"))
    monkeypatch.setenv("YUKI_AGENCY_LEDGER_PATH", str(tmp_path / "agency_ledger.json"))
    monkeypatch.setenv("YUKI_RITUALS_PATH", str(tmp_path / "runtime_rituals.json"))
    monkeypatch.setenv("YUKI_TRANSPARENCY_PATH", str(tmp_path / "transparency.json"))
    # Y que la obra falsa de las pruebas no acabe en el `output/` del repositorio.
    monkeypatch.setenv("YUKI_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("YUKI_PERSONA_PATH", str(tmp_path / "persona_drift.json"))
    monkeypatch.setenv("YUKI_BLACKBOX_PATH", str(tmp_path / "bitacora.jsonl"))
    monkeypatch.setenv("YUKI_FRENO_PATH", str(tmp_path / "freno.json"))
    monkeypatch.delenv("YUKI_FRENO", raising=False)
    # Y la memoria, que era la que faltaba y la única irremplazable. Cualquier
    # prueba que construyera un `YukiAgent` completo escribía recuerdos de verdad
    # en `data/yuki_memory.db`: 887 «Encuentro con Productor» se habían acumulado
    # ahí, uno por cada pasada de la suite. Contaminan lo que Yuki recuerda,
    # engordan cada copia y falsean el signo vital de conversación.
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "data" / "yuki_memory.db"))
