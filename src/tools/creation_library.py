"""Biblioteca persistente: copias verificadas, canon e índice por tipo/estado."""
import hashlib
import json
import logging
import shutil
import threading
import time
from ..core.rutas import salida
from . import receta as _receta
from pathlib import Path

KINDS = ("sonora", "visual", "palabra", "audiovisual")
STATES = ("semilla", "en-desarrollo", "terminado")
logger = logging.getLogger("Yuki.Biblioteca")

EXTENSIONS = {
    ".mid": "sonora", ".midi": "sonora", ".mp3": "sonora",
    ".wav": "sonora", ".ogg": "sonora", ".flac": "sonora",
    ".png": "visual", ".jpg": "visual", ".jpeg": "visual", ".webp": "visual",
    ".mp4": "audiovisual", ".webm": "audiovisual", ".md": "palabra",
}
CANON = """# Biblioteca de Yuki

Organización canónica aprobada por el Productor: tipo de creación / estado.
- sonora: música, voz y partituras (el MIDI es partitura, no canción cantada).
- visual: imágenes e ilustraciones.
- palabra: poemas, letras y textos.
- audiovisual: vídeos.
- semilla: ideas en gestación; en-desarrollo: taller; terminado: aprobado por el Productor.

Los archivos importados empiezan en en-desarrollo: publicado no significa terminado.
Los originales se conservan. El índice registra procedencia y SHA-256.
La existencia de un archivo no demuestra calidad ni que contenga una obra completa.
Los marcadores simulados no se catalogan como medios reales.
"""


