"""
Aislamiento común de la suite.

Sin esto, cualquier prueba que construya el cliente de medios anota gasto en el
libro real del repositorio (`data/spend_ledger.json`) y contamina el
presupuesto del día siguiente a quien ejecute los tests. Lo mismo vale para el
diario de agencia, que además guarda el techo diario de acciones autónomas.
"""

import pytest


@pytest.fixture(autouse=True)
def libro_de_gasto_aislado(tmp_path, monkeypatch):
    monkeypatch.setenv("YUKI_SPEND_LEDGER_PATH", str(tmp_path / "spend_ledger.json"))
    monkeypatch.setenv("YUKI_AGENCY_LEDGER_PATH", str(tmp_path / "agency_ledger.json"))
