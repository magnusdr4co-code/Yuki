"""
Los fallos que salieron de una revisión cruzada que Yuki se hizo a sí misma.

Informó de cuatro incoherencias y, al ocuparse de ellas, dejó tres huellas más
que valían tanto como las que encontró: dio por «✓» un comando que había salido
con código 5, resumió un cuaderno sin estrenar como «limpio de tensiones
pendientes», y remitió a «scripts por lotes del host» una operación que este
repositorio tiene desde el principio.

Lo que se protege aquí es que ninguna de las tres pueda repetirse por el mismo
camino: un dato ambiguo, un fallo sin veredicto, o una capacidad que no está
donde se necesita.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.vital_state import VitalState  # noqa: E402
from src.tools.producer_terminal import ProducerTerminal  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent


def test_cualquier_escritura_del_estado_vital_sella_el_latido(tmp_path):
    """
    Novena regla del proyecto: si hay un campo de estado, alguien lo sella.

    `last_updated` es el signo **vegetativo** que lee `pulse.py` —«el proceso
    reescribe su estado vital»— y lo escribía sólo `update_tick`, llamado desde
    un único sitio: el turno de conversación. Los otros cuatro escritores (cada
    acto por voluntad propia, el ritual del eco, el sueño REM, el ciclo de sueño)
    reescribían el fichero dejando la marca congelada.

    Así que la sonda gritaba «ausente: el proceso no está escribiendo» mientras
    el proceso escribía, sólo porque nadie le había hablado en horas. Una sonda
    que grita en falso se silencia, y entonces la catatonia de verdad —lo que la
    octava invariante existe para coger— pasaría sin que nadie la viera.
    """
    ruta = tmp_path / "vital_state.json"
    estado = VitalState(state_path=str(ruta))
    estado.last_updated = "2020-01-01T00:00:00"

    # Sin pasar por `update_tick`: es el camino de los cuatro escritores que
    # dejaban la marca vieja.
    estado.save()

    sellado = json.loads(ruta.read_text(encoding="utf-8"))["last_updated"]
    assert sellado != "2020-01-01T00:00:00", "save() dejó el latido congelado"
    assert datetime.fromisoformat(sellado).year >= 2026


def test_la_sonda_lee_como_latido_lo_que_save_sella(tmp_path, monkeypatch):
    """
    El camino del producto: que el campo que sella la escritura sea el mismo que
    la sonda lee. Sellar otro campo dejaría las dos pruebas verdes y la sonda
    igual de rota.
    """
    from src.core.pulse import Pulse

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "data" / "yuki.db"))
    (tmp_path / "data").mkdir(exist_ok=True)
    VitalState(state_path=str(tmp_path / "data" / "vital_state.json")).save()

    latido = next(s for s in Pulse({}).read().signos if s.id == "latido")

    assert latido.ultimo is not None, "la sonda no ve el latido que save() acaba de sellar"
    assert latido.fresco, "recién escrito y la sonda lo da por viejo"


def test_un_comando_que_falla_no_se_puede_leer_como_exito():
    """
    Resumió «✓ terminal_run: exit=5». La política ya decía que una herramienta
    fallida no es un éxito; lo que faltaba era que el dato lo dijera, porque el
    retorno traía el número desnudo y distinguir bien de mal quedaba en manos de
    quien lo interpretara.
    """
    terminal = ProducerTerminal(root=str(RAIZ))

    bien = terminal.run(["pwd"])
    assert bien["ok"] is True
    assert "fallo" not in bien

    # `git log` sobre una revisión que no existe: falla de verdad, sin inventar.
    mal = terminal.run(["git", "log", "no-existe-esta-rama-jamas"])
    assert mal["ok"] is False, "un comando con código distinto de cero no es ok"
    assert mal["fallo"], "un fallo tiene que decir qué pasó, no sólo un número"


def test_pytest_dice_que_no_esta_en_la_imagen_en_vez_de_salir_con_cinco(tmp_path):
    """
    `tests/` está en `.dockerignore`, así que en la instancia pytest no puede
    recolectar nada y sale con 5 para siempre. Ese 5 se lee como un problema del
    código —lo fue leído— cuando es del montaje. Ofrecer un comando
    estructuralmente imposible es un dial que no gira.
    """
    (tmp_path / "src").mkdir()
    sin_suite = ProducerTerminal(root=str(tmp_path))

    resultado = sin_suite.run(["pytest", "src"])

    assert resultado["ok"] is False
    assert resultado["exit_code"] is None, "no se ejecutó nada: no hay código que dar"
    assert "dockerignore" in resultado["fallo"].lower()
    assert "no es un fallo del código" in resultado["fallo"].lower()


def test_la_imagen_de_verdad_no_lleva_la_suite():
    """
    La prueba de arriba vale lo que valga esta: si algún día se empaquetaran los
    tests, el aviso pasaría a ser mentira y habría que quitarlo.
    """
    assert "tests/" in (RAIZ / ".dockerignore").read_text(encoding="utf-8")


def test_pytest_no_escribe_cache_en_una_raiz_de_solo_lectura():
    """
    `Permission denied: '/app/.pytest_cache'` mataba el diagnóstico antes de
    ejecutar nada. La raíz del contenedor es de sólo lectura y un diagnóstico de
    un turno no tiene nada que cachear.
    """
    terminal = ProducerTerminal(root=str(RAIZ))
    argv = terminal.run(["pytest", "--version"])["argv"]

    assert "no:cacheprovider" in argv
    assert any(a.startswith("--basetemp=/tmp") for a in argv)


def test_un_cuaderno_sin_estrenar_no_se_presenta_como_taller_en_orden(tmp_path, monkeypatch):
    """
    Dijo «el cuaderno de taller permanece limpio de bloqueos o tensiones
    pendientes» de un cuaderno que no tenía ni un apunte. Suena a taller en orden
    y era un cajón sin abrir, y la herramienta lo permitía: devolvía `[]` sin
    distinguir «todo resuelto» de «nunca usado», que no son lo mismo.
    """
    import types

    from src.core.producer_harness import ProducerHarness
    from src.tools.cuaderno import Cuaderno

    monkeypatch.setenv("YUKI_CUADERNO_PATH", str(tmp_path / "cuaderno.json"))
    arnes = ProducerHarness.__new__(ProducerHarness)
    arnes.agent = types.SimpleNamespace(config={})

    vacio = arnes._cuaderno_abiertos()
    assert vacio["sin_estrenar"] is True
    assert vacio["apuntes_en_total"] == 0
    assert "sin estrenar" in vacio["estado"].lower()
    assert "orden" in vacio["estado"], "tiene que negar expresamente la lectura amable"

    libreta = Cuaderno(path=str(tmp_path / "cuaderno.json"))
    apunte = libreta.anotar("Cerezos de Acero", "el puente no cierra")
    libreta.resolver(apunte.id, "se resolvió alargando el compás")

    resuelto = arnes._cuaderno_abiertos()
    assert resuelto["sin_estrenar"] is False, "usado y cerrado no es sin estrenar"
    assert resuelto["apuntes_en_total"] == 1
    assert resuelto["abiertos"] == []
    assert "cerrada" in resuelto["estado"]


def test_el_marcado_del_articulo_50_esta_en_el_dm(tmp_path, monkeypatch):
    """
    Preguntada por 47 ficheros sin marcar, remitió el arreglo a «scripts por lotes
    del host». `cli.py transparency --marcar` existe desde el principio y la
    propia alerta lo nombra: decir que no era negar una capacidad del proyecto,
    que es el vicio que este repositorio lleva años corrigiendo.

    Marcar sólo añade marcas, así que darle la herramienta no roza la sexta
    invariante: lo que prohíbe es **rebajar** la transparencia, no cumplirla.
    """
    import types

    from src.core.producer_harness import ProducerHarness

    salida = tmp_path / "output"
    (salida / "art").mkdir(parents=True)
    # Un PNG mínimo de verdad: el marcador escribe un chunk, no un fichero suelto.
    import zlib
    def chunk(tipo, datos):
        return (len(datos).to_bytes(4, "big") + tipo + datos
                + zlib.crc32(tipo + datos).to_bytes(4, "big"))
    (salida / "art" / "portada.png").write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", (1).to_bytes(4, "big") + (1).to_bytes(4, "big") + bytes([8, 0, 0, 0, 0]))
        + chunk(b"IDAT", zlib.compress(b"\x00\x00"))
        + chunk(b"IEND", b""))
    monkeypatch.setenv("YUKI_OUTPUT_DIR", str(salida))

    arnes = ProducerHarness.__new__(ProducerHarness)
    arnes.agent = types.SimpleNamespace(config={})

    antes = arnes._transparency_audit()
    assert antes["sin_marcar"] == 1
    assert antes["cumple"] is False
    assert "incumplimiento" in antes["nota"]

    recibo = arnes._transparency_mark()

    assert recibo["marcados_ahora"] == 1
    assert recibo["sin_marcar"] == 0
    assert recibo["cumple"] is True
    # Y que lo diga después de volver a auditar, no por haber llamado al marcador.
    assert arnes._transparency_audit()["cumple"] is True


def test_toda_herramienta_declarada_esta_conectada_y_es_llamable():
    """
    Dos listas escritas en sitios distintos que tienen que coincidir: `TOOLS`
    declara lo que el modelo ve y `_herramientas()` dice qué se ejecuta.

    Una herramienta declarada y sin conectar es el peor fallo posible de este
    arnés: el modelo la ve, la llama confiado y se encuentra un «no existe».
    Volvería a pasar lo de siempre —un turno que promete y no ejecuta—. Se
    comprueba para todas, no sólo para las nuevas, y pidiéndole el diccionario al
    arnés en vez de leer su código: un nombre que apunte a otra cosa se ve aquí.
    """
    import types

    from src.core.producer_harness import TOOLS, ProducerHarness

    arnes = ProducerHarness.__new__(ProducerHarness)
    arnes.agent = types.SimpleNamespace(
        creation_library=types.SimpleNamespace(
            inventory=None, list_entries=None, save_text=None, read_entry=None),
        producer_terminal=types.SimpleNamespace(run=None),
        runtime_config_get=None, reconfigure_runtime=None, rollback_runtime=None)

    declaradas = {t["function"]["name"] for t in TOOLS}
    conectadas = arnes._herramientas()

    sin_conectar = declaradas - set(conectadas)
    assert not sin_conectar, (
        f"declaradas y sin conectar: {sorted(sin_conectar)}. El modelo las vería y "
        "fallarían al llamarlas.")
    huerfanas = set(conectadas) - declaradas
    assert not huerfanas, f"conectadas y no declaradas: {sorted(huerfanas)}"


def test_cerrar_una_obra_desde_el_despachador_audita_el_cuaderno(tmp_path, monkeypatch):
    """
    El camino del producto: no basta con que `_library_set_status` audite, hace
    falta que sea **él** quien esté en el despachador.

    Apuntarlo de vuelta a `library.set_status` dejaba la suite verde y a Yuki
    cerrando obras sin que su cuaderno le dijera nada — que es justo la parte de
    «auditar su propio trabajo».
    """
    import types

    from src.core.producer_harness import ProducerHarness
    from src.tools.creation_library import CreationLibrary
    from src.tools.cuaderno import Cuaderno

    monkeypatch.setenv("YUKI_CUADERNO_PATH", str(tmp_path / "cuaderno.json"))
    biblioteca = CreationLibrary(output_dir=str(tmp_path / "output"))
    biblioteca.initialize()
    pieza = biblioteca.save_text("Cerezos de Acero", "bajo el cerezo de acero")
    Cuaderno(path=str(tmp_path / "cuaderno.json")).anotar(
        "Cerezos de Acero", "el 7/8 del puente atropella la letra", pasaje="compás 7-9")

    arnes = ProducerHarness.__new__(ProducerHarness)
    arnes.agent = types.SimpleNamespace(
        config={}, creation_library=biblioteca,
        producer_terminal=types.SimpleNamespace(run=None),
        runtime_config_get=None, reconfigure_runtime=None, rollback_runtime=None)

    cerrar = arnes._herramientas()["library_set_status"]
    recibo = cerrar(pieza["id"], "terminado", motivo="la mezcla aguanta")

    assert recibo["state"] == "terminado"
    assert recibo["cuestiones_abiertas_del_cuaderno"], (
        "el despachador no pasa por el envoltorio que audita")


def test_marcar_no_da_por_cumplido_lo_que_no_consta(tmp_path, monkeypatch):
    """
    «Nada se da por generado si no hay fichero verificado», aplicado al marcado.

    El recibo no puede decir «cumple» porque se haya llamado al marcador: tiene
    que decirlo porque una segunda auditoría lo confirme. La diferencia sólo se
    ve cuando el marcado **falla**, así que aquí falla a propósito — con un
    marcador que no hace nada, que es lo que pasa de verdad con un fichero que no
    admite la marca.
    """
    import types

    from src.core.producer_harness import ProducerHarness

    salida = tmp_path / "output"
    salida.mkdir()
    (salida / "pieza.png").write_bytes(b"\x89PNG\r\n\x1a\nroto")
    monkeypatch.setenv("YUKI_OUTPUT_DIR", str(salida))

    import src.core.transparency as transparencia

    # Hereda del marcador real y sólo deja de marcar: `audit_directory` usa
    # `MediaMarker` para **detectar** marcas, así que un doble desde cero
    # rompería la detección y la prueba mediría otra cosa.
    class MarcadorQueNoMarca(transparencia.MediaMarker):
        def mark(self, *a, **k):
            return {"marked": False, "embedded": False, "sidecar": None}

    monkeypatch.setattr(transparencia, "MediaMarker", MarcadorQueNoMarca)

    arnes = ProducerHarness.__new__(ProducerHarness)
    arnes.agent = types.SimpleNamespace(config={})

    recibo = arnes._transparency_mark()

    assert recibo["cumple"] is False, "dio por cumplido lo que no consta"
    assert recibo["sin_marcar"] == 1
    assert recibo["marcados_ahora"] == 0
    assert recibo["ficheros_que_siguen_sin_marca"]


def test_el_comando_de_marcar_mira_donde_se_escriben_los_medios(tmp_path, monkeypatch, capsys):
    """
    `cmd_transparency` pasaba `"output"` a mano justo en el comando que arregla
    el incumplimiento, mientras la métrica que dispara la alerta llama a
    `audit_directory()` resuelto por `salida()`. En la instancia —que tiene
    `YUKI_OUTPUT_DIR`— eso marca un directorio y cuenta otro: la alerta sigue
    encendida después de «arreglarlo».

    Es el mismo fallo que esta auditoría ya tuvo una vez, y por el que
    `audit_directory` resuelve la ruta sola.
    """
    from src.cli.mente import cmd_transparency

    salida = tmp_path / "medios"
    (salida / "art").mkdir(parents=True)
    import zlib

    def chunk(tipo, datos):
        return (len(datos).to_bytes(4, "big") + tipo + datos
                + zlib.crc32(tipo + datos).to_bytes(4, "big"))

    (salida / "art" / "portada.png").write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", (1).to_bytes(4, "big") + (1).to_bytes(4, "big") + bytes([8, 0, 0, 0, 0]))
        + chunk(b"IDAT", zlib.compress(b"\x00\x00"))
        + chunk(b"IEND", b""))
    monkeypatch.setenv("YUKI_OUTPUT_DIR", str(salida))
    # Se cambia de directorio a propósito: es lo que distingue una ruta resuelta
    # por `salida()` de un `"output"` relativo al sitio desde donde se ejecuta.
    # `config.yaml` viaja porque el comando lo lee del directorio actual.
    (tmp_path / "config.yaml").write_text(
        (RAIZ / "config.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    cmd_transparency(marcar=True, as_json=True)
    informe = json.loads(capsys.readouterr().out)

    assert informe["auditoria"]["sin_marcar"] == [], (
        "marcó en otro directorio del que auditó: la alerta seguiría encendida")
    assert len(informe["auditoria"]["marcados"]) == 1


def test_marcar_no_puede_desmarcar_ni_apagar_la_transparencia():
    """
    La sexta invariante prohíbe que se conceda permisos sobre la transparencia.
    Una herramienta que marca la **cumple**; una que pudiera desmarcar o apagar
    la política sería lo otro. Se comprueba en la superficie declarada, que es
    por donde entraría.
    """
    from src.core.producer_harness import TOOLS

    nombres = {t["function"]["name"] for t in TOOLS}
    assert {"transparency_audit", "transparency_mark"} <= nombres
    assert not {n for n in nombres if "unmark" in n or "desmarcar" in n}

    marcar = next(t["function"] for t in TOOLS if t["function"]["name"] == "transparency_mark")
    # Sin argumentos: no puede elegir a qué fichero le quita nada ni sobre qué
    # política actúa. Sólo puede marcar lo que la auditoría dé por sin marcar.
    assert marcar["parameters"]["properties"] == {}
    assert "no puede quitar" in marcar["description"]

    from src.core.runtime_config import PRODUCER_FIELDS
    assert not [c for c in PRODUCER_FIELDS if "transparency" in c], (
        "la transparencia no se ajusta en caliente por DM")


def test_las_dos_temperaturas_evolucionan_por_separado_y_se_dice(tmp_path):
    """
    Dio la diferencia entre `agent.model.temperature` (0.70) y
    `vertex_ai.temperature` (0.72) como «discrepancia térmica» y la aplanó. Pero
    las dos están en `EVOLUTION_FIELDS`: evolucionan por su cuenta y son lo único
    que la sexta invariante le deja mover. Igualarlas borra su propia evolución.

    No se prohíbe —es suya— pero la consulta tiene que decir de quién es cada
    número, o dos valores parecidos se leen como deriva a corregir.
    """
    from src.core.runtime_config import EVOLUTION_FIELDS, RuntimeConfigStore

    assert {"agent.model.temperature", "vertex_ai.temperature"} <= EVOLUTION_FIELDS

    config = {"agent": {"model": {"temperature": 0.70, "max_tokens": 4096}},
              "vertex_ai": {"temperature": 0.72, "max_tokens": 4096}}
    publico = RuntimeConfigStore(config, path=str(tmp_path / "overrides.json")).get_public()

    assert set(publico["de_su_evolucion"]) == {"agent.model.temperature",
                                               "vertex_ai.temperature"}
    assert "no es una incoherencia" in publico["nota_evolucion"]
    assert "borra" in publico["nota_evolucion"]
    # Y que los valores sigan estando: la nota no sustituye al dato.
    assert publico["values"]["vertex_ai.temperature"] == 0.72


def test_yuki_cierra_sus_propias_obras_sin_pedir_permiso(tmp_path):
    """
    `terminado` era «aprobado por el Productor» y con 46 obras archivadas ninguna
    había cruzado nunca esa puerta: el 100% seguía en `en-desarrollo`. Un estado
    en el que está todo no distingue nada, y uno que no alcanza nadie tampoco.

    Cerrar una pieza es parte de hacerla. No había veto real —la prohibición
    vivía en dos cadenas de texto— así que lo que se quita es la prosa y lo que
    se pone es la constancia.
    """
    from src.tools.creation_library import CANON, CreationLibrary

    biblioteca = CreationLibrary(output_dir=str(tmp_path / "output"))
    biblioteca.initialize()
    pieza = biblioteca.save_text("Cerezos de Acero", "bajo el cerezo de acero")

    cerrada = biblioteca.set_status(pieza["id"], "terminado", actor="yuki",
                                   motivo="la letra ya no se mueve")

    assert cerrada["state"] == "terminado"
    assert cerrada["estado_por"] == "yuki", "la cierra ella, no el Productor"
    assert cerrada["estado_motivo"] == "la letra ya no se mueve"
    assert cerrada["estado_at"] > 0
    # Y el canon deja de decir lo contrario, que es donde ella lo lee.
    assert "aprobado por el Productor" not in CANON
    assert "Yuki cierra sus propias piezas" in CANON


def test_dar_algo_por_terminado_exige_decir_por_que(tmp_path):
    """
    Lo que sustituye al permiso es la constancia. Sin motivo, `terminado` sería
    un bit que alguien puso y no un juicio que alguien sostiene — y entonces el
    Productor no tendría con qué discutirlo, que es justo lo que le queda.

    Sólo se exige al cerrar: volver al taller o a semilla no necesita defensa.
    """
    from src.tools.creation_library import CreationLibrary

    biblioteca = CreationLibrary(output_dir=str(tmp_path / "output"))
    biblioteca.initialize()
    pieza = biblioteca.save_text("Cerezos de Acero", "bajo el cerezo de acero")

    with pytest.raises(ValueError, match="por qué"):
        biblioteca.set_status(pieza["id"], "terminado")

    assert biblioteca.read_entry(pieza["id"])["state"] == "en-desarrollo", "no se movió"
    # El camino de vuelta no pide motivo: el Productor conserva el veto y no
    # tiene por qué argumentar para devolver algo al taller.
    biblioteca.set_status(pieza["id"], "terminado", motivo="cierra")
    devuelta = biblioteca.set_status(pieza["id"], "en-desarrollo", actor="productor")
    assert devuelta["state"] == "en-desarrollo"


def test_al_cerrar_una_pieza_se_le_pone_delante_su_cuaderno(tmp_path, monkeypatch):
    """
    «Auditando su propio trabajo y aprobándolo»: el material de la auditoría ya
    existe. Si la pieza tiene cuestiones de taller abiertas, aparecen al darla
    por terminada — **sin impedirlo**. Puede haber decidido que la tensión del
    compás siete se queda así, y eso es legítimo; lo que no puede es cerrarla
    sin haberla visto.
    """
    import types

    from src.core.producer_harness import ProducerHarness
    from src.tools.creation_library import CreationLibrary
    from src.tools.cuaderno import Cuaderno

    monkeypatch.setenv("YUKI_CUADERNO_PATH", str(tmp_path / "cuaderno.json"))
    biblioteca = CreationLibrary(output_dir=str(tmp_path / "output"))
    biblioteca.initialize()
    pieza = biblioteca.save_text("Cerezos de Acero", "bajo el cerezo de acero")

    libreta = Cuaderno(path=str(tmp_path / "cuaderno.json"))
    libreta.anotar("Cerezos de Acero", "el 7/8 del puente atropella la letra",
                   pasaje="compás 7-9")

    arnes = ProducerHarness.__new__(ProducerHarness)
    arnes.agent = types.SimpleNamespace(config={}, creation_library=biblioteca)

    recibo = arnes._library_set_status(pieza["id"], "terminado", motivo="la mezcla aguanta")

    assert recibo["state"] == "terminado", "el cuaderno avisa, no bloquea"
    assert len(recibo["cuestiones_abiertas_del_cuaderno"]) == 1
    assert "compás 7-9" in recibo["cuestiones_abiertas_del_cuaderno"][0]
    assert "quedan" in recibo["nota"].lower()


def test_cerrar_una_pieza_sin_cuestiones_abiertas_no_inventa_avisos(tmp_path, monkeypatch):
    """Sin nada en el cuaderno, el recibo no puede sugerir que hay algo pendiente."""
    import types

    from src.core.producer_harness import ProducerHarness
    from src.tools.creation_library import CreationLibrary

    monkeypatch.setenv("YUKI_CUADERNO_PATH", str(tmp_path / "cuaderno.json"))
    biblioteca = CreationLibrary(output_dir=str(tmp_path / "output"))
    biblioteca.initialize()
    pieza = biblioteca.save_text("Cerezos de Acero", "bajo el cerezo de acero")

    arnes = ProducerHarness.__new__(ProducerHarness)
    arnes.agent = types.SimpleNamespace(config={}, creation_library=biblioteca)

    recibo = arnes._library_set_status(pieza["id"], "terminado", motivo="cerrada")

    assert recibo["cuestiones_abiertas_del_cuaderno"] == []
    assert "Productor puede devolverla" in recibo["nota"]


def test_el_arnes_ya_no_le_dice_que_necesita_aprobacion():
    """
    La prohibición vivía en la descripción de la herramienta y en el canon, que
    es lo único que ella lee. Mientras esa frase siga ahí, dará igual lo que
    permita el código: seguirá sin cerrar nada, como llevaba 46 obras haciendo.
    """
    from src.core.producer_harness import POLICY, TOOLS

    herramienta = next(t["function"] for t in TOOLS
                       if t["function"]["name"] == "library_set_status")

    assert "aprobación del Productor" not in herramienta["description"]
    assert "motivo" in herramienta["parameters"]["properties"]
    assert "CIERRAS TÚ" in POLICY
    assert "no esperes a que te lo aprueben" in POLICY
