"""
Pruebas de la cola durable de trabajos multimedia.

Lo que se protege aquí es la propiedad que motivó el módulo: un reinicio no
puede perder un encargo ni volver a pagar un paso ya generado.
"""

import json
from pathlib import Path

import pytest

from src.tools.media_jobs import (
    MAX_INTENTOS_POR_PASO, ABANDONADO, EN_CURSO, TERMINADO,
    MediaJob, MediaJobStore, describe_job,
)


PASOS = [("cancion", "cancion"), ("clip_1", "clip"), ("montaje", "montaje")]


@pytest.fixture
def store(tmp_path):
    return MediaJobStore(str(tmp_path / "media_jobs"))


def test_trabajo_creado_se_persiste_antes_de_gastar(store, tmp_path):
    job = store.create(requester_id="42", order="haz la canción", channel_id="99", steps=PASOS)

    fichero = Path(store.root) / f"{job.id}.json"
    assert fichero.is_file()
    datos = json.loads(fichero.read_text(encoding="utf-8"))
    assert [p["id"] for p in datos["steps"]] == ["cancion", "clip_1", "montaje"]
    assert datos["status"] == EN_CURSO


def test_reinicio_recupera_el_trabajo_a_medias(store, tmp_path):
    job = store.create(requester_id="42", order="canción y vídeo", steps=PASOS)
    audio = tmp_path / "cancion.mp3"
    audio.write_bytes(b"audio")
    job.step("cancion").mark_done(str(audio))
    store.save(job)

    # Un proceso nuevo: sólo tiene el disco.
    otro = MediaJobStore(str(store.root))
    reanudables = otro.resumable()

    assert len(reanudables) == 1
    recuperado = reanudables[0]
    assert recuperado.id == job.id
    assert recuperado.step("cancion").is_done()
    assert [p.id for p in recuperado.pending_steps()] == ["clip_1", "montaje"]


def test_paso_hecho_sin_fichero_deja_de_contar_como_hecho(store, tmp_path):
    """El estado no basta: si el binario ya no está, hay que rehacerlo."""
    job = store.create(requester_id="42", order="x", steps=PASOS)
    audio = tmp_path / "cancion.mp3"
    audio.write_bytes(b"audio")
    job.step("cancion").mark_done(str(audio))
    store.save(job)
    audio.unlink()

    recuperado = MediaJobStore(str(store.root)).get(job.id)
    assert not recuperado.step("cancion").is_done()
    assert "cancion" in [p.id for p in recuperado.pending_steps()]


def test_paso_agotado_no_se_reintenta_indefinidamente(store):
    job = store.create(requester_id="42", order="x", steps=PASOS)
    paso = job.step("clip_1")
    paso.attempts = MAX_INTENTOS_POR_PASO
    paso.mark_failed("Veo devolvió 429")
    store.save(job)

    recuperado = MediaJobStore(str(store.root)).get(job.id)
    assert recuperado.step("clip_1").exhausted()
    assert "clip_1" not in [p.id for p in recuperado.pending_steps()]


def test_trabajo_sin_pasos_pendientes_se_cierra_al_listarlo(store, tmp_path):
    job = store.create(requester_id="42", order="x", steps=[("entrega", "entrega")])
    job.step("entrega").mark_done()
    store.save(job)

    assert MediaJobStore(str(store.root)).resumable() == []
    assert store.get(job.id).status == TERMINADO


def test_abandonar_marca_los_pasos_pendientes_con_el_motivo(store):
    job = store.create(requester_id="42", order="x", steps=PASOS)
    store.abandon(job, "no se pudo recuperar el DM de entrega")

    recuperado = store.get(job.id)
    assert recuperado.status == ABANDONADO
    assert recuperado.step("cancion").error == "no se pudo recuperar el DM de entrega"
    assert store.resumable() == []


def test_filtrado_por_solicitante(store):
    store.create(requester_id="42", order="x", steps=PASOS)
    store.create(requester_id="7", order="y", steps=PASOS)

    assert len(store.resumable(requester_id="42")) == 1
    assert len(store.resumable()) == 2


def test_escritura_atomica_no_deja_json_a_medias(store, tmp_path):
    job = store.create(requester_id="42", order="x", steps=PASOS)
    for _ in range(5):
        job.step("cancion").attempts += 1
        store.save(job)

    assert not list(Path(store.root).glob("*.tmp"))
    assert json.loads((Path(store.root) / f"{job.id}.json").read_text(encoding="utf-8"))


def test_purga_solo_toca_trabajos_cerrados(store):
    vivo = store.create(requester_id="42", order="x", steps=PASOS)
    cerrado = store.create(requester_id="42", order="y", steps=PASOS)
    store.finish(cerrado)
    # `save` refresca `updated_at`, así que el envejecido se escribe a mano.
    envejecido = {**store.get(cerrado.id).to_dict(), "updated_at": 0}
    (Path(store.root) / f"{cerrado.id}.json").write_text(
        json.dumps(envejecido, ensure_ascii=False), encoding="utf-8"
    )

    assert store.purge(older_than_days=1) == 1
    assert store.get(vivo.id) is not None
    assert store.get(cerrado.id) is None


def test_resumen_no_promete_lo_que_no_hay(store, tmp_path):
    job = store.create(requester_id="42", order="x", steps=PASOS)
    fichero = tmp_path / "clip.mp4"
    fichero.write_bytes(b"video")
    job.step("clip_1").mark_done(str(fichero))
    job.step("cancion").mark_failed("Lyria no devolvió audio")

    texto = describe_job(job)
    assert job.id in texto
    assert "1/3 pasos verificados" in texto
    assert "1 con fallo registrado" in texto


def test_json_corrupto_se_ignora_sin_romper_el_arranque(store):
    (Path(store.root) / "roto.json").write_text("{ no es json", encoding="utf-8")
    assert store.list_jobs() == []
    assert store.resumable() == []


def test_from_dict_tolera_campos_ausentes():
    job = MediaJob.from_dict({"steps": [{"id": "a", "kind": "clip"}]})
    assert job.status == EN_CURSO
    assert job.step("a").kind == "clip"
