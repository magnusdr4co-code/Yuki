"""
Pruebas del ritual con el que Yuki decide con qué cara y qué voz se presenta.

Este módulo estuvo escrito un año sin que nadie lo importara mientras su skill
prometía que el ritual corría solo al cambiar el sekki. Al enchufarlo apareció
el fallo que explica por qué nadie lo había notado: con un fallo del proveedor
—presupuesto agotado, freno puesto, un 503— el diccionario devuelto no trae
`local_path` y el ritual entero moría con `KeyError`. Y si lo hubiera traído,
habría anotado en el manifiesto un avatar que no existe, que es peor.

Así que lo que se prueba aquí no es que el módulo funcione: es que **no aparenta
haber generado lo que no generó**, y que el camino del producto —el cron de las
04:00 y el ritual del eco— lo recorre de verdad.
"""

import asyncio
import os
import sys
import types
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.self_characterization import SelfCharacterization  # noqa: E402
from src.scheduler.tasks import AutonomousTasks  # noqa: E402

ESTACION = {"sekki": "Hakuro (Rocío Blanco)", "seasonal_kigo": "rocío blanco",
            "tea_element": "té de otoño", "micro_season_ko": "Las golondrinas parten"}


class PortalConGuion:
    """
    Doble del portal de medios que sigue un guion por llamada.

    Nada de red: cada entrada del guion es lo que el camino de imagen real
    devuelve en un caso —éxito con fichero, marcador simulado, error con motivo—.
    """

    def __init__(self, guion):
        self.guion = list(guion)
        self.llamadas = 0

    async def generate_image_frontier(self, **kwargs):
        self.llamadas += 1
        indice = min(self.llamadas - 1, len(self.guion) - 1)
        return self.guion[indice]


def _exito(tmp_path, nombre="avatar.png"):
    ruta = tmp_path / nombre
    ruta.write_bytes(b"PNG-de-mentira")
    return {"status": "success", "simulated": False, "local_path": str(ruta),
            "provider": "vertex_ai", "image_url": f"file://{ruta}",
            "marking": {"marked": True}}


def _vital():
    return types.SimpleNamespace(mood=0.5, energy=0.5, inspiration=0.4,
                                 circadian_phase="atelier", vulnerability=0.2)


def _agente(motor, portal=None, freno=None):
    """Lo justo del agente para que las dos tareas del producto corran de verdad."""
    return types.SimpleNamespace(
        self_characterization=motor,
        vital_state=_vital(),
        nous_portal=portal,
        agency_loop=types.SimpleNamespace(
            brake=freno or types.SimpleNamespace(blocked_reason=lambda acto: "")),
    )


def test_un_avatar_que_no_se_generó_no_entra_en_el_manifiesto(tmp_path):
    """
    Lo que falló consta como fallo, con su motivo, y sin ruta que aparente fichero.

    Es la regla primera del proyecto aplicada a este ritual: nada se da por
    generado si no hay fichero verificado.
    """
    portal = PortalConGuion([{"status": "error", "simulated": False,
                              "error": "Vertex devolvió 503"}])
    motor = SelfCharacterization(nous_portal=portal)

    manifiesto = asyncio.run(motor.synthesize_identity(ESTACION, _vital()))
    avatares = manifiesto["visual_identity"]["avatars"]

    assert all(a["status"] == "error" for a in avatares.values())
    assert all("local_path" not in a for a in avatares.values())
    assert all("503" in a["error"] for a in avatares.values())
    assert manifiesto["visual_identity"]["avatar_summary"]["con_fichero_verificado"] == 0
    # Y el avatar activo no existe: devolverlo haría que quien lo use adjunte
    # una ruta que no está.
    assert motor.get_active_avatar("atelier") is None


