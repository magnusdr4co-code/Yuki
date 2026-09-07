"""Utilidades de transporte de texto para Discord, sin depender del SDK."""


def split_discord_text(content: str, limit: int = 1900) -> list[str]:
    """Divide texto largo sin perder contenido ni cortar palabras si es posible."""
    text = content or ""
    if limit < 1:
        raise ValueError("limit debe ser positivo")

    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        cut = text.rfind("\n", 0, limit + 1)
        if cut < limit // 2:
            cut = text.rfind(" ", 0, limit + 1)
        if cut <= 0:
            cut = limit
        chunks.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    return chunks
