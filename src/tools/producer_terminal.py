"""Terminal de diagnóstico para el Productor: argv, allowlist, sin shell ni secretos."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

SAFE_ROOTS = {".", "src", "tests", "docs", "skills", "scripts", "config.yaml", "AGENTS.md", "SOUL.md", "MEMORY.md", "output/Biblioteca"}
FORBIDDEN = {"data", ".git", ".env", "deploy", "__pycache__"}
SECRET_PATTERN = re.compile(r"(?i)(?:api[_-]?key|token|password|secret)\s*[=:]\s*[^\s]+")


class ProducerTerminal:
    def __init__(self, root="."):
        self.root = Path(root).resolve()

    def _safe_path(self, value):
        path = (self.root / value).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Ruta fuera del repositorio")
        relative = str(path.relative_to(self.root)) or "."
        if any(part in FORBIDDEN for part in Path(relative).parts):
            raise ValueError("Ruta sensible no disponible en la terminal")
        if not any(relative == root or relative.startswith(root + "/") for root in SAFE_ROOTS):
            raise ValueError("Ruta no disponible en la terminal")
        return relative

    def _validate(self, argv):
        if not isinstance(argv, list) or not 1 <= len(argv) <= 16 or not all(isinstance(x, str) and len(x) <= 300 for x in argv):
            raise ValueError("argv debe ser una lista corta de cadenas")
        command, args = argv[0], argv[1:]
        if command in {"pwd"}:
            if args:
                raise ValueError("pwd no acepta argumentos")
        elif command == "git":
            if not args or args[0] not in {"status", "diff", "log"}:
                raise ValueError("Sólo git status/diff/log")
        elif command in {"pytest", "python", "python3"}:
            if command != "pytest" and args[:2] != ["-m", "pytest"]:
                raise ValueError("Python sólo puede ejecutar pytest")
            targets = args if command == "pytest" else args[2:]
            for item in targets:
                if item.startswith("-"):
                    continue
                self._safe_path(item)
        elif command in {"ls", "find", "rg", "sed"}:
            for item in args:
                if item.startswith("-") or item.isdigit() or item in {"p", ""}:
                    continue
                if "/" in item or item == "." or item in SAFE_ROOTS or item in FORBIDDEN:
                    self._safe_path(item)
        else:
            raise ValueError("Comando no permitido")
        if any(any(mark in item for mark in (";", "&&", "|", "`", "$", "\n")) for item in argv):
            raise ValueError("La terminal no acepta sintaxis de shell")
        return argv

    def run(self, argv):
        argv = self._validate(argv)
        env = {"PATH": os.environ.get("PATH", ""), "LANG": "C.UTF-8", "PYTHONUNBUFFERED": "1"}
        try:
            result = subprocess.run(argv, cwd=self.root, env=env, text=True, capture_output=True,
                                    timeout=30, check=False)
        except subprocess.TimeoutExpired as exc:
            output = ((exc.stdout or "") + (exc.stderr or ""))[:12000]
            return {"argv": argv, "exit_code": 124,
                    "output": SECRET_PATTERN.sub("[REDACTED]", output),
                    "truncated": True, "timed_out": True}
        output = (result.stdout + result.stderr)[:12000]
        output = SECRET_PATTERN.sub("[REDACTED]", output)
        return {"argv": argv, "exit_code": result.returncode, "output": output,
                "truncated": len(result.stdout + result.stderr) > len(output), "timed_out": False}
