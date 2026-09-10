"""
Salida real a Telegram, y lo que no está dicho sin rodeos.

`docs/VIRTUALIZACION_Y_MEJORAS.md` (M6, limitador L6) lo describía así: «Telegram
registra en log, no llega a ningún seguidor». Era peor que eso. `start_polling`
escribía «Bot de Telegram de Yuki iniciado» con un token configurado y no
iniciaba nada; `broadcast_drop` registraba `📢 [TELEGRAM BROADCAST]` con el texto
del lanzamiento y devolvía `None`, así que la tarea de las 07:30 daba el día por
difundido. Nadie recibía nada y nada fallaba.

Cerrar un canal simulado admitía dos salidas honestas —implementarlo o retirarlo
del diagrama—. Aquí está implementada **la salida**, que es lo que el proyecto
usa, contra la API HTTP de Telegram con la biblioteca estándar. Sin dependencia
nueva: la instancia es una `e2-small` con 2 GB para todo, y `multipart` son
veinte líneas que no envejecen.

**La entrada no está implementada y se dice.** Un bucle de `getUpdates` con su
desplazamiento persistido es otro trabajo, y anunciarlo a medias es exactamente
lo que hacía el código anterior.

Tres reglas del proyecto se cumplen aquí y no son adorno:
- el freno para la publicación se consulta **antes** de salir a la red;
- todo material sintético se marca **antes** de entregarlo (Artículo 50), y cada
  mensaje lleva además la declaración visible;
- nada se da por entregado si no consta la respuesta del servidor.
"""

import asyncio
import json
import logging
import mimetypes
import os
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..core.brake import Brake
from ..core.transparency import MediaMarker

logger = logging.getLogger("Yuki.TelegramAdapter")

API = "https://api.telegram.org"

# La misma línea que el adaptador de Discord añade a cada entrega.
DECLARACION = "🤖 Contenido generado por IA"

# Telegram corta los pies de foto y las leyendas antes que los mensajes sueltos.
MAX_LEYENDA = 1024
MAX_MENSAJE = 4096

TOKEN_DE_EJEMPLO = "your_telegram_bot_token_here"


def _multipart(campos: Dict[str, Any],
               fichero: Optional[Tuple[str, Tuple[str, bytes]]]) -> Tuple[bytes, str]:
    """
    Cuerpo `multipart/form-data` con la biblioteca estándar.

    Telegram sólo acepta un fichero local así, y añadir una dependencia HTTP al
    camino de arranque por veinte líneas no sale a cuenta en una `e2-small`.
    """
    frontera = f"----yuki{uuid.uuid4().hex}"
    partes: List[bytes] = []
    for clave, valor in campos.items():
        partes.append(
            f"--{frontera}\r\nContent-Disposition: form-data; name=\"{clave}\"\r\n\r\n"
            f"{valor}\r\n".encode("utf-8"))
    if fichero is not None:
        campo, (nombre, datos) = fichero
        tipo = mimetypes.guess_type(nombre)[0] or "application/octet-stream"
        partes.append(
            f"--{frontera}\r\nContent-Disposition: form-data; name=\"{campo}\"; "
            f"filename=\"{nombre}\"\r\nContent-Type: {tipo}\r\n\r\n".encode("utf-8"))
        partes.append(datos)
        partes.append(b"\r\n")
    partes.append(f"--{frontera}--\r\n".encode("utf-8"))
    return b"".join(partes), f"multipart/form-data; boundary={frontera}"


