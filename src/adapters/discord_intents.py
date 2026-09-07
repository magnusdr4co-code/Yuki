"""Utilidades puras para detectar encargos de producción desde Discord."""

import re
import unicodedata
from typing import Tuple


def fold(value: str) -> str:
    """Normaliza texto para detectar intenciones y nombres sin depender de tildes."""
    decomposed = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()


def channel_slug(value: str) -> str:
    """Convierte un nombre humano en un nombre de canal seguro para Discord."""
    ascii_name = "".join(
        ch for ch in unicodedata.normalize("NFKD", value or "")
        if not unicodedata.combining(ch)
    ).casefold()
    slug = re.sub(r"[^a-z0-9_-]+", "-", ascii_name).strip("-_")
    return slug[:90] or "salon"


def looks_like_discord_production_request(content: str) -> bool:
    """Reconoce sólo la petición explícita de abrir un espacio de producción."""
    text = fold(content)
    return (
        "canal" in text
        and any(token in text for token in ("crea", "crear", "abre", "dispon"))
        and "salon" in text
        and ("discord" in text or "servidor" in text)
    )


def looks_like_media_delivery_request(content: str) -> bool:
    """Encargo explícito de generar y adjuntar medios en el DM del Productor."""
    text = fold(content)
    asks_to_make = any(token in text for token in (
        "crea", "crear", "genera", "generar", "haz", "realiza", "procede", "continua",
    ))
    media_terms = ("cancion", "musica", "audio", "video", "mp3", "mp4")
    asks_for_media = any(token in text for token in media_terms)
    asks_for_delivery = any(token in text for token in ("aqui", "pasame", "adjunta", "envia"))
    asks_for_both_media = sum(token in text for token in ("cancion", "video")) == 2
    # El Productor puede decir "procede" tras haber descrito los adjuntos;
    # exigir literalmente "pásamelo" convertía una orden inequívoca en prosa.
    return asks_to_make and asks_for_media and (asks_for_delivery or asks_for_both_media)


def extract_production_target(content: str) -> Tuple[str, str]:
    """Extrae servidor y canal de la petición; mantiene defaults conservadores."""
    quoted = re.findall(r'["“”\']([^"“”\']+)["”\']', content or "")
    guild_name = quoted[0].strip() if quoted else "Dev Server"
    channel_name = quoted[1].strip() if len(quoted) > 1 else "Salón"
    return guild_name, channel_name
