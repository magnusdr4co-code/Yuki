"""
Lo que Yuki decidió sobre sí misma, puesto en la página del Salón.

El ritual de autocaracterización elegía cuatro avatares, una paleta y una
tipografía… y nadie los usaba: se generaban, se marcaban y se quedaban en el
disco. Una decisión suya sin consecuencia es lo mismo que no haberla tomado, y
este módulo es el sitio donde deja de serlo.

Vive aparte del servidor por lo mismo que `metricas.py`: no es HTTP. Son dos
preguntas —qué cara enseñar y con qué colores pintar— que se responden leyendo
el manifiesto, y que el manejador sólo coloca.
"""

from __future__ import annotations

import html
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("Yuki.WebServer")

# Dónde inyecta cada cosa la plantilla. Son comentarios HTML para que
# `salon.html` siga siendo una página válida si nadie los sustituye —que es lo
# que pasa antes de que ella se caracterice por primera vez—.
ANCLA_PALETA = "<!-- identidad:paleta -->"
ANCLA_RETRATO = "<!-- identidad:retrato -->🌸"
ANCLA_NOTA = "<!-- identidad:nota -->"

# Los papeles de la paleta que la página sabe usar. El manifiesto trae quince
# colores agrupados en cuatro familias; aquí se toman los que tienen sitio, y el
# resto se ignora en vez de pintar de cualquier manera.
#
# La forma de la paleta es `{familia: {papel: "#hex"}}` y se comprobó contra un
# manifiesto de verdad: escrita de memoria salía `{"hex":…, "role":…}` —que es
# como está el mapa de colores del alma, no como queda al diseñar el espacio— y
# con esa suposición la página se pintaba igual que antes sin que nada fallara.
PAPELES = ("background_dark", "accent_gold", "warmth_base", "soft_light",
           "kigo_primary", "text_dark")

# El valor de una familia puede no ser un color: `seasonal` lleva también el
# nombre del sekki aplicado. Un `#` delante es lo que distingue un color de una
# etiqueta, y colarla como color pintaría la página de nada.
def _es_color(valor: Any) -> bool:
    return isinstance(valor, str) and valor.startswith("#") and len(valor) in (4, 7)


def _motor():
    """El motor de identidad, sin huella: construirlo no escribe nada."""
    from ..core.self_characterization import SelfCharacterization

    return SelfCharacterization()


def retrato() -> Optional[str]:
    """La ruta del retrato que se puede enseñar, o `None`."""
    try:
        return _motor().retrato_publico()
    except Exception:
        # Que no tenga cara no puede tumbar el Salón.
        logger.exception("No pude resolver el retrato de identidad")
        return None


def _colores(manifiesto: Dict[str, Any]) -> Dict[str, str]:
    """Los colores de la paleta por papel, aplanando las familias del manifiesto."""
    paleta = (manifiesto.get("visual_identity", {}) or {}).get("color_palette") or {}
    por_papel: Dict[str, str] = {}
    for familia in paleta.values():
        if not isinstance(familia, dict):
            continue
        for papel, valor in familia.items():
            if _es_color(valor):
                por_papel.setdefault(str(papel), valor)
    return {papel: por_papel[papel] for papel in PAPELES if papel in por_papel}


def vestir(pagina: str) -> str:
    """
    Devuelve la página con su cara y sus colores, si los hay.

    Sin manifiesto no cambia nada: la plantilla trae su propio aspecto y la flor
    de siempre. Es lo correcto —una instancia recién desplegada no se ha
    caracterizado todavía— y además significa que este módulo nunca deja la
    página peor de como estaba.
    """
    try:
        motor = _motor()
        manifiesto = motor._manifest or {}
        if not manifiesto:
            return pagina

        colores = _colores(manifiesto)
        if colores:
            reglas = "\n".join(f"            --yuki-{papel.replace('_', '-')}: {valor};"
                               for papel, valor in colores.items())
            # Sólo variables: la paleta tiñe los acentos que la hoja de estilo ya
            # declara, no reescribe la página. Una identidad que rehiciera el
            # Salón entero podría dejarlo ilegible sin que nadie lo revisara.
            estilo = (
                "<style>\n        :root {\n" + reglas + "\n        }\n"
                "        .accent-gold { color: var(--yuki-accent-gold, #d4af37); }\n"
                "        body { background-color: var(--yuki-background-dark, #0d0f12);\n"
                "               color: var(--yuki-text-dark, #e2e8f0); }\n"
                "        .border-gold { border-color: var(--yuki-warmth-base, rgba(212, 175, 55, 0.3)); }\n"
                "    </style>"
            )
            pagina = pagina.replace(ANCLA_PALETA, estilo, 1)

        if motor.retrato_publico():
            estacion = (manifiesto.get("season_context", {}) or {}).get("sekki", "")
            # El origen sintético viaja con la imagen: es material generado que
            # sale hacia una persona, igual que un adjunto del DM.
            retrato_html = (
                '<img src="/identidad/avatar" alt="Retrato de Yuki, generado por ella misma"'
                ' title="Retrato generado por IA" class="w-full h-full object-cover">'
            )
            pagina = pagina.replace(ANCLA_RETRATO, retrato_html, 1)
            nota = ('<p class="text-[10px] text-stone-500">🤖 Retrato y paleta generados por '
                    'ella misma al caracterizarse'
                    + (f' para {html.escape(estacion)}' if estacion else "") + '</p>')
            pagina = pagina.replace(ANCLA_NOTA, nota, 1)
        return pagina
    except Exception:
        # La página del Salón es la puerta de entrada: si la identidad falla,
        # falla la identidad, no el Salón.
        logger.exception("No pude vestir el Salón con su identidad")
        return pagina
