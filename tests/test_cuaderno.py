"""
El cuaderno de taller: lo que guarda, lo que se niega a guardar y a quién avisa.

Lo que se protege aquí no es que los campos se persistan —eso lo haría cualquier
JSON— sino las tres decisiones que lo hacen distinto de la Biblioteca y de la
memoria: no admite obra, el olvido no lo alcanza, y lo que sabe llega al criterio
como observación y nunca como parámetro.
"""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.tools import cuaderno as modulo  # noqa: E402
from src.tools.cuaderno import Cuaderno, CuadernoError  # noqa: E402


@pytest.fixture
def libreta(tmp_path):
    return Cuaderno(path=str(tmp_path / "cuaderno.json"))


def test_un_apunte_no_es_una_obra_y_el_error_dice_donde_va(libreta):
    """
    El tope no es cosmético: es lo que impide que el cuaderno se convierta en
    una Biblioteca paralela y peor —sin hash, sin estado, sin marca de origen—.

    Y el error nombra la Biblioteca a propósito. Si sólo dijera «demasiado
    largo», quien se lo encontrase recortaría el texto para que cupiera, y
    entonces el cuaderno sí habría empezado a guardar obra, sólo que mutilada.
    """
    letra_entera = "Bajo el cerezo de acero " * 40

    with pytest.raises(CuadernoError) as exc:
        libreta.anotar("Cerezos de Acero", letra_entera)

    assert "Biblioteca" in str(exc.value), "el error tiene que decir dónde va la obra"
    assert "library_save_text" in str(exc.value)
    assert libreta.abiertos() == [], "nada se guardó a medias"


def test_los_intentos_se_acumulan_en_vez_de_sustituirse(libreta):
    """
    Tres intentos por la misma razón no son tres fracasos: son un diagnóstico.
    Guardar sólo el último borra justo la serie que enseña algo.
    """
    apunte = libreta.anotar("Cerezos de Acero", "el 7/8 del puente atropella la letra",
                            pasaje="compás 7-9")
    libreta.intentar(apunte.id, "bajar a 64 BPM", "pierde el empuje del estribillo")
    libreta.intentar(apunte.id, "pasar el puente a 4/4", "deja de ser el puente")

    guardado = libreta.get(apunte.id)
    assert [i.que for i in guardado.intentos] == ["bajar a 64 BPM", "pasar el puente a 4/4"]
    assert guardado.intentos[0].por_que_no == "pierde el empuje del estribillo"


def test_un_intento_sin_por_que_no_cuajo_no_se_admite(libreta):
    """
    «Probé bajar el BPM» sin el porqué no sirve dentro de tres semanas: el qué
    se deduce del fichero, el porqué es lo único que no se puede reconstruir.
    """
    apunte = libreta.anotar("Cerezos de Acero", "el puente no cierra")

    with pytest.raises(CuadernoError, match="tres semanas"):
        libreta.intentar(apunte.id, "bajar a 64 BPM", "   ")

    assert libreta.get(apunte.id).intentos == []


def test_el_olvido_no_alcanza_al_cuaderno(tmp_path, monkeypatch):
    """
    La razón por la que esto no vive en la memoria.

    El ciclo de sueño suelta lo viejo, leve y nunca recuperado, y un apunte de
    taller es exactamente eso durante meses: nadie recuerda la tensión del
    compás siete hasta que vuelve a tocar esa pieza. La quinta invariante
    protege canon, síntesis, crecimiento y lo fijado —no apuntes—, así que un
    cuaderno construido sobre la memoria se borraría por donde más falta hace.

    Aquí no puede pasar, y no por una promesa: el ciclo de sueño recorre la base
    de datos y el cuaderno no está en ella. Se comprueba en el producto, podando
    de verdad, no leyendo el código.
    """
    from src.memory.fts5_memory import FTS5MemoryEngine
    from src.memory.sleep_cycle import SleepCycle, SleepPolicy

    ruta = tmp_path / "cuaderno.json"
    libreta = Cuaderno(path=str(ruta))
    apunte = libreta.anotar("Cerezos de Acero", "el 7/8 del puente atropella la letra")
    libreta.intentar(apunte.id, "bajar a 64 BPM", "pierde el empuje")
    antes = ruta.read_text(encoding="utf-8")

    # Un recuerdo que el olvido sí se lleva: viejo, leve y nunca recuperado, que
    # son las tres condiciones. Sirve de testigo — sin él, esta prueba pasaría
    # también con un olvido que no borrase nada, y no probaría nada.
    motor = FTS5MemoryEngine(db_path=str(tmp_path / "m.db"))
    motor.add_memory("inner_thought", "una nota cualquiera",
                     "algo leve que nadie volvió a mirar", importance=0.1)
    ciclo = SleepCycle(motor, SleepPolicy(forget_min_age_days=0.0,
                                          forget_max_importance=1.0,
                                          forget_require_unrecalled=False))
    recibo = ciclo.prune(dry_run=False)

    assert recibo.get("olvidados"), f"el olvido no borró nada; la prueba no probaría nada: {recibo}"
    assert ruta.read_text(encoding="utf-8") == antes, "el olvido tocó el cuaderno"
    assert libreta.get(apunte.id).intentos, "el intento sobrevive al ciclo de sueño"


