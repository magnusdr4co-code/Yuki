"""
Pruebas de que la suite no escribe en la instancia.

`CLAUDE.md` lo pone entre lo que no se hace, y aun así llevaba tiempo pasando:
`data/yuki_memory.db` había acumulado 887 recuerdos falsos —«Encuentro con
Productor», uno o dos por cada pasada de la suite— porque el agente resolvía la
ruta de la memoria desde `config.yaml` ignorando `DATABASE_PATH`, que es lo que
`conftest.py` redirige.

El mismo defecto tenía una cara peor fuera de las pruebas: la copia de
seguridad, la sonda de signos vitales y la comprobación de humo **sí** respetan
`DATABASE_PATH`. Una instancia con esa variable puesta habría estado escribiendo
en un sitio y respaldando y vigilando otro: una copia impecable de una base que
nadie usa.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_la_variable_de_entorno_manda_sobre_la_configuracion(monkeypatch, tmp_path):
    """
    La misma precedencia que en el resto del proyecto.

    Si el que escribe y los que leen no resuelven la ruta igual, todo lo demás
    —copias, métricas, signos vitales— habla de una base distinta.
    """
    from src.core.agent import YukiAgent

    elegida = tmp_path / "otra" / "memoria.db"
    monkeypatch.setenv("DATABASE_PATH", str(elegida))
    agente = YukiAgent()

    assert agente.memory_manager.engine.db_path == str(elegida)
    assert elegida.is_file(), "no llegó a crear la base donde dijo"


def test_todos_los_que_miran_la_memoria_miran_la_misma(monkeypatch, tmp_path):
    """
    El que escribe, el que copia y el que vigila, de acuerdo.

    Es la propiedad que faltaba, y su ausencia no da ningún error: da una copia
    perfecta de la base equivocada.
    """
    from src.core.agent import YukiAgent
    from src.core.pulse import Pulse
    from src.tools.backup import BackupManager

    elegida = tmp_path / "instancia" / "memoria.db"
    monkeypatch.setenv("DATABASE_PATH", str(elegida))
    config = {"memory": {"database_path": "data/otra_cosa.db"}}

    escribe = YukiAgent().memory_manager.engine.db_path
    copia = BackupManager.from_config(config).db_path
    vigila = Pulse(config).db_path

    assert str(escribe) == str(copia) == str(vigila) == str(elegida)


def test_la_suite_no_deja_recuerdos_en_la_base_de_la_instancia(monkeypatch, tmp_path):
    """
    Construir el agente entero no puede tocar `data/yuki_memory.db`.

    Se comprueba con la variable puesta como la pone `conftest.py`: si alguien
    vuelve a resolver la ruta ignorándola, esto lo dice.
    """
    from src.core.agent import YukiAgent

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "aislada" / "memoria.db"))
    real = os.path.join(os.path.dirname(__file__), "..", "data", "yuki_memory.db")
    antes = os.path.getsize(real) if os.path.exists(real) else None

    YukiAgent()

    if antes is not None:
        assert os.path.getsize(real) == antes, "la suite escribió en la base de la instancia"


# --- La otra variable de reubicación: dónde acaba lo que Yuki crea ---

def test_la_salida_se_reubica_entera_o_no_sirve_de_nada(monkeypatch, tmp_path):
    """
    Cinco módulos escribían en `output/…` fijo mientras uno respetaba la
    variable, y la auditoría del Artículo 50 mira la de la variable.

    Es decir: material sintético sin marcar que el auditor **no puede ver**. Eso
    ya no es ruido en las pruebas, es un agujero de cumplimiento.
    """
    from src.tools.creation_library import CreationLibrary
    from src.tools.music_fallback import LocalMusicEngine
    from src.tools.vertex_media import VertexMediaClient

    destino = tmp_path / "otra_salida"
    monkeypatch.setenv("YUKI_OUTPUT_DIR", str(destino))

    medios = VertexMediaClient.__new__(VertexMediaClient)
    VertexMediaClient.__init__(medios, project_id="", location="global")
    motor = LocalMusicEngine()
    biblioteca = CreationLibrary()

    for ruta in (medios.art_dir, medios.voice_dir, medios.music_dir, medios.video_dir,
                 motor.music_dir, str(biblioteca.output)):
        assert str(destino) in str(ruta), f"{ruta} se quedó fuera de la reubicación"


def test_la_ruta_se_resuelve_al_llamar_y_no_al_importar(monkeypatch, tmp_path):
    """
    Un `def f(dir="output/art")` congela el valor en el momento de importar el
    módulo, que es antes de que nadie haya podido reubicar nada. El síntoma es
    desconcertante: la variable funciona o no según qué se importó primero.
    """
    from src.core.rutas import salida

    monkeypatch.setenv("YUKI_OUTPUT_DIR", str(tmp_path / "primera"))
    assert str(tmp_path / "primera" / "art") == str(salida("art"))

    monkeypatch.setenv("YUKI_OUTPUT_DIR", str(tmp_path / "segunda"))
    assert str(tmp_path / "segunda" / "art") == str(salida("art"))


def test_la_precedencia_es_la_misma_para_las_dos_variables(monkeypatch, tmp_path):
    """Entorno, luego configuración, luego el valor por defecto. Sin excepciones."""
    from src.core.rutas import base_de_datos, salida

    monkeypatch.delenv("DATABASE_PATH", raising=False)
    monkeypatch.delenv("YUKI_OUTPUT_DIR", raising=False)
    assert str(base_de_datos()) == "data/yuki_memory.db"
    assert str(base_de_datos({"memory": {"database_path": "otra/mem.db"}})) == "otra/mem.db"
    assert str(salida()) == "output"

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "manda.db"))
    assert str(base_de_datos({"memory": {"database_path": "otra/mem.db"}})) == str(tmp_path / "manda.db")


def test_ningun_cliente_de_medios_escribe_en_la_salida_real(monkeypatch, tmp_path):
    """
    La propiedad, no el estado del directorio.

    La primera versión de esta prueba miraba si `output/` del repositorio tenía
    material sin marcar. Cazó la fuga, pero depende del estado ambiente: falla
    por lo que hiciera antes quien la ejecuta —a mí me falló por mis propias
    órdenes sueltas sin la variable puesta— y eso convierte una prueba en una
    lotería. Guardar el directorio real es trabajo de `scripts/smoke_check.py`,
    que lo mira donde tiene sentido: en la instancia.

    Aquí se comprueba lo que sí es determinista: con la variable puesta, ningún
    cliente de medios escribe fuera de ella.
    """
    from src.tools.nous_portal import NousPortalClient

    destino = tmp_path / "salida"
    monkeypatch.setenv("YUKI_OUTPUT_DIR", str(destino))

    portal = NousPortalClient()

    for ruta in (portal.art_dir, portal.voice_dir, portal.music_dir,
                 portal.video_dir, portal.posts_dir):
        assert str(destino) in str(ruta), f"{ruta} escribiría fuera de la reubicación"


def test_quien_escribe_y_quien_copia_miran_el_mismo_sitio(monkeypatch, tmp_path):
    """
    La propiedad que faltaba, y cuya ausencia no daba ningún error.

    `VitalState` y el perfil de Honcho escribían en `data/` fijo mientras la
    copia de seguridad los buscaba en el directorio reubicado, y la Biblioteca
    se guardaba donde dijera `YUKI_OUTPUT_DIR` mientras la copia miraba
    `output/`. En una instancia con esas variables puestas, **nada de eso
    entraba en ninguna copia**: el manifiesto los listaba como ausentes, que es
    donde nadie mira hasta el día de restaurar.
    """
    from src.core.agent import YukiAgent
    from src.tools.backup import BackupManager

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "datos" / "memoria.db"))
    monkeypatch.setenv("YUKI_OUTPUT_DIR", str(tmp_path / "salida"))

    gestor = BackupManager.from_config({})
    # Por el camino que recorre el producto, no construyendo `VitalState` suelto:
    # la primera versión de esta prueba pasaba mientras el agente seguía pasándole
    # la ruta fija a mano, que anulaba el arreglo entero.
    agente = YukiAgent()

    assert agente.vital_state.state_path == str(gestor.data_dir / "vital_state.json")
    assert str(gestor.output_dir) == str(tmp_path / "salida")
    assert str(gestor.db_path) == str(tmp_path / "datos" / "memoria.db")


def test_la_auditoria_del_articulo_50_mira_donde_se_escribe(monkeypatch, tmp_path):
    """
    Si el auditor mira `output/` fijo y los medios se escriben en otro sitio, la
    conformidad que declara es sobre un directorio vacío.
    """
    from src.core.rutas import salida
    from src.core.transparency import audit_directory

    monkeypatch.setenv("YUKI_OUTPUT_DIR", str(tmp_path / "salida"))
    (tmp_path / "salida" / "art").mkdir(parents=True)
    (tmp_path / "salida" / "art" / "sin_marca.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 40)

    auditoria = audit_directory()

    assert str(salida()) == str(tmp_path / "salida")
    assert auditoria["sin_marcar"], "el auditor no vio un fichero que sí está sin marcar"


def test_construir_el_agente_no_deja_nada_en_el_repositorio(tmp_path):
    """
    El guardián que habría cazado las dos fugas de hoy, y las siguientes.

    No comprueba una variable concreta —eso envejece en cuanto alguien añade
    estado nuevo— sino la propiedad: **construir el agente entero no puede dejar
    un solo fichero en `data/` ni en `output/` del repositorio**. Las dos fugas
    de esta tarde, 887 recuerdos y cinco ficheros de medios, se coleron cada una
    por una variable distinta que nadie había pensado en aislar.
    """
    from src.core.agent import YukiAgent

    raiz = Path(__file__).resolve().parents[1]

    def foto():
        instantanea = set()
        for carpeta in ("data", "output"):
            base = raiz / carpeta
            if base.is_dir():
                instantanea |= {p.relative_to(raiz) for p in base.rglob("*") if p.is_file()}
        return instantanea

    antes = foto()
    YukiAgent()
    nuevos = foto() - antes

    assert not nuevos, f"construir el agente dejó ficheros en el repositorio: {sorted(nuevos)}"


def test_todo_estado_durable_se_puede_reubicar(monkeypatch, tmp_path):
    """
    `CLAUDE.md` lo exige: cada estado durable tiene variable para reubicarlo.

    Sin eso no hay forma de aislar la suite —ni de mover la instancia— y el
    fichero acaba escrito donde caiga, que es como empezaron las dos fugas.
    """
    import re

    raiz = Path(__file__).resolve().parents[1]
    fuentes = "\n".join(p.read_text(encoding="utf-8") for p in (raiz / "src").rglob("*.py"))
    variables = set(re.findall(r'getenv\("(YUKI_[A-Z_]+_PATH|DATABASE_PATH|YUKI_OUTPUT_DIR)"',
                               fuentes))

    # Las que redirigen estado durable tienen que estar aisladas en la suite, o
    # bien colgar de una que sí lo esté.
    conftest = (raiz / "tests" / "conftest.py").read_text(encoding="utf-8")
    derivadas = {"YUKI_RUNTIME_CONFIG_PATH"}  # cuelga de DATABASE_PATH vía rutas.datos()

    sin_aislar = sorted(v for v in variables if v not in conftest and v not in derivadas)

    assert not sin_aislar, (
        f"estas variables redirigen estado y la suite no las aísla: {sin_aislar}")


def test_el_repositorio_no_lleva_obra_generada():
    """
    El guardián que habría cazado el commit en que se me colaron cinco.

    Al cambiar la extensión de los marcadores a `.simulado.txt` —para que un
    fichero de texto dejara de llamarse `.png`— dejaron de encajar en las reglas
    de `.gitignore`, que enumeran extensiones de medio. Se colaron en el
    siguiente commit sin que nada dijera nada.

    Lo que se comprueba no es una regla concreta de `.gitignore` sino la
    propiedad: **en `output/` no hay nada versionado salvo los marcadores de
    carpeta**. Da igual cómo se llame lo que se genere mañana.
    """
    import subprocess

    raiz = Path(__file__).resolve().parents[1]
    seguidos = subprocess.run(["git", "ls-files", "output/"], cwd=raiz,
                              capture_output=True, text=True, timeout=60).stdout.split()

    permitidos = {".gitkeep", "INDEX.md", "CANON.md"}

    # Cuatro artefactos estaban versionados **antes** de este trabajo: una
    # partitura con sus metadatos y una exportación de identidad. No los borro
    # —una vez estuve a punto de borrar ese `.mid` creyéndolo basura y era obra
    # suya— y si deben seguir ahí es decisión de quien tiene el repositorio. Se
    # nombran aquí para que consten, no para tolerar los siguientes.
    HEREDADOS = {
        "output/music/cerezos_de_acero_1787764737.json",
        "output/music/cerezos_de_acero_1787764737.mid",
        "output/music/memoria_de_metal_y_sal_1787761122.json",
        "output/yuki_identity_export_1787762950.zip",
    }

    colados = [f for f in seguidos
               if Path(f).name not in permitidos and "/Biblioteca/" not in f
               and f not in HEREDADOS]

    assert not colados, f"obra generada versionada en el repositorio: {colados}"