def test_un_exito_sin_fichero_en_disco_no_cuenta_como_avatar(tmp_path):
    """
    `status: success` no basta: el fichero tiene que estar.

    Un proveedor que devuelva éxito sin escribir nada —o que escriba en otro
    sitio— dejaría el manifiesto apuntando al vacío, y el fallo aparecería
    semanas después, al intentar adjuntar el retrato.
    """
    portal = PortalConGuion([{"status": "success", "simulated": False,
                              "local_path": str(tmp_path / "no_existe.png"),
                              "provider": "x", "image_url": None}])
    motor = SelfCharacterization(nous_portal=portal)

    manifiesto = asyncio.run(motor.synthesize_identity(ESTACION, _vital()))
    avatares = manifiesto["visual_identity"]["avatars"]

    assert all(a["status"] == "error" for a in avatares.values())
    assert manifiesto["visual_identity"]["avatar_summary"]["con_fichero_verificado"] == 0


def test_un_marcador_simulado_viaja_declarado_como_simulado(tmp_path):
    """Sin Vertex configurado salen marcadores; el manifiesto no los llama retratos."""
    marcador = tmp_path / "avatar.png.simulado.txt"
    marcador.write_text("SIMULADO", encoding="utf-8")
    portal = PortalConGuion([{"status": "simulated", "simulated": True,
                              "local_path": str(marcador),
                              "note": "Marcador de texto, no un medio real."}])
    motor = SelfCharacterization(nous_portal=portal)

    manifiesto = asyncio.run(motor.synthesize_identity(ESTACION, _vital()))
    avatares = manifiesto["visual_identity"]["avatars"]

    assert all(a["simulated"] is True for a in avatares.values())
    assert manifiesto["visual_identity"]["avatar_summary"]["con_fichero_verificado"] == 0
    assert "no es un medio real" in avatares["atelier"]["note"].lower() or \
           "no un medio real" in avatares["atelier"]["note"].lower()


def test_el_presupuesto_agotado_no_se_reintenta_tres_veces_mas(tmp_path):
    """
    Un «no cabe hoy» no cambia entre una variante y la siguiente.

    Insistir cuatro veces no produce ningún avatar más: llena el registro de la
    misma negativa y, el día que el límite se mida por intentos, gasta cuota.
    Los que no se piden se declaran `no_intentado`, que no es lo mismo que
    fallidos.
    """
    portal = PortalConGuion([{"status": "error", "simulated": False,
                              "error": "presupuesto agotado: imagenes 40/40",
                              "budget_exceeded": True, "unit": "imagenes"}])
    motor = SelfCharacterization(nous_portal=portal)

    manifiesto = asyncio.run(motor.synthesize_identity(ESTACION, _vital()))
    estados = manifiesto["visual_identity"]["avatar_summary"]["por_estado"]

    assert portal.llamadas == 1, "se pidió otro avatar después de quedarse sin presupuesto"
    assert estados.get("no_intentado") == 3
    assert estados.get("error") == 1


def test_lo_que_recuerda_del_ritual_coincide_con_lo_que_salio(tmp_path):
    """
    La frase que guarda en memoria no puede afirmar más de lo ocurrido.

    Sin esto, un ritual con los cuatro avatares fallidos quedaba recordado
    igual que uno completo, y ese recuerdo alimenta sus respuestas.
    """
    recuerdos = []
    motor = SelfCharacterization(
        nous_portal=PortalConGuion([{"status": "error", "simulated": False,
                                     "error": "Vertex devolvió 503"}]),
        memory_manager=types.SimpleNamespace(
            record_interaction=lambda **kw: recuerdos.append(kw)),
    )

    asyncio.run(motor.synthesize_identity(ESTACION, _vital()))

    assert len(recuerdos) == 1
    dicho = recuerdos[0]["agent_response"]
    assert "Ningún avatar llegó a existir" in dicho
    assert "503" in dicho