def _publicar(url: str, datos: Dict[str, Any],
              fichero: Optional[Tuple[str, Tuple[str, bytes]]]) -> Dict[str, Any]:
    """POST bloqueante; se llama desde un hilo para no parar el bucle."""
    cuerpo, tipo = _multipart(datos, fichero)
    peticion = urllib.request.Request(url, data=cuerpo, headers={"Content-Type": tipo})
    try:
        with urllib.request.urlopen(peticion, timeout=30) as respuesta:
            return json.loads(respuesta.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # Telegram explica el motivo en el cuerpo incluso con 4xx, y ese motivo
        # —«chat not found»— vale más que el código.
        try:
            return json.loads(exc.read().decode("utf-8"))
        except Exception:
            return {"ok": False, "description": f"HTTP {exc.code}"}


class TelegramAdapter:
    def __init__(self, agent_instance, token: Optional[str] = None,
                 cliente=None, brake: Optional[Brake] = None):
        self.agent = agent_instance
        self.token = (token or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
        if self.token == TOKEN_DE_EJEMPLO:
            self.token = ""
        self.default_chat_id = (os.getenv("TELEGRAM_DEFAULT_CHAT_ID") or "").strip()
        # El cliente se inyecta en pruebas: nada de red en la suite.
        self._cliente = cliente
        self.brake = brake or Brake()
        self.agent.telegram_adapter = self

    @property
    def enabled(self) -> bool:
        """Con token y destino. Sin las dos cosas no hay a quién escribir."""
        return bool(self.token and self.default_chat_id)

    def por_que_no(self) -> str:
        """El motivo concreto, para poder decirlo en vez de callar."""
        if not self.token:
            return "sin TELEGRAM_BOT_TOKEN declarado"
        if not self.default_chat_id:
            return "sin TELEGRAM_DEFAULT_CHAT_ID declarado"
        return ""

    async def start_polling(self):
        """
        No hay entrada por Telegram, y esto lo dice en vez de fingirlo.

        Antes registraba «Bot de Telegram de Yuki iniciado» y volvía sin abrir
        nada: un mensaje de arranque que afirmaba una capacidad inexistente en el
        único sitio donde alguien iría a comprobarlo.
        """
        logger.warning(
            "Telegram: la entrada (polling) no está implementada; sólo la salida. "
            "Estado de la salida: %s.",
            "lista" if self.enabled else self.por_que_no(),
        )
        return {"polling": False, "motivo": "getUpdates no implementado",
                "salida_disponible": self.enabled}

    async def handle_message(self, user_id: str, user_name: str, text: str) -> str:
        """Responde a un mensaje ya recibido. No lo recoge de Telegram: eso no existe."""
        if hasattr(self.agent, "presence_controller"):
            if not self.agent.presence_controller.should_respond("telegram_dm"):
                return "NADA_QUE_DECIR"
        return await self.agent.generate_response(
            user_id=user_id, user_name=user_name, message=text, channel_type="telegram_dm",
        )

    # -- Salida ----------------------------------------------------------

    def _url(self, metodo: str) -> str:
        return f"{API}/bot{self.token}/{metodo}"

    async def _pedir(self, metodo: str, datos: Dict[str, Any],
                     fichero: Optional[Tuple[str, Tuple[str, bytes]]] = None) -> Dict[str, Any]:
        """Una llamada a la API. Un fallo se devuelve, nunca se disfraza de éxito."""
        if self._cliente is not None:
            respuesta = await self._cliente.post(
                self._url(metodo), data=datos,
                files={fichero[0]: fichero[1]} if fichero else None)
            return self._interpretar(metodo, respuesta.json)
        try:
            cuerpo = await asyncio.to_thread(_publicar, self._url(metodo), datos, fichero)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return {"ok": False, "error": f"{type(exc).__name__} llamando a {metodo}"}
        return self._interpretar(metodo, lambda: cuerpo)

    @staticmethod
    def _interpretar(metodo: str, leer) -> Dict[str, Any]:
        try:
            cuerpo = leer()
        except Exception:
            return {"ok": False, "error": f"{metodo} devolvió una respuesta ilegible"}
        if not cuerpo.get("ok"):
            return {"ok": False, "error": f"{metodo}: {cuerpo.get('description') or 'sin detalle'}"}
        return {"ok": True, "resultado": cuerpo.get("result")}

    def _marcar(self, ruta: Optional[str]) -> None:
        """Segunda puerta del Artículo 50: se marca antes de entregar, no después."""
        if not ruta or not Path(ruta).is_file():
            return
        marcador = getattr(self.agent, "marker", None) or MediaMarker()
        if not marcador.is_marked(ruta):
            marcador.mark(ruta, "", "", "telegram")

    async def broadcast_drop(self, text: str, image_path: Optional[str] = None,
                             audio_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Difunde un lanzamiento. Devuelve **qué se entregó de verdad**.

        Antes registraba una línea con aspecto de difusión y devolvía `None`, así
        que la tarea de las 07:30 daba el día por difundido sin que llegara nada.
        Ahora el resultado dice `entregado` y, si no, por qué; quien lo reciba
        puede distinguirlo sin leer el código.
        """
        if hasattr(self.agent, "presence_controller"):
            if not self.agent.presence_controller.should_broadcast("telegram_channel"):
                return {"entregado": False, "motivo": "sin disposición para publicar ahora",
                        "mensajes": []}
        frenada = self.brake.blocked_reason("publicar")
        if frenada:
            return {"entregado": False, "motivo": f"frenado: {frenada}", "mensajes": []}
        if not self.enabled:
            motivo = self.por_que_no()
            logger.warning("Telegram no difunde: %s. Nada ha salido.", motivo)
            return {"entregado": False, "motivo": motivo, "mensajes": []}

        cuerpo = f"{text}\n\n{DECLARACION}"
        enviados: List[str] = []
        fallos: List[str] = []

        for ruta, metodo, campo, limite in (
            (image_path, "sendPhoto", "photo", MAX_LEYENDA),
            (audio_path, "sendVoice", "voice", MAX_LEYENDA),
        ):
            if not ruta or not Path(ruta).is_file():
                continue
            self._marcar(ruta)
            with open(ruta, "rb") as binario:
                resultado = await self._pedir(
                    metodo,
                    {"chat_id": self.default_chat_id, "caption": cuerpo[:limite]},
                    fichero=(campo, (Path(ruta).name, binario.read())),
                )
            (enviados if resultado["ok"] else fallos).append(
                campo if resultado["ok"] else f"{campo}: {resultado['error']}")

        # El texto va suelto sólo si no viajó ya como pie de un adjunto: repetirlo
        # sería mandar el mismo lanzamiento dos veces al mismo canal.
        if not enviados:
            resultado = await self._pedir(
                "sendMessage", {"chat_id": self.default_chat_id, "text": cuerpo[:MAX_MENSAJE]})
            (enviados if resultado["ok"] else fallos).append(
                "texto" if resultado["ok"] else f"texto: {resultado['error']}")

        entregado = bool(enviados)
        if entregado:
            logger.info("Telegram: entregado %s%s", ", ".join(enviados),
                        f" (fallos: {'; '.join(fallos)})" if fallos else "")
        else:
            logger.warning("Telegram: nada entregado (%s)", "; ".join(fallos) or "sin detalle")
        return {"entregado": entregado, "mensajes": enviados, "fallos": fallos,
                "motivo": "" if entregado else ("; ".join(fallos) or "sin detalle")}