def test_el_cuaderno_avisa_al_criterio_y_no_le_toca_un_solo_parametro(libreta, monkeypatch):
    """
    La frontera que la idea pedía expresamente: **no es un generador de
    coincidencias.**

    Un apunte puede cambiar lo que Yuki decide, pero no puede cambiarlo por
    ella: llega a `observaciones` —el canal de `criterio_base` para lo que se
    dice en voz alta antes de gastar— y ni un BPM se mueve solo.
    """
    from src.tools.criterio_musical import leer_criterio

    monkeypatch.setattr(modulo, "Cuaderno", lambda *a, **k: libreta)
    libreta.anotar("Cerezos de Acero", "el 7/8 del puente atropella la letra",
                   arte="sonora", pasaje="compás 7-9")

    letra = "Bajo el cerezo de acero\nla escarcha guarda su nombre\ny el agua no dice nada"
    sin_cuaderno = leer_criterio(letra, titulo="Cerezos de Acero")
    con_cuaderno = leer_criterio(letra, titulo="Cerezos de Acero")
    sumados = modulo.anotar_en_criterio(con_cuaderno, "Cerezos de Acero", arte="sonora")

    assert sumados == 1
    assert any("compás 7-9" in nota for nota in con_cuaderno.observaciones)
    assert "no cuajó" in " ".join(con_cuaderno.observaciones) or "Sin intentos" in " ".join(
        con_cuaderno.observaciones)
    # Y ahora lo que de verdad se protege: ningún parámetro se ha movido.
    for campo in ("bpm", "compas", "tonalidad", "escala", "duracion_segundos",
                  "registro_vocal", "secciones"):
        assert getattr(con_cuaderno, campo) == getattr(sin_cuaderno, campo), (
            f"el cuaderno movió '{campo}': es un cuaderno, no un piloto automático")
    # El aviso tiene que verse donde se dice todo lo demás, no en un log.
    assert "compás 7-9" in con_cuaderno.resumen()


def test_preguntar_por_una_cuestion_cuenta_como_releerla(libreta, monkeypatch):
    """
    «Merece una segunda lectura» es una promesa vacía si nadie sabe cuáles se
    releyeron nunca. El contador es lo que distingue un cuaderno vivo de un
    cajón, así que tiene que moverlo el camino real —el aviso al criterio—, no
    una llamada aparte que nadie hace.
    """
    from src.tools.criterio_musical import leer_criterio

    monkeypatch.setattr(modulo, "Cuaderno", lambda *a, **k: libreta)
    apunte = libreta.anotar("Cerezos de Acero", "el puente no cierra")
    assert libreta.get(apunte.id).relecturas == 0

    modulo.anotar_en_criterio(leer_criterio("una letra\ncualquiera", titulo="Cerezos de Acero"),
                              "Cerezos de Acero", arte="sonora")

    releido = libreta.get(apunte.id)
    assert releido.relecturas == 1
    assert releido.ultima_relectura is not None