def test_el_cron_se_recaracteriza_al_cambiar_la_estacion_y_no_antes(tmp_path, monkeypatch):
    """
    El camino del producto: la tarea de las 04:00, con el sekki de verdad.

    Corre a diario y casi todos los días no hace nada. Que compruebe la estación
    en vez de fiarse de un calendario es lo que hace que una instancia apagada
    durante el cambio se recaracterice al volver.
    """
    portal = PortalConGuion([_exito(tmp_path)])
    motor = SelfCharacterization(nous_portal=portal)
    tareas = AutonomousTasks(_agente(motor, portal))

    monkeypatch.setattr("src.core.seasons.get_current_micro_season", lambda: ESTACION)

    primera = asyncio.run(tareas.seasonal_self_characterization())
    assert primera["season_context"]["sekki"] == ESTACION["sekki"]
    llamadas_tras_la_primera = portal.llamadas

    # Segunda pasada, misma estación: no se vuelve a gastar.
    segunda = asyncio.run(tareas.seasonal_self_characterization())
    assert segunda == {"omitido": "identidad vigente", "sekki": ESTACION["sekki"]}
    assert portal.llamadas == llamadas_tras_la_primera

    # Cambia el sekki: se rehace.
    otra = dict(ESTACION, sekki="Shubun (Equinoccio de Otoño)")
    monkeypatch.setattr("src.core.seasons.get_current_micro_season", lambda: otra)
    tercera = asyncio.run(tareas.seasonal_self_characterization())
    assert tercera["season_context"]["sekki"] == otra["sekki"]
    assert portal.llamadas > llamadas_tras_la_primera


def test_el_freno_de_iniciativa_para_la_autocaracterizacion(tmp_path, monkeypatch):
    """
    Recaracterizarse es algo que emprende ella, así que el freno la alcanza.

    Frenar no es enmudecer: esto no es responder a nadie, es iniciativa, y por
    eso cae del lado que el freno detiene. Y detenida significa **sin llamar al
    proveedor**, no llamar y descartar.
    """
    portal = PortalConGuion([_exito(tmp_path)])
    motor = SelfCharacterization(nous_portal=portal)
    freno = types.SimpleNamespace(
        blocked_reason=lambda acto: "freno de mano en «todo»" if acto == "iniciativa" else "")
    tareas = AutonomousTasks(_agente(motor, portal, freno=freno))

    monkeypatch.setattr("src.core.seasons.get_current_micro_season", lambda: ESTACION)
    resultado = asyncio.run(tareas.seasonal_self_characterization())

    assert "detenida" in resultado["omitido"]
    assert portal.llamadas == 0, "llamó al proveedor con el freno puesto"


def test_el_ritual_del_eco_ajusta_la_identidad_del_dia(tmp_path, monkeypatch):
    """
    La documentación prometía el micro-ajuste diario en el eco de las 06:30
    desde antes de que nadie lo llamara. Ahora ocurre ahí, y se comprueba por el
    camino del producto: se ejecuta `echo_ritual`, no `daily_micro_adjust`.
    """
    motor = SelfCharacterization(nous_portal=PortalConGuion([_exito(tmp_path)]))
    asyncio.run(motor.synthesize_identity(ESTACION, _vital()))

    agente = _agente(motor)
    agente.echo_ritual = types.SimpleNamespace(
        generate_echo_prompt=lambda **kw: "despierta",
        extract_impulses_from_echo=lambda **kw: [],
        record_echo=lambda texto: None)

    async def responder(**kwargs):
        return "buenos días"

    agente.generate_response = responder
    agente.will_queue = types.SimpleNamespace(add=lambda i: None, to_list=lambda: [])
    agente.vital_state.accumulated_interactions_today = 3
    agente.vital_state.accumulated_creations_today = 1
    agente.vital_state.save = lambda: None
    agente.vital_state.mood = 0.2          # amanece baja: luz de lluvia industrial

    asyncio.run(AutonomousTasks(agente).echo_ritual())

    ajustes = motor._manifest["daily_adjustments"]["adjustments"]
    assert ajustes["preferred_lighting"] == "industrial_rain"
    assert ajustes["active_prosody_mode"] == "night_mode"


