"""
Pruebas de la consola del Productor: los comandos del DM.

Es la superficie de mando de una instancia que habla con personas reales, y
estaba casi entera sin pruebas: cinco en el adaptador, ninguna sobre los
comandos. Entre ellos está `!olvidar`, que es **irreversible por definición** —un
olvido que se pueda deshacer no es un olvido—, y el freno, que es lo que se usa
cuando ya no hay tiempo de desplegar nada.

Lo que se protege aquí no es que las cadenas de texto no cambien, sino las tres
propiedades que harían daño si se rompieran: que sin `confirmar` no se borre
nada, que un DM no autenticado no llegue a ningún comando, y que frenar no sea
enmudecer.
"""

import asyncio
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.adapters.discord_bot import DiscordAdapter  # noqa: E402
from src.core.brake import Brake  # noqa: E402


@pytest.fixture
def consola(tmp_path, monkeypatch):
    """
    Un adaptador sin Discord.

    El constructor real abre un cliente de gateway; aquí sólo interesan los
    manejadores, así que se monta la instancia con lo justo. Una prueba que
    necesite red para comprobar un `if` se deja de ejecutar.
    """
    monkeypatch.delenv("YUKI_FRENO", raising=False)
    monkeypatch.setenv("YUKI_FRENO_PATH", str(tmp_path / "freno.json"))

    adaptador = DiscordAdapter.__new__(DiscordAdapter)
    adaptador.brake = Brake(path=str(tmp_path / "freno.json"))
    adaptador.paired_producer_ids = {"42"}
    adaptador.pairing_path = tmp_path / "pairing.json"
    adaptador.pairing_path.write_text('{"paired_ids": ["42"]}', encoding="utf-8")
    adaptador.agent = types.SimpleNamespace()
    return adaptador


# --- El derecho de supresión: lo único irreversible de toda la consola ---

class RegistroFalso:
    """Doble del registro de estado que anota si alguien le pidió borrar."""

    borrados = []

    def subject_export(self, sujeto):
        return {"recuerdos_total": 7, "declaraciones_de_naturaleza": 1, "sujeto": sujeto}

    def subject_forget(self, sujeto, actor="", reason=""):
        if sujeto in ("general", "yuki_internal"):
            raise ValueError(f"`{sujeto}` no es una persona: no se puede olvidar")
        RegistroFalso.borrados.append((sujeto, actor, reason))
        return {"recuerdos_borrados": 7, "declaraciones_borradas": 1}


@pytest.fixture
def registro(monkeypatch):
    RegistroFalso.borrados = []
    monkeypatch.setattr("src.core.state_registry.StateRegistry", RegistroFalso)
    return RegistroFalso


def test_olvidar_sin_confirmar_no_borra_absolutamente_nada(consola, registro):
    """
    La propiedad que justifica el comando entero.

    La autenticación del DM no basta para un dedo que resbala: sin la palabra
    `confirmar` el comando sólo cuenta qué desaparecería.
    """
    respuesta = consola._handle_forget_command("!olvidar 99887766", "productor")

    assert registro.borrados == []
    assert "7 recuerdo(s)" in respuesta
    assert "irreversible" in respuesta.lower()
    assert "confirmar" in respuesta


def test_olvidar_con_confirmar_borra_y_da_recibo(consola, registro):
    respuesta = consola._handle_forget_command(
        "!olvidar 99887766 confirmar me lo pidió por escrito", "productor")

    assert registro.borrados == [("99887766", "productor", "me lo pidió por escrito")]
    assert "7 recuerdo(s)" in respuesta
    # Queda constancia de la operación, no de lo borrado.
    assert "constancia de la operación" in respuesta


def test_olvidar_sin_sujeto_no_puede_interpretarse_como_borrarlo_todo(consola, registro):
    """Un comando a medias nunca es una orden amplia: es un error de uso."""
    respuesta = consola._handle_forget_command("!olvidar", "productor")

    assert registro.borrados == []
    assert "Uso:" in respuesta