def test_un_cuaderno_que_falla_no_impide_entregar_la_obra(monkeypatch, caplog):
    """
    Lo que se pierde con un cuaderno roto es un recordatorio, no una garantía.
    Dejar que tumbe una generación ya pagada sería cambiar una molestia por un
    fallo de verdad — pero callarlo del todo tampoco: queda en el log.

    El fallo se inyecta en vez de provocarse con el disco, y por dos razones que
    conviene dejar escritas. Un JSON corrupto no vale: `estado_json` lo absorbe y
    devuelve el esquema vacío, así que una prueba con un fichero roto pasa
    aunque se quite la red entera. Y un directorio sin permisos tampoco, porque
    la suite corre como root y root se los salta: pasaría igual de vacía.
    """
    from src.tools.criterio_musical import leer_criterio

    class CuadernoQueFalla:
        def abiertos(self, obra="", arte=""):
            raise OSError("el volumen no está montado")

    monkeypatch.setattr(modulo, "Cuaderno", lambda *a, **k: CuadernoQueFalla())

    criterio = leer_criterio("una letra\ncualquiera", titulo="Cerezos de Acero")
    intactas = list(criterio.observaciones)
    with caplog.at_level("WARNING"):
        sumados = modulo.anotar_en_criterio(criterio, "Cerezos de Acero", arte="sonora")

    assert sumados == 0, "no se puede dar por anotado lo que no se leyó"
    assert criterio.observaciones == intactas
    assert criterio.bpm > 0, "el criterio sigue siendo utilizable"
    # Y que no se calle: un aviso perdido en silencio es indistinguible de un
    # cuaderno vacío, y eso tranquiliza igual que una alerta rota.
    assert "no está montado" in caplog.text


def test_todos_los_criterios_del_adaptador_consultan_el_cuaderno():
    """
    Regla 8: el camino del producto, no la función suelta.

    Todo lo demás de este fichero prueba `anotar_en_criterio` llamándolo a mano.
    Eso deja pasar el fallo que de verdad importa: que el adaptador deje de
    llamarlo. Y no se arregla fijando tres sitios a mano, porque el arte que se
    añada mañana nacería sin cuaderno y nadie se enteraría.

    Así que se comprueba la **propiedad**: todo criterio que el adaptador
    construye antes de gastar pasa por el cuaderno. Lo mismo que hace
    `test_aislamiento` con `output/` en vez de fiarse de una lista.
    """
    import ast

    fuente = (Path(__file__).resolve().parent.parent
              / "src" / "adapters" / "discord_bot.py").read_text(encoding="utf-8")
    arbol = ast.parse(fuente)

    construidos, consultados = {}, set()
    for nodo in ast.walk(arbol):
        # `x = criterio_algo.leer_loquesea(...)`
        if (isinstance(nodo, ast.Assign) and isinstance(nodo.value, ast.Call)
                and isinstance(nodo.value.func, ast.Attribute)
                and isinstance(nodo.value.func.value, ast.Name)
                and nodo.value.func.value.id.startswith("criterio_")
                and nodo.value.func.attr.startswith("leer_")
                and len(nodo.targets) == 1 and isinstance(nodo.targets[0], ast.Name)):
            construidos[nodo.targets[0].id] = nodo.value.func.value.id
        # `cuaderno.anotar_en_criterio(x, ...)`
        if (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
                and nodo.func.attr == "anotar_en_criterio" and nodo.args
                and isinstance(nodo.args[0], ast.Name)):
            consultados.add(nodo.args[0].id)

    assert construidos, "no se encontró ningún criterio en el adaptador: ¿cambió la forma?"
    huerfanos = {var: mod for var, mod in construidos.items() if var not in consultados}
    assert not huerfanos, (
        f"criterios que se construyen sin mirar el cuaderno: {huerfanos}. "
        "Un arte nuevo sin cuaderno redescubre pagando lo que ya estaba escrito.")


def test_lo_cerrado_no_se_borra(libreta):
    """Una cuestión resuelta sigue enseñando: se cierra, no se olvida."""
    apunte = libreta.anotar("Cerezos de Acero", "la voz entra por encima de lo cómodo",
                            arte="voz")
    libreta.resolver(apunte.id, "transportar a Fa# y dejar el registro donde estaba")

    assert libreta.abiertos() == [], "resuelta deja de estar abierta"
    guardadas = libreta.sobre("Cerezos de Acero")
    assert len(guardadas) == 1
    assert guardadas[0].estado == "resuelto"
    assert "Fa#" in guardadas[0].resolucion


def test_resolver_sin_decir_que_funciono_pierde_lo_que_valia(libreta):
    apunte = libreta.anotar("Cerezos de Acero", "el puente no cierra")
    with pytest.raises(CuadernoError):
        libreta.resolver(apunte.id, "   ")
    assert libreta.get(apunte.id).estado == "abierto"