def test_el_manifiesto_de_identidad_esta_declarado_y_entra_en_la_copia():
    """
    Estado durable nuevo: declarado en el inventario y dentro de la copia.

    La voz y la paleta son una elección suya y los avatares costaron crédito de
    imagen; perder el manifiesto no es perder un fichero, es volver a pagarlos.
    """
    from src.core.state_registry import build_registry
    from src.tools.backup import BackupManager

    piezas = {p.id: p for p in build_registry()}
    assert "manifiesto_identidad" in piezas
    assert piezas["manifiesto_identidad"].path.endswith("identity_manifest.json")

    copiadas = [str(p) for p in BackupManager()._piezas()]
    assert any(p.endswith("identity_manifest.json") for p in copiadas)


def test_el_cron_del_proyecto_declara_la_autocaracterizacion():
    """
    La tarea existe en `config.yaml` y el agente sabe ejecutarla.

    Una acción declarada que el agente no reconozca se omite con un aviso en el
    registro: el cron parecería configurado y no correría nunca.
    """
    import yaml

    with open("config.yaml", "r", encoding="utf-8") as fichero:
        config = yaml.safe_load(fichero)

    acciones = {j["action"] for j in config["scheduler"]["cron_jobs"] if j.get("enabled", True)}
    assert "seasonal_self_characterization" in acciones

    # Y que el agente la reconozca: `func_map` vive dentro de `_register_cron_jobs`,
    # así que se comprueba por donde se nota —el planificador con la tarea dentro—.
    from src.core.agent import YukiAgent

    agente = YukiAgent()
    assert "seasonal_self_characterization" in agente.cron.jobs
    assert hasattr(agente.tasks, "seasonal_self_characterization")
    assert agente.self_characterization is not None

def test_la_identidad_caducada_se_ve_en_las_metricas(tmp_path):
    """
    Que el ritual deje de funcionar no se nota por ausencia: corre a diario y
    casi nunca hace nada. Se nota porque la identidad se queda atrás, y eso
    tiene que salir por `/metrics` o la alerta vigilaría el vacío.
    """
    from src.web import metricas

    def familia(salida, nombre):
        for linea in salida.splitlines():
            if linea.startswith(f"yuki_{nombre} "):
                return float(linea.split()[-1])
        raise AssertionError(f"la métrica yuki_{nombre} no se expone")

    # Sin manifiesto: -1, que es «nunca se ha caracterizado» y no «caducada».
    assert familia(metricas.exposicion(), "identidad_al_dia") == -1

    motor = SelfCharacterization(nous_portal=PortalConGuion([_exito(tmp_path)]))
    asyncio.run(motor.synthesize_identity(ESTACION, _vital()))

    import src.core.seasons as seasons

    original = seasons.get_current_micro_season
    try:
        seasons.get_current_micro_season = lambda: ESTACION
        assert familia(metricas.exposicion(), "identidad_al_dia") == 1
        # Las cuatro variantes salieron con fichero en este guion.
        assert familia(metricas.exposicion(), "identidad_avatares_reales") == 4
        # Cambia la estación y nadie rehace el manifiesto: caducada.
        seasons.get_current_micro_season = lambda: dict(ESTACION, sekki="Shubun")
        assert familia(metricas.exposicion(), "identidad_al_dia") == 0
    finally:
        seasons.get_current_micro_season = original


def test_construir_el_motor_no_deja_huella_en_el_disco(tmp_path):
    """
    La sonda de métricas y el gemelo lo instancian sólo para preguntar. El
    constructor creaba `output/identity/{avatars,textures,voice_profiles}`, así
    que cada raspado de `/metrics` —cada minuto— escribía en el directorio de
    obra. Una lectura que crea carpetas no es una lectura.
    """
    import os

    salida = Path(os.environ["YUKI_OUTPUT_DIR"]) / "identity"
    SelfCharacterization()
    assert not salida.exists(), "construir el motor creó directorios de salida"

