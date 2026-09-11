"""
«Genera el archivo de audio con esa estructura» no disparaba nada.

El 11 de septiembre el Productor pidió la canción con esa frase y el encargo no
se reconoció: cayó al arnés del DM —que no tiene herramienta de medios, y no la
tiene a propósito— y Yuki acabó explicando una arquitectura falsa para
justificar por qué no podía. Llegó a decir que la pista anterior «no se ejecutó
desde este chat» cuando el acuse de ese mismo encargo estaba cuatro mensajes más
arriba, en ese chat.

La orden era inequívoca. Lo que fallaba era leerla: el detector exigía además
una palabra de entrega —«pásamelo», «aquí»—, y nadie dice «genera el mp3» para
no recibirlo.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.adapters.discord_intents import looks_like_media_delivery_request as _encargo  # noqa: E402


@pytest.mark.parametrize("pedido", [
    "Genera el archivo de audio con esa estructura",
    "genera la cancion",
    "crea el mp3 con la nueva letra",
    "hazme la pista",
    "produce el audio con la letra revisada",
    "saca una canción completa y pásamela por aquí",
])
def test_una_orden_de_producir_medios_se_reconoce(pedido):
    assert _encargo(pedido), f"orden no reconocida: {pedido!r}"


@pytest.mark.parametrize("frase", [
    "me gusta mucho la música que haces",
    "hablemos de la canción que hiciste ayer",
    "¿algún día podrías generar la canción?",
    "¿podrías hacer un vídeo?",
    "¿sería posible generar el audio?",
])
def test_hablar_de_medios_no_los_encarga(frase):
    """
    La contrapartida de relajar la exigencia de «pásamelo»: una hipótesis no
    puede gastar crédito. El vídeo se factura por segundo.
    """
    assert not _encargo(frase), f"esto no era un encargo: {frase!r}"


def test_el_mensaje_real_del_incidente_se_reconoce():
    """El literal del hilo, para que la prueba no dependa de mi paráfrasis."""
    assert _encargo("Genera el archivo de audio con esa estructura")
    assert _encargo(
        "Con alguno de los poemas que tienes preparados, haz una partitura para un modelo "
        "de audio, e intenta sacar una cancion completa y pasamela por aqui")
