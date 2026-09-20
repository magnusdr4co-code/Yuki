"""
Un módulo que nadie importa, o dice quién lo arranca, o dice que nadie lo hace.

`src/core/self_characterization.py` son mil líneas que leen SOUL.md, generan
cuatro avatares, calibran la voz y escriben un manifiesto de identidad. No lo
importa nadie: ni el agente, ni el cron, ni la CLI, ni una prueba. Y mientras
tanto `skills/autocaracterizarse/SKILL.md` prometía que el ritual corre solo al
cambiar el sekki y a mano con `/autocaracterizarse`. Las dos puertas no existen.

Es el vicio del proyecto en su forma más difícil de ver, porque no falla nunca:
un módulo grande y con buena pinta se confunde con una capacidad, y nada lo
desmiente. Un linter tampoco lo encuentra —el código es correcto, sólo que
nadie lo llama—.

Así que se comprueba la propiedad, no una lista: todo módulo de `src/` al que
no llega ningún `import` del proyecto tiene que declararlo en su propio
docstring, sea porque lo arranca algo de fuera (`Punto de entrada:`) o porque
todavía no lo arranca nadie (`Nadie lo llama todavía:`). Quien escriba el
siguiente módulo huérfano se lo encuentra aquí, y quien lo lea sabrá si corre.
"""

import ast
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

# Las dos formas de declararlo. La primera dice quién lo arranca desde fuera del
# repo; la segunda reconoce que está escrito y no corre.
DECLARACIONES = ("Punto de entrada:", "Nadie lo llama todavía:")


def _nombres_importados(fichero: Path) -> set:
    """Todo lo que un fichero nombra al importar, con relativos y `from . import x`."""
    try:
        arbol = ast.parse(fichero.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return set()
    nombres = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ImportFrom):
            nombres.update((nodo.module or "").split("."))
            # `from ..tools import receta` nombra el módulo en los alias, no en
            # `module`: mirar sólo `module` daba por huérfanos a media docena.
            nombres.update(alias.name for alias in nodo.names)
        elif isinstance(nodo, ast.Import):
            for alias in nodo.names:
                nombres.update(alias.name.split("."))
    return nombres


def _modulos_sin_importador() -> dict:
    modulos = {f.stem: f for f in RAIZ.glob("src/**/*.py") if f.name != "__init__.py"}
    llamados = set()
    fuentes = (list(RAIZ.glob("src/**/*.py")) + list(RAIZ.glob("tests/*.py"))
               + list(RAIZ.glob("scripts/*.py")) + [RAIZ / "cli.py"])
    for fichero in fuentes:
        for nombre in _nombres_importados(fichero) & set(modulos):
            if modulos[nombre] != fichero:
                llamados.add(nombre)
    return {n: r for n, r in modulos.items() if n not in llamados}


def test_un_modulo_que_nadie_importa_lo_dice_en_su_cabecera():
    huerfanos = _modulos_sin_importador()
    assert huerfanos, ("no se encontró ningún módulo sin importador: si de verdad "
                       "no queda ninguno, esta prueba sobra; revisa antes que la "
                       "detección siga funcionando")

    sin_declarar = {}
    for nombre, ruta in huerfanos.items():
        docstring = ast.get_docstring(ast.parse(ruta.read_text(encoding="utf-8"))) or ""
        if not any(marca in docstring for marca in DECLARACIONES):
            sin_declarar[nombre] = str(ruta.relative_to(RAIZ))

    assert not sin_declarar, (
        f"módulos que no llama nadie y no lo dicen: {sin_declarar}. "
        "Escribe en su docstring quién lo arranca (`Punto de entrada:`) o que "
        "todavía no lo arranca nadie (`Nadie lo llama todavía:`). Un módulo que "
        "sólo existe se confunde con una capacidad que funciona."
    )