def test_sin_alma_que_leer_se_caracteriza_igual_y_no_inventa_fichero(tmp_path):
    """
    Si `SOUL.md` no está donde se dice, el ritual sigue con el extracto por
    defecto en vez de reventar a las cuatro de la mañana.

    Es una rama que antes no ejecutaba nadie y ahora corre en la instancia: una
    imagen de Docker que no copiara `SOUL.md` dejaría el cron fallando cada día
    en silencio, que es la forma en que este proyecto pierde capacidades.
    """
    motor = SelfCharacterization(soul_path=str(tmp_path / "no_hay_alma.md"),
                                 nous_portal=PortalConGuion([_exito(tmp_path)]))

    manifiesto = asyncio.run(motor.synthesize_identity(ESTACION, _vital()))

    assert manifiesto["soul_extract_summary"]["age_presence"]
    assert manifiesto["visual_identity"]["avatar_summary"]["con_fichero_verificado"] == 4


def test_sin_portal_lo_que_queda_es_la_instruccion_y_se_llama_asi(tmp_path):
    """
    Una instancia sin medios configurados no genera avatares: genera los prompts
    para pintarlos. El manifiesto tiene que decir eso y no «avatar generado»,
    que es la diferencia entre un plan y una obra.
    """
    motor = SelfCharacterization(nous_portal=None)

    manifiesto = asyncio.run(motor.synthesize_identity(ESTACION, _vital()))
    avatares = manifiesto["visual_identity"]["avatars"]

    assert all(a["status"] == "instrucciones" for a in avatares.values())
    assert manifiesto["visual_identity"]["avatar_summary"]["con_fichero_verificado"] == 0
    assert all(Path(a["instruction_path"]).is_file() for a in avatares.values())
    # Y el aviso va dentro del propio fichero, no sólo en el manifiesto.
    assert "no un avatar generado" in avatares["atelier"]["note"]

def _png(ancho: int, alto: int) -> bytes:
    """Una cabecera PNG de verdad: firma + IHDR con ancho y alto."""
    return (b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR"
            + ancho.to_bytes(4, "big") + alto.to_bytes(4, "big"))


def test_un_fallo_del_momento_se_reintenta_una_vez_y_solo_una(tmp_path):
    """
    El 20 de septiembre, en la primera ejecución real contra Vertex, tres
    avatares salieron y `kage` murió con «Gemini Image no devolvió datos de
    imagen» —un 200 sin parte de imagen, con el mismo prompt que funcionó en las
    otras tres—. Sin reintento, esa variante se pierde hasta el siguiente cambio
    de estación.

    Una vez y no más: un acto propio que falla no se reintenta en bucle.
    """
    vacio = {"status": "error", "simulated": False,
             "error": "Gemini Image no devolvió datos de imagen."}
    portal = PortalConGuion([vacio, _exito(tmp_path, "kage.png")])
    motor = SelfCharacterization(nous_portal=portal)

    manifiesto = asyncio.run(motor.synthesize_identity(ESTACION, _vital()))

    # El primero falló y el reintento salió: cuatro avatares reales, cinco
    # llamadas (una de más, la del reintento).
    assert manifiesto["visual_identity"]["avatar_summary"]["con_fichero_verificado"] == 4
    assert portal.llamadas == 5

    # Y con un fallo que se repite, exactamente dos intentos por variante: ni
    # uno más, o una avería del proveedor se convierte en una factura.
    terco = PortalConGuion([vacio])
    asyncio.run(SelfCharacterization(nous_portal=terco).synthesize_identity(ESTACION, _vital()))
    assert terco.llamadas == 8


def test_el_presupuesto_y_el_freno_no_se_reintentan(tmp_path):
    """
    Son estados, no accidentes: repetirlos no cambia la respuesta y vuelve a
    mover la reserva. Sólo se reintenta lo que puede salir distinto.
    """
    for motivo in ({"budget_exceeded": True, "error": "presupuesto agotado"},
                   {"braked": True, "error": "detenido por el freno de mano"}):
        portal = PortalConGuion([dict({"status": "error", "simulated": False}, **motivo)])
        asyncio.run(SelfCharacterization(nous_portal=portal)
                    .synthesize_identity(ESTACION, _vital()))
        assert portal.llamadas == 1, f"reintentó con {motivo}"


