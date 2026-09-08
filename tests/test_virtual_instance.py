"""
Pruebas del gemelo virtual de la instancia.

Lo que importa aquí es que el informe diga la verdad del entorno donde corre:
sin proyecto de Vertex los medios son marcadores y el crédito no se consume, y
con él dejan de serlo. Un informe que se equivoque en eso es peor que no tenerlo.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.virtual_instance import (  # noqa: E402
    BLOQUEANTE, INACTIVO, MITIGADO, REAL, SIMULADO,
    PRODUCTION_INSTANCE, VirtualInstance,
)

CONFIG = {
    "agent": {"model": {"primary_model": "upstage/solar-pro4"}},
    "provider_routing": {"enabled": True, "aggregator": "openrouter",
                         "routes": {"feed_summary": {"tier": "fast_and_cheap"}}},
    "vertex_ai": {"enabled": True, "project_id": "",
                  "media": {"image_model": "gemini-2.5-flash-image",
                            "video_model": "veo-3.1-fast-generate-001",
                            "music_model": "lyria-3-pro-preview",
                            "tts_model": "gemini-2.5-flash-tts"}},
    "model_armor": {"enabled": True},
    "memory": {"database_path": "data/yuki_memory.db"},
    "scheduler": {"timezone": "Europe/Madrid",
                  "cron_jobs": [{"name": "a", "enabled": True}, {"name": "b", "enabled": False}]},
}


@pytest.fixture(autouse=True)
def entorno_limpio(monkeypatch, tmp_path):
    for var in ("VERTEX_PROJECT_ID", "OPENROUTER_API_KEY", "DISCORD_BOT_TOKEN",
                "HONCHO_API_KEY", "FIRECRAWL_API_KEY", "GEMINI_API_KEY",
                "GOOGLE_API_KEY", "NOUS_PORTAL_MODE", "ENVIRONMENT",
                "YUKI_VIRTUAL_INSTANCE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "data" / "yuki.db"))


def _cap(instancia, cap_id):
    return next(c for c in instancia.capabilities if c.id == cap_id)


def _lim(instancia, lim_id):
    return next((lim for lim in instancia.limiters if lim.id == lim_id), None)


def test_sin_proyecto_vertex_los_medios_son_marcadores_y_es_bloqueante():
    instancia = VirtualInstance(CONFIG)

    assert _cap(instancia, "texto.vertex").state == INACTIVO
    assert _cap(instancia, "medios.video").state == SIMULADO
    limitador = _lim(instancia, "L2")
    assert limitador is not None and limitador.severity == BLOQUEANTE
    assert instancia.summary()["limitadores_bloqueantes"] == 1


def test_con_proyecto_vertex_los_medios_pasan_a_reales(monkeypatch):
    monkeypatch.setenv("VERTEX_PROJECT_ID", "yuki-prod")
    instancia = VirtualInstance(CONFIG)

    assert _cap(instancia, "texto.vertex").state == REAL
    assert _cap(instancia, "medios.musica").state == REAL
    assert _cap(instancia, "texto.model_armor").state == REAL
    assert _lim(instancia, "L2") is None


def test_clave_de_ai_studio_se_denuncia_por_facturar_fuera_del_credito(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-real-looking-key")
    instancia = VirtualInstance(CONFIG)

    limitador = _lim(instancia, "L3")
    assert limitador is not None
    assert "crédito" in limitador.impact


def test_claves_marcador_no_cuentan_como_capacidad_real(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "your_openrouter_api_key_here")
    instancia = VirtualInstance(CONFIG)

    assert _cap(instancia, "texto.openrouter").state == INACTIVO


def test_las_rutas_por_tarea_se_declaran_reales_cuando_estan_activas():
    activo = VirtualInstance(CONFIG)
    apagado = VirtualInstance({**CONFIG, "provider_routing": {"enabled": False}})

    assert _cap(activo, "texto.tiers").state == REAL
    assert _cap(apagado, "texto.tiers").state == INACTIVO


def test_la_cola_durable_cuenta_los_trabajos_reanudables(monkeypatch, tmp_path):
    from src.tools.media_jobs import MediaJobStore

    store = MediaJobStore(str(tmp_path / "data" / "media_jobs"))
    store.create(requester_id="42", order="canción", steps=[("cancion", "cancion")])

    instancia = VirtualInstance(CONFIG)

    assert instancia.pending_media_jobs() == 1
    assert "1 trabajo(s) reanudable(s)" in _cap(instancia, "medios.cola").detail
    assert _lim(instancia, "L1").status == MITIGADO


def test_la_replica_no_se_confunde_con_la_vm_de_produccion(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert VirtualInstance(CONFIG).is_production_vm

    monkeypatch.setenv("YUKI_VIRTUAL_INSTANCE", "1")
    assert not VirtualInstance(CONFIG).is_production_vm


def test_el_informe_markdown_incluye_la_ficha_de_la_instancia_y_los_limitadores():
    texto = VirtualInstance(CONFIG).render_markdown()

    assert PRODUCTION_INSTANCE["instancia"] in texto
    assert PRODUCTION_INSTANCE["zona"] in texto
    assert "## Limitadores" in texto
    assert "L2" in texto


def test_el_informe_no_filtra_secretos(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-secreto-real")
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "MTIz.token.secreto")

    texto = VirtualInstance(CONFIG).render_markdown()

    assert "sk-or-v1-secreto-real" not in texto
    assert "MTIz.token.secreto" not in texto


def test_serializacion_json_estable():
    datos = VirtualInstance(CONFIG).to_dict()

    assert set(datos) == {"instancia_produccion", "entorno", "capacidades", "limitadores", "resumen"}
    assert all({"id", "pillar", "state", "detail"} == set(c) for c in datos["capacidades"])
    assert all(lim["severity"] in {"bloqueante", "grave", "moderado"}
               for lim in datos["limitadores"])
    # Los limitadores salen ordenados por gravedad: lo que bloquea, primero.
    gravedades = [lim["severity"] for lim in datos["limitadores"]]
    assert gravedades == sorted(gravedades, key=lambda g: {"bloqueante": 0, "grave": 1, "moderado": 2}[g])


def test_el_presupuesto_activo_mitiga_el_limitador_del_video():
    con_presupuesto = {**CONFIG, "budget": {"enabled": True,
                                            "daily_limits": {"video_segundos": 120}}}
    instancia = VirtualInstance(con_presupuesto)

    assert _cap(instancia, "medios.presupuesto").state == REAL
    assert _lim(instancia, "L8").status == MITIGADO
    assert "120" in _lim(instancia, "L8").evidence


def test_sin_presupuesto_el_video_vuelve_a_estar_sin_techo():
    instancia = VirtualInstance({**CONFIG, "budget": {"enabled": False}})

    assert _cap(instancia, "medios.presupuesto").state == INACTIVO
    limitador = _lim(instancia, "L8")
    assert limitador.status == "abierto"
    assert "nada acota el gasto" in limitador.evidence


def test_la_copia_con_bucket_mitiga_la_perdida_del_disco(monkeypatch):
    monkeypatch.setenv("BACKUP_GCS_BUCKET", "yuki-respaldo")
    instancia = VirtualInstance({**CONFIG, "backup": {"bucket": "yuki-respaldo"}})

    assert _cap(instancia, "mente.respaldo").state == REAL
    assert _lim(instancia, "L7").status == MITIGADO


def test_sin_bucket_la_copia_no_protege_de_perder_el_disco(monkeypatch):
    monkeypatch.delenv("BACKUP_GCS_BUCKET", raising=False)
    instancia = VirtualInstance(CONFIG)

    assert _cap(instancia, "mente.respaldo").state == SIMULADO
    limitador = _lim(instancia, "L7")
    assert limitador.status == "abierto"
    assert "mismo disco" in limitador.evidence


def test_el_respaldo_musical_depende_de_los_binarios_de_la_imagen(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda nombre: None)
    sin_respaldo = VirtualInstance(CONFIG)

    assert _cap(sin_respaldo, "medios.musica_local").state == INACTIVO
    assert _lim(sin_respaldo, "L4").status == "abierto"

    monkeypatch.setattr("shutil.which", lambda nombre: f"/usr/bin/{nombre}")
    monkeypatch.setattr("src.tools.music_fallback.LocalMusicEngine._soundfont_disponible",
                        staticmethod(lambda: "/usr/share/sounds/sf2/FluidR3_GM.sf2"))
    con_respaldo = VirtualInstance(CONFIG)

    assert _cap(con_respaldo, "medios.musica_local").state == REAL
    assert _lim(con_respaldo, "L4").status == MITIGADO
    assert "no cantado" in _lim(con_respaldo, "L4").evidence


def test_el_salon_sin_credencial_se_denuncia_como_limitador(monkeypatch):
    monkeypatch.delenv("SALON_API_TOKEN", raising=False)
    instancia = VirtualInstance(CONFIG)

    limitador = _lim(instancia, "L10")
    assert limitador is not None and limitador.severity == "grave"
    assert "ABIERTAS" in _cap(instancia, "presencia.salon").detail


def test_con_credencial_el_salon_deja_de_ser_limitador(monkeypatch):
    monkeypatch.setenv("SALON_API_TOKEN", "secreto-del-salon")
    instancia = VirtualInstance(CONFIG)

    assert _lim(instancia, "L10") is None
    assert "con credencial" in _cap(instancia, "presencia.salon").detail


def test_el_gemelo_declara_la_sonda_de_signos_vitales(tmp_path, monkeypatch):
    """
    Saber distinguir «el proceso corre» de «Yuki hace cosas» es una capacidad.

    Sin ella el fallo más silencioso de la instancia queda invisible, así que el
    informe tiene que decir si está o no.
    """
    monkeypatch.setenv("YUKI_BLACKBOX_PATH", str(tmp_path / "bitacora.jsonl"))
    capacidad = _cap(VirtualInstance(CONFIG), "mente.pulso")

    assert capacidad.state == REAL
    assert "Signos vitales" in capacidad.detail