def test_lo_que_no_es_una_persona_no_se_olvida(consola, registro):
    """
    `general` y `yuki_internal` no son nadie: son la memoria de Yuki.

    Borrarlos con el derecho de supresión de un tercero sería vaciarla a ella.
    """
    respuesta = consola._handle_forget_command("!olvidar general confirmar", "productor")

    assert registro.borrados == []
    assert respuesta.startswith("❌")


def test_un_fallo_al_borrar_no_se_presenta_como_borrado(consola, monkeypatch):
    """No se da por borrado lo que no consta: es la especificación del proyecto."""
    class Rota(RegistroFalso):
        def subject_forget(self, sujeto, actor="", reason=""):
            raise RuntimeError("la base está bloqueada")

    monkeypatch.setattr("src.core.state_registry.StateRegistry", Rota)

    respuesta = consola._handle_forget_command("!olvidar 5 confirmar", "productor")

    assert respuesta.startswith("❌")
    assert "No doy por borrado" in respuesta


# --- El freno: la palanca de cuando ya no hay tiempo ---

def test_frenar_no_es_enmudecer_y_se_dice_al_frenar(consola):
    """
    La invariante, en el sitio donde alguien la lee con prisa.

    Quien tira del freno a las tres de la mañana quiere seguir pudiendo
    preguntarle qué pasó. Que el propio mensaje lo diga evita el siguiente
    minuto de duda.
    """
    respuesta = consola._handle_brake_command("!freno todo incidente de gasto", "productor")

    assert consola.brake.state().nivel == "todo"
    assert "enmudecerme no es frenarme" in respuesta


def test_el_freno_se_pone_con_una_sola_palabra(consola):
    """El momento de usarlo es el de menos paciencia que hay."""
    consola._handle_brake_command("!freno medios", "productor")

    assert consola.brake.state().nivel == "medios"
    assert not consola.brake.permits("medios")
    assert consola.brake.permits("iniciativa"), "frenar medios no frena el pensar"


def test_el_freno_con_minutos_se_suelta_solo(consola):
    respuesta = consola._handle_brake_command("!freno todo 30 mientras miro el gasto", "productor")

    assert "30 min" in respuesta
    assert consola.brake.state().activo


def test_soltar_el_freno_del_operador_no_esta_en_manos_del_dm(consola, monkeypatch):
    """
    La palanca de entorno manda sobre el DM, y se dice cuando ocurre.

    Si el DM pudiera soltar lo que puso el operador, el freno no serviría para
    contener a nadie —incluida ella—.
    """
    monkeypatch.setenv("YUKI_FRENO", "todo")

    respuesta = consola._handle_brake_command("!freno soltar", "productor")

    assert consola.brake.state().activo
    assert "eso no lo controlo yo" in respuesta


def test_un_nivel_inventado_se_rechaza_sin_tocar_el_freno(consola):
    respuesta = consola._handle_brake_command("!freno catastrofe", "productor")

    assert respuesta.startswith("❌")
    assert not consola.brake.state().activo


# --- La puerta: nada de lo anterior existe para quien no está emparejado ---

def test_un_dm_no_emparejado_no_llega_a_ningun_comando(consola):
    """
    La puerta se comprueba **antes** de mirar el contenido.

    Un `!olvidar` de un desconocido no puede llegar ni a la rama que consulta
    qué se borraría.
    """
    respuesta = asyncio.run(consola.handle_producer_dm(
        author_id="12345", author_name="alguien", content="!olvidar 42 confirmar"))

    assert respuesta.startswith("🔒")


def test_estar_en_la_lista_no_basta_sin_emparejamiento(consola):
    """
    Dos condiciones, no una: la lista de IDs y el emparejamiento en disco.

    La lista viaja en una variable de entorno; el emparejamiento es un acto
    deliberado que quedó escrito. Que baste una sola convertiría un despliegue
    mal configurado en una puerta abierta.
    """
    consola.pairing_path.unlink()

    respuesta = asyncio.run(consola.handle_producer_dm(
        author_id="42", author_name="productor", content="!estado"))

    assert respuesta.startswith("🔒")