def test_la_misma_pieza_se_reencuentra_aunque_se_escriba_distinto(libreta):
    """
    El aviso llega por el título del encargo, que nadie escribe dos veces igual.
    Sin normalizar, «Cerezos de Acero» y «cerezos de acero» serían dos piezas y
    el cuaderno callaría justo cuando tiene algo que decir.
    """
    libreta.anotar("Cerezos de Acero", "el puente no cierra")
    assert len(libreta.abiertos(obra="cerezos de acero")) == 1
    assert len(libreta.abiertos(obra="CEREZOS DE ACERO")) == 1
    assert len(libreta.sobre("Cerezos  de  Acero")) == 1


def test_el_cuaderno_es_irremplazable_y_entra_en_la_copia(monkeypatch, tmp_path):
    """
    Una obra perdida se rehace desde su receta; «se probó 4/4 en el puente y
    dejó de ser el puente» no se deduce de ningún fichero. Si esto no entra en
    la copia, perder el disco borra lo único del oficio que no se puede repetir.
    """
    from src.tools.backup import BackupManager

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "data" / "yuki_memory.db"))
    gestor = BackupManager.from_config({})
    nombres = {Path(pieza).name for pieza in gestor._piezas()}

    assert "cuaderno_taller.json" in nombres


def test_el_gemelo_no_declara_en_verde_un_cuaderno_vacio(monkeypatch, tmp_path):
    """
    Octava invariante otra vez: la facultad existe siempre, y decir REAL sin un
    solo apunte sería declarar en verde un cajón sin estrenar.
    """
    from src.core.virtual_instance import INACTIVO, REAL, VirtualInstance

    monkeypatch.setenv("YUKI_CUADERNO_PATH", str(tmp_path / "cuaderno.json"))
    config = {"agent": {"model": {}}, "memory": {"database_path": str(tmp_path / "m.db")}}

    def capacidad():
        return next(c for c in VirtualInstance(config).capabilities if c.id == "mente.cuaderno")

    vacio = capacidad()
    assert vacio.state == INACTIVO
    assert "Biblioteca" in vacio.detail, "tiene que decir qué NO guarda, o se confunden"

    Cuaderno(path=str(tmp_path / "cuaderno.json")).anotar(
        "Cerezos de Acero", "el puente no cierra")

    assert capacidad().state == REAL


def test_las_herramientas_del_dm_no_dejan_guardar_obra_en_el_cuaderno():
    """
    Regla 6 del proyecto aplicada al arnés: si la descripción de la herramienta
    no distingue cuaderno de Biblioteca, el modelo archivará letras aquí y la
    Biblioteca dejará de ser el sitio donde está la obra.
    """
    from src.core.producer_harness import TOOLS

    nombres = {t["function"]["name"] for t in TOOLS}
    assert {"cuaderno_anotar", "cuaderno_abiertos", "cuaderno_intentar",
            "cuaderno_resolver", "cuaderno_sobre"} <= nombres

    anotar = next(t["function"] for t in TOOLS if t["function"]["name"] == "cuaderno_anotar")
    assert "Biblioteca" in anotar["description"]
    assert set(anotar["parameters"]["required"]) == {"obra", "cuestion"}
    # Y que no acepte un campo de contenido: sería la puerta por la que entraría
    # la obra que el tope de caracteres cierra por el otro lado.
    assert "contenido" not in anotar["parameters"]["properties"]
    assert "content" not in anotar["parameters"]["properties"]


def test_el_cuaderno_sobrevive_a_un_fichero_a_medio_escribir(tmp_path):
    """
    El proceso muere a mitad justo cuando se despliega. Un cuaderno corrupto
    devuelve el esquema vacío en vez de tumbar la instancia, como el resto del
    estado en JSON.
    """
    ruta = tmp_path / "cuaderno.json"
    ruta.write_text('{"apuntes": [{"id": "abc", "obra"', encoding="utf-8")

    libreta = Cuaderno(path=str(ruta))
    assert libreta.abiertos() == []

    apunte = libreta.anotar("Cerezos de Acero", "el puente no cierra")
    assert libreta.get(apunte.id) is not None
    assert json.loads(ruta.read_text(encoding="utf-8"))["apuntes"]
