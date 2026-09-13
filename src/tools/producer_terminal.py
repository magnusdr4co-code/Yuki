"""
Terminal de diagnóstico para el Productor: argv, allowlist, sin shell ni secretos.

Dos cosas de aquí salieron de un turno real en el que Yuki lanzó `pytest` para
comprobarse y resumió el resultado como «✓ terminal_run: exit=5»:

**Un fallo no puede parecer un éxito.** El retorno traía `exit_code` y nada más,
así que distinguir bien de mal quedaba en manos de quien leyera el número. Ahora
hay un veredicto explícito —`ok`— y, cuando falla, un `fallo` que dice en
castellano qué pasó. La política ya decía «una herramienta fallida no es un
éxito»; faltaba que el dato lo dijera igual de claro.

**Y pytest no puede funcionar aquí, así que se dice antes de intentarlo.**
`tests/` está en `.dockerignore`: la imagen de la instancia no lleva la suite, de
modo que recolectar da cero y `pytest` sale con 5 para siempre. Ofrecer un
comando estructuralmente imposible es un dial que no gira, y encima devolvía un
código que parecía un problema del código y no de la imagen. El caché tampoco
cabía: la raíz del contenedor está en sólo lectura, así que se desactiva —no hay
nada que cachear en un diagnóstico de un turno— y el temporal va a `/tmp`.
"""
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

    def _es_pytest(self, argv):
        return argv[0] == "pytest" or argv[1:3] == ["-m", "pytest"]

    def suite_disponible(self):
        """
        Si la suite está en esta imagen. En la instancia **no**: `tests/` está en
        `.dockerignore`, y sin esto el diagnóstico sale con 5 —«no recolectó
        nada»— que se lee como un problema del código y no de la imagen.
        """
        return (self.root / "tests").is_dir()

    def run(self, argv):
        argv = self._validate(argv)
        if self._es_pytest(argv) and not self.suite_disponible():
            # Se dice qué falta y por qué, en vez de dejar que pytest devuelva un
            # 5 que no significa lo que parece.
            return {"argv": argv, "exit_code": None, "ok": False,
                    "fallo": "la suite no está en esta imagen: `tests/` está en "
                             "`.dockerignore`, así que pytest no puede recolectar nada aquí. "
                             "No es un fallo del código; se ejecuta en CI y en desarrollo.",
                    "output": "", "truncated": False, "timed_out": False}

        env = {"PATH": os.environ.get("PATH", ""), "LANG": "C.UTF-8", "PYTHONUNBUFFERED": "1"}
        if self._es_pytest(argv):
            # La raíz del contenedor es de sólo lectura. Sin esto, pytest muere
            # con `Permission denied: '.pytest_cache'` antes de ejecutar nada, y
            # el error parece del proyecto en vez de del montaje.
            argv = [*argv, "-p", "no:cacheprovider", "--basetemp=/tmp/yuki-pytest"]
            env["PYTHONDONTWRITEBYTECODE"] = "1"
        try:
            result = subprocess.run(argv, cwd=self.root, env=env, text=True, capture_output=True,
                                    timeout=30, check=False)
        except subprocess.TimeoutExpired as exc:
            output = ((exc.stdout or "") + (exc.stderr or ""))[:12000]
            return {"argv": argv, "exit_code": 124, "ok": False,
                    "fallo": "se agotaron los 30 segundos y se mató el proceso",
                    "output": SECRET_PATTERN.sub("[REDACTED]", output),
                    "truncated": True, "timed_out": True}
        crudo = result.stdout + result.stderr
        output = SECRET_PATTERN.sub("[REDACTED]", crudo[:12000])
        salida = {"argv": argv, "exit_code": result.returncode, "ok": result.returncode == 0,
                  "output": output, "truncated": len(crudo) > 12000, "timed_out": False}
        if result.returncode != 0:
            salida["fallo"] = f"el comando terminó con código {result.returncode}"
        return salida