def test_el_remate_del_ritual_cuenta_los_que_existen(tmp_path, caplog):
    """
    El cierre decía «Avatares: 4 variantes» con tres ficheros en disco y el
    cuarto fallado. El resumen de arriba lo decía bien y el remate no, que es la
    peor combinación: la línea que queda en el log es la última.
    """
    import logging

    fallo = {"status": "error", "simulated": False, "error": "503 del proveedor"}
    # Tres ficheros y una variante que falla en los dos intentos.
    portal = PortalConGuion([_exito(tmp_path, "a.png")] * 3 + [fallo, fallo])
    motor = SelfCharacterization(nous_portal=portal)

    with caplog.at_level(logging.INFO, logger="Yuki.SelfCharacterization"):
        asyncio.run(motor.synthesize_identity(ESTACION, _vital()))

    remate = [m for m in caplog.messages if "COMPLETADA" in m]
    assert remate, "el ritual no dejó constancia de haber terminado"
    assert "3 de 4 con fichero" in remate[-1]


def test_la_proporcion_declarada_es_la_que_tiene_el_fichero(tmp_path):
    """
    El avatar estacional se pide en 16:9 y Gemini devuelve un cuadrado: la
    proporción viajaba sólo en la rama de Imagen, así que la receta y el
    manifiesto anotaban 16:9 sobre un fichero 1:1. Una obra no se puede rehacer
    desde una receta que miente sobre su encuadre.
    """
    from src.tools.vertex_media import _proporcion_del_png

    cuadrado = tmp_path / "cuadrado.png"
    cuadrado.write_bytes(_png(1024, 1024))
    panoramico = tmp_path / "ancho.png"
    panoramico.write_bytes(_png(1920, 1080))
    roto = tmp_path / "no_es_png.png"
    roto.write_bytes(b"esto no es un PNG")

    assert _proporcion_del_png(str(cuadrado)) == "1:1"
    assert _proporcion_del_png(str(panoramico)) == "16:9"
    # Lo que no se puede medir no se inventa.
    assert _proporcion_del_png(str(roto)) is None
    assert _proporcion_del_png(str(tmp_path / "no_existe.png")) is None

def test_la_voz_elegida_nombra_una_del_proveedor_y_no_una_inventada(tmp_path):
    """
    `yuki_night_contralto` es un nombre suyo, no del catálogo de Gemini TTS: la
    calibración lo anunciaba como voz mientras la síntesis usaba `Aoede` pasara
    lo que pasara. Ahora cada manera de hablar declara con qué voz real se
    sintetiza, el manifiesto guarda las dos y `voz_del_proveedor()` es lo que se
    le pasa al sintetizador.
    """
    motor = SelfCharacterization(nous_portal=PortalConGuion([_exito(tmp_path)]))

    manifiesto = asyncio.run(motor.synthesize_identity(ESTACION, _vital()))
    vocal = manifiesto["vocal_identity"]

    assert vocal["provider_voice"], "el manifiesto no dice con qué voz se sintetiza"
    assert vocal["provider_voice"] != vocal["selected_voice_id"], (
        "la voz del proveedor no puede ser el nombre interno: eso es lo que se "
        "estaba anunciando como voz sin serlo")
    assert motor.voz_del_proveedor() == vocal["provider_voice"]
    # Todas las candidatas declaran una, o elegir cualquiera de ellas volvería a
    # dejar la síntesis sin voz que pasar.
    assert all(c.get("provider_voice")
               for c in SelfCharacterization.VOICE_CANDIDATES.values())

    # Y el razonamiento lo dice en voz alta, que es lo que lee el Productor.
    assert vocal["provider_voice"] in vocal["selection_reasoning"]


def test_sin_manifiesto_no_hay_voz_que_imponer():
    """Antes de caracterizarse no hay elección: manda la de `config.yaml`."""
    assert SelfCharacterization().voz_del_proveedor() is None