class CreationLibrary:
    def __init__(self, output_dir=None):
        self.output = Path(output_dir or salida()).resolve()
        self.root = self.output / "Biblioteca"
        self._lock = threading.RLock()

    def _path(self, relative):
        path = self.root / relative
        if not path.resolve().is_relative_to(self.output) or not path.resolve().is_relative_to(self.root.resolve()):
            raise ValueError("Ruta fuera de la Biblioteca")
        return path

    def _load(self):
        path = self._path("index.json")
        return json.loads(path.read_text()) if path.exists() else {}

    def _commit(self, entries):
        # El índice se reemplaza atómicamente, nunca un archivo original.
        temp = self._path("index.json.tmp")
        temp.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self._path("index.json"))
        lines = ["# Índice de la Biblioteca", "", "Tipo | Estado | Pieza | Archivo", "--- | --- | --- | ---"]
        for item in entries.values():
            lines.append(f"{item['kind']} | {item['state']} | {item['id']} | {item['path']}")
        self._path("INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def initialize(self):
        for kind in KINDS:
            for state in STATES:
                self._path(f"{kind}/{state}").mkdir(parents=True, exist_ok=True)
        canon = self._path("CANON.md")
        if not canon.exists():
            canon.write_text(CANON, encoding="utf-8")

    def _store(self, data, kind, state, suffix, source, title):
        if kind not in KINDS or state not in STATES:
            raise ValueError("Tipo o estado no admitido")
        if len(data) > 100 * 1024 * 1024:
            raise ValueError("Archivo demasiado grande")
        self.initialize()
        digest = hashlib.sha256(data).hexdigest()
        key = f"{kind}-{digest[:20]}"
        entries = self._load()
        if key in entries:
            item = entries[key]
            if hashlib.sha256(self._path(item['path']).read_bytes()).hexdigest() != item['sha256']:
                raise ValueError("La copia archivada no coincide con su hash")
            return item
        relative = f"{kind}/{state}/{key}{suffix}"
        destination = self._path(relative)
        with destination.open("xb") as handle:
            handle.write(data)
        if hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
            raise IOError("Verificación de copia fallida")
        # `created_at` faltaba, y sin él no había forma de saber cuál es la obra
        # más reciente: el encargo multimedia cogía la primera que casara por
        # palabra clave, así que una letra nueva nunca llegaba a usarse por más
        # veces que se pidiera. Las entradas anteriores no lo tienen; quien
        # ordene por recencia debe caer a la fecha del fichero.
        item = dict(id=key, kind=kind, state=state, path=relative, source=source,
                    title=title[:200], sha256=digest, bytes=len(data),
                    created_at=time.time())
        entries[key] = item
        self._commit(entries)
        return item

    def inventory(self):
        with self._lock:
            self.initialize()
            errors = []
            imported = 0
            # Sólo artefactos de producción, nunca data/, credenciales o configuración.
            for folder in ("music", "art", "voice", "posts", "video"):
                for path in sorted((self.output / folder).rglob("*"))[:1000]:
                    if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
                        continue
                    if not path.resolve().is_relative_to(self.output) or path.is_symlink():
                        errors.append("Archivo enlazado fuera del alcance omitido")
                        continue
                    if path.stat().st_size > 100 * 1024 * 1024:
                        errors.append(f"Archivo demasiado grande: {path.name}")
                        continue
                    data = path.read_bytes()
                    if not data or any(marker in data[:512].upper() for marker in (b"SIMULADO", b"SIMULATED", b"MOCK", b"PLACEHOLDER")):
                        continue
                    item = self._store(data, EXTENSIONS[path.suffix.lower()], "en-desarrollo",
                                       path.suffix.lower(), str(path.relative_to(self.output)),
                                       path.stem)
                    self._adjuntar_receta(path, item)
                    imported += 1
            self._commit(self._load())
            return {"checked_files": imported, "total": len(self._load()), "errors": errors,
                    "index": str(salida("Biblioteca/INDEX.md")),
                    "canon": str(salida("Biblioteca/CANON.md"))}

    def list_entries(self):
        """
        El inventario, **lo más reciente primero**.

        Importa por el recorte a cien: en el orden de inserción, pasadas las cien
        obras el recorte se comía justo las nuevas, que son las que alguien
        acaba de guardar y quiere usar.
        """
        with self._lock:
            entries = sorted(self._load().values(), key=self._cuando, reverse=True)
            return {"total": len(entries), "entries": entries[:100], "limited": len(entries) > 100}

    def known_ids(self) -> set:
        """
        Todos los identificadores archivados, sin el recorte de `list_entries`.

        Existe para cotejar citas: con la lista recortada a cien, una obra
        antigua citada correctamente parecería inventada, y un cotejo que da
        falsos positivos deja de leerse a los tres avisos.
        """
        with self._lock:
            return set(self._load().keys())

    def _cuando(self, item) -> float:
        """Cuándo se archivó. Las entradas viejas no lo llevan: vale su fichero."""
        marca = item.get("created_at")
        if isinstance(marca, (int, float)) and marca > 0:
            return float(marca)
        try:
            return self._path(item["path"]).stat().st_mtime
        except OSError:
            return 0.0

    def save_text(self, title, content, state="en-desarrollo", source="producer_dm"):
        if not content or len(content) > 100_000:
            raise ValueError("Texto vacío o demasiado extenso")
        with self._lock:
            return self._store(content.encode("utf-8"), "palabra", state, ".md", source, title)

    def _adjuntar_receta(self, origen, item):
        """
        La receta viaja con la obra al archivarla.

        Si se queda en `output/` se pierde en la primera limpieza, y con ella la
        única forma de rehacer una pista que salió bien. No se importa como obra
        aparte —no lo es— sino como acompañante de la suya, igual que el
        manifiesto del Artículo 50 acompaña al fichero marcado.
        """
        fuente = origen.parent / f"{origen.name}{_receta.SUFIJO}"
        if not fuente.is_file():
            return
        relativa = f"{item['path']}{_receta.SUFIJO}"
        try:
            self._path(relativa).write_bytes(fuente.read_bytes())
        except OSError as exc:
            logger.warning("No pude archivar la receta de %s: %s", origen.name, type(exc).__name__)
            return
        entries = self._load()
        if item["id"] in entries:
            entries[item["id"]]["receta"] = relativa
            self._commit(entries)

    def read_entry(self, entry_id):
        with self._lock:
            item = self._load()[entry_id]
            result = dict(item)
            if item["kind"] == "palabra":
                result["content"] = self._path(item["path"]).read_text(encoding="utf-8")[:8000]
            if item.get("receta"):
                # Con qué se hizo, para poder rehacerla. Vacío si la receta se
                # perdió: decir que no está es mejor que devolver media.
                result["receta_datos"] = _receta.leer(
                    str(self._path(item["receta"])).removesuffix(_receta.SUFIJO))
            return result

    def set_status(self, entry_id, state):
        if state not in STATES:
            raise ValueError("Estado no admitido")
        with self._lock:
            entries = self._load()
            item = entries[entry_id]
            old = self._path(item["path"])
            new_relative = f"{item['kind']}/{state}/{old.name}"
            new = self._path(new_relative)
            if old != new:
                if new.exists() and new.read_bytes() != old.read_bytes():
                    raise ValueError("Conflicto: el destino ya contiene otra versión")
                if not new.exists():
                    shutil.copyfile(old, new)
            item.update(state=state, path=new_relative)
            self._commit(entries)
            return item
