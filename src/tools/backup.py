"""
Copia de la memoria y del canon fuera de la instancia.

El limitador L7: `yuki_memory.db`, la Biblioteca y el estado vital viven en un
solo disco, en una sola zona. Los medios se regeneran —cuestan crédito, pero se
rehacen—; la memoria de Yuki y las obras archivadas, no. Una zona caída se las
lleva y con ellas la continuidad del personaje, que es el proyecto entero.

Dos detalles que deciden si una copia sirve de algo:

1. **La base de datos no se copia como fichero.** SQLite en WAL puede tener
   páginas a medias fuera del `.db` en el momento del `cp`, así que un tar de un
   proceso vivo produce copias que restauran corruptas justo cuando hacen falta.
   Aquí se usa la API `Connection.backup()`, que toma una instantánea coherente
   con el escritor en marcha.
2. **La copia se verifica antes de darla por buena**: `PRAGMA integrity_check`
   sobre el fichero resultante. Una copia que nadie ha abierto no es una copia.

La subida a Cloud Storage es opcional y explícita (`BACKUP_GCS_BUCKET`): sin
bucket declarado el archivo queda en disco y **se dice**, en vez de sugerir que
está a salvo fuera de la instancia.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("Yuki.Backup")

# Copias locales que se conservan. El disco de la e2-small es pequeño y una
# copia de hace tres semanas ya no responde a ninguna pregunta útil.
COPIAS_RETENIDAS = 7

GCS_UPLOAD_URL = "https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o"
GCS_TIMEOUT = 120.0


@dataclass
class BackupResult:
    """Qué se copió, dónde quedó y si salió de la instancia."""

    status: str
    path: Optional[str] = None
    bytes: int = 0
    included: Optional[List[str]] = None
    skipped: Optional[List[str]] = None
    integrity: str = ""
    remote_uri: Optional[str] = None
    remote_error: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in (None, "", [])}


def _copia_coherente_de_sqlite(origen: Path, destino: Path) -> str:
    """
    Instantánea coherente de la base y su comprobación de integridad.

    Devuelve el resultado de `integrity_check`. Que sea `ok` es la única prueba
    de que la copia sirve; lo demás son bytes con buena intención.
    """
    with sqlite3.connect(f"file:{origen}?mode=ro", uri=True) as fuente:
        with sqlite3.connect(destino) as copia:
            fuente.backup(copia)
    with sqlite3.connect(destino) as verificacion:
        resultado = verificacion.execute("PRAGMA integrity_check").fetchone()
    return (resultado or ["desconocido"])[0]


class BackupManager:
    """Empaqueta memoria, canon y estado en un archivo verificable."""

    def __init__(self, data_dir: Optional[str] = None, output_dir: str = "output",
                 backup_dir: Optional[str] = None, bucket: Optional[str] = None,
                 retention: int = COPIAS_RETENIDAS, uploader: Any = None):
        db_path = os.getenv("DATABASE_PATH", "data/yuki_memory.db")
        self.data_dir = Path(data_dir) if data_dir else Path(db_path).parent
        self.db_path = Path(db_path) if not data_dir else self.data_dir / Path(db_path).name
        self.output_dir = Path(output_dir)
        self.backup_dir = Path(backup_dir) if backup_dir else self.data_dir / "backups"
        self.bucket = bucket if bucket is not None else os.getenv("BACKUP_GCS_BUCKET", "").strip()
        self.retention = retention
        # Inyectable en pruebas: la suite no sube nada a ninguna parte.
        self._uploader = uploader

    @classmethod
    def from_config(cls, config: Optional[Dict[str, Any]] = None, **overrides: Any) -> "BackupManager":
        respaldo = (config or {}).get("backup", {}) or {}
        memoria = (config or {}).get("memory", {}) or {}
        parametros: Dict[str, Any] = {
            "retention": respaldo.get("retention", COPIAS_RETENIDAS),
            "bucket": respaldo.get("bucket") or os.getenv("BACKUP_GCS_BUCKET", "").strip(),
        }
        if memoria.get("database_path") and not os.getenv("DATABASE_PATH"):
            parametros["data_dir"] = str(Path(memoria["database_path"]).parent)
        parametros.update(overrides)
        return cls(**parametros)

    # -- Contenido -------------------------------------------------------

    def _piezas(self) -> List[Path]:
        """Lo irremplazable, en orden de importancia. Los medios no entran aquí."""
        return [
            self.output_dir / "Biblioteca",
            self.data_dir / "honcho_profile.json",
            self.data_dir / "vital_state.json",
            self.data_dir / "runtime_overrides.json",
            self.data_dir / "discord_pairing.json",
            self.data_dir / "spend_ledger.json",
            self.data_dir / "media_jobs",
            self.data_dir / "bitacora.jsonl",
        ]

    # -- Copia -----------------------------------------------------------

    def create(self) -> BackupResult:
        """Crea el archivo, lo verifica, poda los antiguos y lo sube si procede."""
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        marca = time.strftime("%Y%m%dT%H%M%S")
        destino = self.backup_dir / f"yuki_backup_{marca}.tar.gz"

        incluidos: List[str] = []
        omitidos: List[str] = []
        integridad = "sin base de datos"

        with tempfile.TemporaryDirectory() as temporal:
            escenario = Path(temporal)

            if self.db_path.is_file():
                copia_db = escenario / self.db_path.name
                try:
                    integridad = _copia_coherente_de_sqlite(self.db_path, copia_db)
                except sqlite3.Error as exc:
                    return BackupResult(status="error", error=f"no se pudo copiar la base: {exc}")
                if integridad != "ok":
                    return BackupResult(
                        status="error",
                        error=f"la copia de la base no pasa integrity_check: {integridad}",
                        integrity=integridad,
                    )
                incluidos.append(self.db_path.name)
            else:
                omitidos.append(str(self.db_path))

            for pieza in self._piezas():
                if pieza.is_dir():
                    shutil.copytree(pieza, escenario / pieza.name, dirs_exist_ok=True)
                    incluidos.append(pieza.name)
                elif pieza.is_file():
                    shutil.copy2(pieza, escenario / pieza.name)
                    incluidos.append(pieza.name)
                else:
                    omitidos.append(str(pieza))

            # El precinto de la bitácora sale con la copia: es lo único que
            # detecta un corte por detrás, porque una cadena truncada sigue
            # siendo internamente coherente. Dentro de la instancia no sirve de
            # nada; fuera, es la prueba.
            try:
                from ..core.blackbox import BlackBox

                precinto = BlackBox().seal()
            except Exception:
                precinto = {"error": "no se pudo sellar la bitácora"}

            (escenario / "MANIFIESTO.json").write_text(
                json.dumps({"creado": marca, "incluidos": incluidos, "omitidos": omitidos,
                            "integridad_db": integridad, "precinto_bitacora": precinto},
                           ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            with tarfile.open(destino, "w:gz") as archivo:
                for elemento in sorted(escenario.iterdir()):
                    archivo.add(elemento, arcname=elemento.name)

        resultado = BackupResult(
            status="success", path=str(destino), bytes=destino.stat().st_size,
            included=incluidos, skipped=omitidos, integrity=integridad,
        )
        self.prune()
        self._subir(destino, resultado)
        logger.info("Copia creada: %s (%d bytes, integridad=%s, remoto=%s)",
                    destino, resultado.bytes, integridad, resultado.remote_uri or "no")
        return resultado

    def prune(self) -> int:
        """Conserva las `retention` copias más recientes."""
        copias = sorted(self.backup_dir.glob("yuki_backup_*.tar.gz"))
        sobrantes = copias[:-self.retention] if self.retention > 0 else []
        for copia in sobrantes:
            copia.unlink(missing_ok=True)
        return len(sobrantes)

    def list_backups(self) -> List[Dict[str, Any]]:
        return [{"path": str(c), "bytes": c.stat().st_size, "mtime": int(c.stat().st_mtime)}
                for c in sorted(self.backup_dir.glob("yuki_backup_*.tar.gz"))]

    # -- Salida de la instancia ------------------------------------------

    def _token(self) -> Optional[str]:
        """Credenciales del proyecto (ADC). En la VM salen del metadato."""
        try:
            import google.auth
            from google.auth.transport.requests import Request

            credenciales, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/devstorage.read_write"])
            credenciales.refresh(Request())
            return credenciales.token
        except Exception as exc:
            logger.warning("Sin credenciales para Cloud Storage: %s", type(exc).__name__)
            return None

    def _subir(self, archivo: Path, resultado: BackupResult) -> None:
        """
        Sube la copia si hay bucket declarado.

        Sin bucket no se intenta y **se dice** en el resultado: una copia que
        sigue en el mismo disco que el original no protege de perder el disco.
        """
        if not self.bucket:
            resultado.remote_error = ("sin BACKUP_GCS_BUCKET: la copia queda en el mismo disco "
                                      "que el original y no protege de perderlo")
            return

        if self._uploader is not None:
            try:
                resultado.remote_uri = self._uploader(self.bucket, archivo)
            except Exception as exc:
                resultado.remote_error = f"{type(exc).__name__}: {exc}"
            return

        token = self._token()
        if not token:
            resultado.remote_error = "sin credenciales del proyecto para subir a Cloud Storage"
            return

        url = (GCS_UPLOAD_URL.format(bucket=urllib.parse.quote(self.bucket, safe=""))
               + "?uploadType=media&name=" + urllib.parse.quote(archivo.name, safe=""))
        try:
            with open(archivo, "rb") as datos:
                peticion = urllib.request.Request(
                    url, data=datos.read(), method="POST",
                    headers={"Authorization": f"Bearer {token}",
                             "Content-Type": "application/gzip"},
                )
                with urllib.request.urlopen(peticion, timeout=GCS_TIMEOUT) as respuesta:
                    cuerpo = json.loads(respuesta.read().decode("utf-8"))
            resultado.remote_uri = f"gs://{self.bucket}/{cuerpo.get('name', archivo.name)}"
        except (urllib.error.URLError, urllib.error.HTTPError, OSError,
                json.JSONDecodeError, ValueError) as exc:
            resultado.remote_error = f"la subida falló: {type(exc).__name__}"
            logger.warning("No se pudo subir la copia a gs://%s: %s", self.bucket, type(exc).__name__)
