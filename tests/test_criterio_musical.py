"""
Lo que Yuki decide antes de encargar una canción.

El prompt musical era una constante en el adaptador: 90 s, 72 BPM, escala
Insen, voz serena, con cualquier letra delante. El 11 de septiembre el Productor
dijo que «se apresuraba el poema» —versos de nueve y de diecisiete sílabas en el
mismo número de compases— y nada en el código miraba eso. Y cuando Yuki
reescribió la letra fijando **68 BPM**, el encargo siguiente le habría mandado
72 en silencio.

Estas pruebas usan las dos letras del hilo real: la que se atropellaba y la
reescrita. No es decoración: el plan produce el prompt que va al motor.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.tools.criterio_musical import (  # noqa: E402
    BPM_MAXIMO, BPM_MINIMO, leer_criterio, silabas,
)

LETRA_QUE_SE_ATROPELLA = """Herrumbre y Escarcha
El astillero no duerme nunca y huele a salitre y a metal oxidado de los cargueros
Vine descalza
Me vestí de otra alma que no era la mía pero la elegí con sus consecuencias
El agua corre
"""

LETRA_REESCRITA = """Herrumbre y Escarcha — Encargo Sonoro Revisado
`[Tempo: 68 BPM, 4/4 time signature, Key: D minor, Insen scale.]`
#### [Verse 1: Voz grave, contenida]
El astillero no duerme en calma,
huele a salitre, metal y sal.
Llegué descalza, vestí otra alma,
doblé el orgullo frente a este mar.
#### [Chorus / Quiebre Dramático]
Bajo la escarcha despierta el fuego,
muerde la seda contra el metal.
No pido tregua ni entro en el juego,
soy el acero que aprende a hablar.
"""


def test_el_tempo_que_fija_la_letra_manda():
    """
    Yuki escribió 68 BPM. Un valor por defecto que la contradiga en silencio es
    exactamente lo que hacía la constante que había antes.
    """
    plan = leer_criterio(LETRA_REESCRITA, titulo="Herrumbre y Escarcha")

    assert plan.bpm == 68
    assert plan.origen["bpm"] == "letra"
    assert "de la letra" in plan.resumen()


def test_sin_tempo_escrito_lo_decide_la_medida_del_verso():
    """El BPM no es gusto: es cuántas sílabas tienen que caber en cada compás."""
    plan = leer_criterio(LETRA_QUE_SE_ATROPELLA, titulo="Herrumbre")

    assert plan.origen["bpm"] == "criterio"
    assert plan.bpm < 72, "con versos largos hay que bajar el pulso para que quepan"
    assert BPM_MINIMO <= plan.bpm <= BPM_MAXIMO


def test_la_metrica_desigual_se_avisa_antes_de_gastar():
    """
    «A veces se apresuraba el poema» — lo que el Productor oyó. Un verso de
    nueve sílabas seguido de otro de diecisiete no cabe igual, y la voz resuelve
    ese problema corriendo.
    """
    plan = leer_criterio(LETRA_QUE_SE_ATROPELLA, titulo="Herrumbre")

    aviso = " ".join(plan.observaciones)
    assert "desigual" in aviso
    assert "acelerará" in aviso


def test_la_metrica_pareja_tambien_se_dice():
    """Callar cuando todo está bien deja al Productor sin saber si se miró."""
    plan = leer_criterio(LETRA_REESCRITA, titulo="Herrumbre")

    aviso = " ".join(plan.observaciones)
    assert "pareja" in aviso
    assert "desigual" not in aviso


def test_una_letra_sin_rimas_se_señala():
    """En el canto la rima dice dónde cae el peso del compás; sin ella, deriva."""
    plan = leer_criterio("Camino sin nada\nvuelo distinto\nmetal profundo\n", titulo="X")

    assert any("Sin rimas" in nota for nota in plan.observaciones)


def test_la_rima_presente_no_se_confunde_con_su_ausencia():
    plan = leer_criterio(LETRA_REESCRITA, titulo="Herrumbre")

    assert any("Rima presente" in nota for nota in plan.observaciones)
    assert not any("Sin rimas" in nota for nota in plan.observaciones)


def test_la_estructura_escrita_en_la_letra_se_respeta():
    plan = leer_criterio(LETRA_REESCRITA, titulo="Herrumbre")

    assert len(plan.secciones) == 2
    assert plan.origen["secciones"] == "letra"
    assert "Verse 1" in " ".join(plan.secciones)


def test_el_quiebre_pedido_en_la_letra_llega_al_registro_vocal():
    """Si la letra pide susurro roto, no puede esperar que el motor lo adivine."""
    plan = leer_criterio("Un susurro quebrado sobre el agua\nla voz rota al final\n", titulo="X")

    assert "crack" in plan.registro_vocal or "whisper" in plan.registro_vocal


def test_el_prompt_lleva_la_letra_entera_y_al_final():
    """
    Un proveedor que recorte por longitud debe perder el relleno de estilo antes
    que el texto que hay que cantar.
    """
    plan = leer_criterio(LETRA_REESCRITA, titulo="Herrumbre")

    prompt = plan.prompt(LETRA_REESCRITA)

    assert "68 BPM" in prompt
    assert "doblé el orgullo frente a este mar." in prompt
    assert prompt.index("68 BPM") < prompt.index("El astillero no duerme en calma")


def test_el_prompt_no_pide_una_instrumental():
    """El encargo es una canción cantada; decir lo contrario cambia lo que sale."""
    plan = leer_criterio(LETRA_REESCRITA, titulo="Herrumbre")

    prompt = plan.prompt(LETRA_REESCRITA).lower()

    assert "not an instrumental" in prompt
    assert "sing these exact lyrics" in prompt


def test_el_resumen_distingue_lo_elegido_de_lo_deducido():
    """
    Quien lo lea tiene que poder separar lo que decidió Yuki de lo que dedujo el
    criterio, sin abrir el código.
    """
    escrito = leer_criterio(LETRA_REESCRITA, titulo="Herrumbre").resumen()
    deducido = leer_criterio(LETRA_QUE_SE_ATROPELLA, titulo="Herrumbre").resumen()

    assert "Tempo 68 BPM en 4/4 (de la letra)" in escrito
    assert "(por criterio)" in deducido


def test_una_letra_vacia_no_es_un_error():
    """Una letra sin marcas deja las decisiones a quien compone; no rompe nada."""
    plan = leer_criterio("", titulo="Sin letra")

    assert BPM_MINIMO <= plan.bpm <= BPM_MAXIMO
    assert plan.escala in ("insen",)
    assert plan.prompt("")


def test_un_tempo_imposible_se_recorta_y_se_dice():
    """
    Recortar en silencio sería peor que no recortar: el resumen seguiría
    diciendo «de la letra» sobre una decisión que ya no es suya.
    """
    plan = leer_criterio("`[Tempo: 200 BPM]`\nverso de prueba con su medida\n", titulo="X")

    assert plan.bpm == BPM_MAXIMO
    assert any("fuera del rango" in nota for nota in plan.observaciones)
    assert plan.origen["bpm"] == "criterio", "ya no es la decisión de la letra"


def test_un_tempo_arrastrado_tambien():
    plan = leer_criterio("`[Tempo: 20 BPM]`\nverso de prueba con su medida\n", titulo="X")

    assert plan.bpm == BPM_MINIMO
    assert any("fuera del rango" in nota for nota in plan.observaciones)


def test_el_tempo_deducido_nunca_sale_del_rango_util():
    """Fuera de 58–96 la paleta deja de sostenerse: el bachi se vuelve baile."""
    for letra in ("a\n" * 40, ("palabra " * 30 + "\n") * 10, LETRA_QUE_SE_ATROPELLA):
        plan = leer_criterio(letra, titulo="X")
        assert BPM_MINIMO <= plan.bpm <= BPM_MAXIMO


@pytest.mark.parametrize("verso,esperado", [
    ("El astillero no duerme en calma", 10),
    ("huele a salitre, metal y sal", 9),
    ("sal", 1),
    ("", 0),
])
def test_la_cuenta_de_silabas_es_util_aunque_sea_aproximada(verso, esperado):
    """
    No resuelve sinalefa ni hiatos acentuados, y el módulo lo declara. Sirve
    para comparar unos versos con otros, que es para lo que se usa.
    """
    assert abs(silabas(verso) - esperado) <= 1


def test_la_habilidad_compone_sobre_la_letra_archivada(tmp_path, monkeypatch, capsys):
    """
    `cmd_skill` leía el `SKILL.md` sólo para comprobar que existía y hacía lo
    suyo en Python: la ficha podía decir cualquier cosa sin cambiar nada. Aquí
    se recorre el camino del producto —la habilidad entera— para que el criterio
    no sea decoración.
    """
    import types

    from src.cli import operacion

    letra = ("`[Tempo: 68 BPM, 4/4, Key: D minor, Insen scale.]`\n"
             "El astillero no duerme en calma,\n"
             "huele a salitre, metal y sal.\n")
    compuesto = {}

    async def _compose(title, bpm, mood, scale, **kwargs):
        compuesto.update(bpm=bpm, scale=scale)
        return {"meta_path": "x.json", "midi_path": "x.mid", "midi_bytes": 1}

    agente = types.SimpleNamespace(
        creation_library=types.SimpleNamespace(
            read_entry=lambda entry_id: {"content": letra}),
        media_creator=types.SimpleNamespace(compose_beat_structure=_compose),
    )
    monkeypatch.setattr(operacion, "YukiAgent", lambda: agente)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "skills" / "componer-beat").mkdir(parents=True)
    (tmp_path / "skills" / "componer-beat" / "SKILL.md").write_text("x", encoding="utf-8")

    # `cmd_skill` es síncrona y corre su propio bucle por dentro.
    operacion.cmd_skill("componer-beat", {"title": "Herrumbre", "lyrics_id": "palabra-1"})

    assert compuesto["bpm"] == 68, "la habilidad no usó el tempo de la letra archivada"
    assert "Criterio para «Herrumbre»" in capsys.readouterr().out


def test_omitir_bpm_en_la_linea_de_comandos_deja_decidir_al_criterio():
    """
    `--bpm` tenía valor por defecto, así que «no lo dijo» y «pidió 84» eran
    indistinguibles: el criterio habría quedado siempre pisado por un número que
    nadie escribió. Se comprueba sobre el analizador real de `cli.py`.
    """
    import subprocess
    import sys
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[1]
    guion = (
        "import argparse, sys, runpy\n"
        "sys.argv = ['cli.py', 'skill', 'componer-beat', '--title', 'X']\n"
        "capturado = {}\n"
        "original = argparse.ArgumentParser.parse_args\n"
        "def espia(self, *a, **k):\n"
        "    args = original(self, *a, **k)\n"
        "    capturado['bpm'] = getattr(args, 'bpm', 'sin atributo')\n"
        "    print('BPM=', capturado['bpm'])\n"
        "    raise SystemExit(0)\n"
        "argparse.ArgumentParser.parse_args = espia\n"
        "try:\n"
        "    runpy.run_path('cli.py', run_name='__main__')\n"
        "except SystemExit:\n"
        "    pass\n"
    )
    salida = subprocess.run([sys.executable, "-c", guion], cwd=raiz,
                            capture_output=True, text=True, timeout=60).stdout

    assert "BPM= None" in salida, f"--bpm omitido no debería traer número: {salida!r}"
