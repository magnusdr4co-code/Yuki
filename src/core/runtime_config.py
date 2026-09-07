"""Ajustes persistentes y reversibles del arnés, sin credenciales ni infraestructura."""
from __future__ import annotations

import copy
import json
import os
import time
from pathlib import Path

MODEL_IDS = {
    "google/gemini-3.6-flash", "google/gemini-3.7-flash", "google/gemini-3.8-flash",
}
PRODUCER_FIELDS = {
    "agent.model.temperature", "agent.model.max_tokens",
    "vertex_ai.temperature", "vertex_ai.max_tokens",
    "vertex_ai.primary_model", "vertex_ai.fallback_model",
}
EVOLUTION_FIELDS = {"agent.model.temperature", "vertex_ai.temperature"}


def _merge(target, overlay):
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        else:
            target[key] = copy.deepcopy(value)


class RuntimeConfigStore:
    """Overlay en data/: sobrevive reinicios, pero nunca reescribe config.yaml."""
    def __init__(self, base_config, path="data/runtime_overrides.json"):
        self.base_config = copy.deepcopy(base_config)
        self.path = Path(path)

    def _load(self):
        if not self.path.exists():
            return {"overrides": {}, "history": []}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return {"overrides": data.get("overrides", {}), "history": data.get("history", [])}

    def _write(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

    def effective_config(self):
        result = copy.deepcopy(self.base_config)
        _merge(result, self._load()["overrides"])
        return result

    @staticmethod
    def _validate(path, value, actor):
        allowed = PRODUCER_FIELDS if actor == "producer" else EVOLUTION_FIELDS
        if path not in allowed:
            raise ValueError("Ajuste no autorizado para este origen")
        if path.endswith("temperature"):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= value <= 2.0:
                raise ValueError("temperature debe estar entre 0 y 2")
            return float(value)
        if path.endswith("max_tokens"):
            if isinstance(value, bool) or not isinstance(value, int) or not 256 <= value <= 8192:
                raise ValueError("max_tokens debe ser un entero entre 256 y 8192")
            return value
        if path.endswith("model"):
            if value not in MODEL_IDS:
                raise ValueError("Modelo fuera de la lista permitida de Vertex")
            return value
        raise ValueError("Ajuste no reconocido")

    @staticmethod
    def _assign(data, dotted, value, remove=False):
        cursor = data
        parts = dotted.split(".")
        for part in parts[:-1]:
            if remove and part not in cursor:
                return
            cursor = cursor.setdefault(part, {})
        if remove:
            cursor.pop(parts[-1], None)
        else:
            cursor[parts[-1]] = value

    def set(self, path, value, *, actor, reason=""):
        value = self._validate(path, value, actor)
        data = self._load()
        self._assign(data["overrides"], path, value)
        data["history"].append({"at": int(time.time()), "actor": actor, "path": path,
                                "value": value, "reason": str(reason)[:240]})
        data["history"] = data["history"][-100:]
        self._write(data)
        return {"path": path, "value": value, "actor": actor, "persistence": str(self.path)}

    def rollback(self, path, *, actor, reason=""):
        self._validate(path, self.get_public()["values"].get(path, self._base_value(path)), actor)
        data = self._load()
        self._assign(data["overrides"], path, None, remove=True)
        data["history"].append({"at": int(time.time()), "actor": actor, "path": path,
                                "value": "rollback", "reason": str(reason)[:240]})
        data["history"] = data["history"][-100:]
        self._write(data)
        return {"path": path, "value": self._base_value(path), "actor": actor, "rolled_back": True}

    def _base_value(self, dotted):
        cursor = self.base_config
        for part in dotted.split("."):
            cursor = cursor[part]
        return cursor

    def get_public(self):
        effective = self.effective_config()
        values = {}
        for path in PRODUCER_FIELDS:
            cursor = effective
            for part in path.split("."):
                cursor = cursor[part]
            values[path] = cursor
        return {"values": values, "history": self._load()["history"][-20:]}
