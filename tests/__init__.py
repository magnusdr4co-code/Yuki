"""
Suite de tests para Yuki (Hermes Agent Harness).

**El aislamiento vive aquí, no sólo en `conftest.py`.**

`conftest.py` es un mecanismo de pytest. La CI ejecuta además
`python -m unittest discover -s tests` —y el README lo documentó durante meses
como la forma de probar el proyecto—, y por ese camino las *fixtures* no se
aplican: la suite escribía estado de verdad en `data/` de la instancia. Una
pasada dejaba ahí `yuki_memory.db`, `honcho_profile.json`, `vital_state.json`,
`spend_ledger.json`, `agency_ledger.json`, `persona_drift.json` y
`transparency.json`. La segunda pasada fallaba, porque el perfil dialéctico ya
traía el ajuste que la prueba iba a hacer. En integración continua no se notaba
nunca: cada trabajo arranca de un checkout limpio.

Es exactamente el fallo de los 887 recuerdos que `test_aislamiento.py` vigila,
vivo en el camino que la propia CI ejecuta. Por eso la redirección se hace al
importar el paquete —que ocurre en los dos caminos— y `conftest.py` sigue
afinando por prueba con `monkeypatch`, que manda sobre esto.
"""

import os
import tempfile
from pathlib import Path

# Un directorio por proceso. No se borra al terminar a propósito: si una prueba
# deja algo raro, poder mirarlo vale más que el espacio que ocupa, y el sistema
# lo limpia solo.
_SANDBOX = Path(tempfile.mkdtemp(prefix="yuki-tests-"))

# Todas las variables de reubicación del estado durable. La lista es la misma
# que `conftest.py` redirige; si nace una nueva, va en los dos sitios — y
# `test_aislamiento.py` comprueba que ninguna se quede fuera.
_REUBICACIONES = {
    "DATABASE_PATH": _SANDBOX / "data" / "yuki_memory.db",
    "YUKI_OUTPUT_DIR": _SANDBOX / "output",
    "YUKI_SPEND_LEDGER_PATH": _SANDBOX / "spend_ledger.json",
    "YUKI_AGENCY_LEDGER_PATH": _SANDBOX / "agency_ledger.json",
    "YUKI_RITUALS_PATH": _SANDBOX / "runtime_rituals.json",
    "YUKI_TRANSPARENCY_PATH": _SANDBOX / "transparency.json",
    "YUKI_CUADERNO_PATH": _SANDBOX / "cuaderno_taller.json",
    "YUKI_PERSONA_PATH": _SANDBOX / "persona_drift.json",
    "YUKI_BLACKBOX_PATH": _SANDBOX / "bitacora.jsonl",
    "YUKI_FRENO_PATH": _SANDBOX / "freno.json",
    "YUKI_RUNTIME_CONFIG_PATH": _SANDBOX / "runtime_overrides.json",
    "DISCORD_PAIRING_PATH": _SANDBOX / "discord_pairing.json",
}

for _variable, _destino in _REUBICACIONES.items():
    # `setdefault`: quien ejecute la suite con una ruta puesta a mano manda.
    os.environ.setdefault(_variable, str(_destino))

# El freno de entorno no se hereda de la máquina de quien ejecuta: una prueba
# que corriera con `YUKI_FRENO=todo` puesto comprobaría otra cosa.
os.environ.pop("YUKI_FRENO", None)
