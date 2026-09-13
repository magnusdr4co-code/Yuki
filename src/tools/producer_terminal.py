"""Terminal de diagnóstico para el Productor: argv, allowlist, sin shell ni secretos."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

SAFE_ROOTS = {".", "src", "tests", "docs", "skills", "scripts", "config.yaml", "AGENTS.md", "SOUL.md", "MEMORY.md", "output/Biblioteca"}
FORBIDDEN = {"data", ".git", ".env", "deploy", "__pycache__"}
SECRET_PATTERN = re.compile(r"(?i)(?:api[_-]?key|token|password|secret)\s*[=:]\s*[^\s]+")


def _as_text(value):
    """Normaliza stdout/stderr de excepciones y dobles de subprocess."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


class ProducerTerminal:
    def __init__(self, root="."):
        self.root = Path(root).resolve()

    def _safe_path(self, value):
        candidate = Path(value)
        path = (candidate if candidate.is_absolute() else self.root / candidate).resolve()
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

    @staticmethod
    def _is_pytest(argv):
        """Detecta pytest para aplicar sólo variables de entorno seguras."""
        return bool(argv) and (argv[0] == "pytest" or
                               (argv[0] in {"python", "python3"} and
                                argv[1:3] == ["-m", "pytest"]))

    def run(self, argv):
        argv = self._validate(argv)
        env = {
            "PATH": os.environ.get("PATH", ""),
            "LANG": "C.UTF-8",
            "PYTHONUNBUFFERED": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        if self._is_pytest(argv):
            # El runtime puede montar `/app` como solo lectura. La suite debe
            # seguir siendo diagnóstica sin convertir el repositorio en un
            # destino de escritura ni fallar antes de recolectar tests.
            env["TMPDIR"] = "/tmp"
        try:
            result = subprocess.run(argv, cwd=self.root, env=env, text=True, capture_output=True,
                                    timeout=90, check=False)
        except subprocess.TimeoutExpired as exc:
            output = (_as_text(exc.stdout) + _as_text(exc.stderr))[:12000]
            return {"argv": argv, "exit_code": 124,
                    "output": SECRET_PATTERN.sub("[REDACTED]", output),
                    "truncated": True, "timed_out": True}
        except FileNotFoundError:
            return {"argv": argv, "exit_code": 127,
                    "output": f"Comando no encontrado: {argv[0]}",
                    "truncated": False, "timed_out": False}
        except OSError as exc:
            return {"argv": argv, "exit_code": 126,
                    "output": f"No se pudo ejecutar el comando: {type(exc).__name__}",
                    "truncated": False, "timed_out": False}
        output = (_as_text(result.stdout) + _as_text(result.stderr))[:12000]
        output = SECRET_PATTERN.sub("[REDACTED]", output)
        return {"argv": argv, "exit_code": result.returncode, "output": output,
                "truncated": len(_as_text(result.stdout) + _as_text(result.stderr)) > len(output),
                "timed_out": False}
