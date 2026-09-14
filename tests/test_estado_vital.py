"""
Que una muerte a mitad de escribir no le vacíe el estado vital.

Era el último módulo que guardaba su JSON a mano, con `json.dump` directamente
sobre el fichero bueno. El proceso muere a la mitad justo al desplegar, y
entonces pasaba esto, sin que nada fallara: el estado quedaba ilegible, al
arrancar se descartaba y el primer `save()` sellaba encima los valores por
defecto. Se iban los impulsos pendientes —lo que ella había decidido hacer— y
`last_sleep_cycle`, que es la única traza de que la noche corrió; la sonda
pasaba a leer «nunca» una consolidación que sí había ocurrido.
"""

from pathlib import Path

import pytest

from src.core import estado_json
from src.core.vital_state import VitalState


@pytest.fixture
def vital(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "data" / "memoria.db"))
    estado = VitalState()
    estado.energy = 0.93
    estado.will_queue = [{"seed": "quiero componer algo", "action": "compose"}]
    estado.mark_sleep_cycle("nrem")
    return estado


def test_morir_a_mitad_de_escribir_no_deja_el_estado_a_medias(vital, monkeypatch):
    """
    El camino del producto: sellar la noche. Es lo que hace el ciclo de sueño.

    Lo que se comprueba no es que no se pierda nada —el turno en curso se
    pierde—, sino que lo anterior sobrevive **entero**. `os.replace` es atómico,
    así que quien lea sólo puede encontrar el contenido viejo o el nuevo.
    """
    bueno = Path(vital.state_path)
    antes = bueno.read_text(encoding="utf-8")
    escribir_real = Path.write_text

    def muere_a_medias(self, contenido, **kwargs):
        escribir_real(self, contenido[: len(contenido) // 2], **kwargs)
        raise KeyboardInterrupt("el proceso murió a mitad de escribir")

    monkeypatch.setattr(Path, "write_text", muere_a_medias)
    vital.energy = 0.10
    with pytest.raises(KeyboardInterrupt):
        vital.save()
    # Se restaura sólo la escritura. `monkeypatch.undo()` habría revertido
    # también el `DATABASE_PATH` del fixture, y la recarga de abajo habría ido a
    # parar al `data/` de la instancia — el fallo que esta suite persigue.
    monkeypatch.setattr(Path, "write_text", escribir_real)

    assert bueno.read_text(encoding="utf-8") == antes, "el fichero bueno quedó a medias"

    recuperado = VitalState()
    assert recuperado.energy == 0.93
    assert recuperado.will_queue == [{"seed": "quiero componer algo", "action": "compose"}]
    assert recuperado.last_sleep_cycle == vital.last_sleep_cycle, \
        "se perdió la única traza de que la noche corrió"


def test_un_estado_de_otro_esquema_no_se_aplica_a_trozos(monkeypatch, tmp_path):
    """
    O entra entero o no entra: nada de quedarse con las claves que encajan.

    El filtro por `hasattr` descarta lo que no reconoce, pero no protege del caso
    que duele: un fichero que es JSON válido y **comparte parte de los nombres**
    —otro esquema, una restauración cruzada, una versión anterior— se aplicaba
    campo a campo encima de los valores por defecto. El resultado es un estado
    mitad de uno y mitad de otro, que no falla aquí sino mucho después y lejos.
    Comprobar la forma lo rechaza entero, y `estado_json` lo deja dicho en el
    registro en vez de tragárselo.
    """
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "data" / "memoria.db"))
    ajeno = tmp_path / "data" / "vital_state.json"
    ajeno.parent.mkdir(parents=True, exist_ok=True)
    # Sin `energy`: no es un estado vital. Pero trae dos nombres que sí existen.
    estado_json.escribir(ajeno, {"will_queue": [{"basura": 1}],
                                 "circadian_phase": "fase_inventada"})

    estado = VitalState()

    assert estado.will_queue == [], "aplicó a trozos un estado de otro esquema"
    assert estado.circadian_phase == "atelier"
    assert estado.energy == 0.75


def test_el_estado_vital_se_escribe_donde_manda_la_variable(monkeypatch, tmp_path):
    """
    La copia de seguridad lo busca en el directorio de la memoria. Con `data/`
    fijo, una instancia reubicada no lo metía en ninguna copia — y el manifiesto
    lo listaba como ausente, donde nadie mira hasta el día de restaurar.
    """
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "otra" / "memoria.db"))

    estado = VitalState()
    estado.mark_sleep_cycle("rem")

    assert Path(estado.state_path) == tmp_path / "otra" / "vital_state.json"
    assert (tmp_path / "otra" / "vital_state.json").is_file()
