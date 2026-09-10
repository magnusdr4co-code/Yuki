"""
Cotejar lo que Yuki dice haber hecho con lo que consta que hizo.

El 9 de septiembre cerró un turno afirmando que varias obras quedaban
«indexadas y localizables bajo el canon» y citó identificadores de Biblioteca
—`sonora-…`, `visual-…`, `audiovisual-…`— que no existían: su propio registro
de ejecución de ese turno sólo mostraba una consulta y cuatro lecturas de tipo
palabra. En otro dijo «la obra queda restituida en su totalidad» sin haber
escrito nada; el primer guardado real llegó dieciséis minutos después.

El arnés ya emitía recibos honestos. El problema es que nadie los comparaba con
la prosa, y la prosa es lo que lee el Productor. Aquí se comparan, y la
discrepancia se dice en la propia respuesta: una corrección que llega con el
mensaje vale más que un log que nadie abre.

Esto no juzga intenciones ni reescribe la respuesta. Sólo señala dos cosas
comprobables: un identificador citado que no está en el índice, y una
afirmación de haber archivado en un turno sin ninguna escritura.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Set

# Los identificadores de Biblioteca son `<tipo>-<sha256 recortado>`. Se admite
# una cita recortada —Yuki las abrevia al escribir— y se resuelve por prefijo:
# exigir los veinte caracteres marcaría como inventada una cita correcta.
_CITA = re.compile(r"\b(sonora|visual|palabra|audiovisual)-([0-9a-f]{6,20})\b", re.IGNORECASE)

# Longitud mínima de prefijo que se acepta como designación. Por debajo, la
# colisión es probable y «existe» dejaría de significar nada.
_PREFIJO_MINIMO = 6

# Herramientas que dejan algo escrito en Biblioteca. `library_inventory` cuenta:
# crea el canon e indexa lo que había suelto.
_ESCRITURAS = frozenset({"library_save_text", "library_set_status", "library_inventory"})

# Afirmaciones de que algo *acaba de* quedar guardado. Se buscan en su forma sin
# tildes y en presente: el pasado remoto («lo guardé en agosto») no es lo que
# este cotejo puede ni debe discutir.
_DICE_QUE_GUARDO = (
    "queda guardad", "quedan guardad", "queda archivad", "quedan archivad",
    "queda restituid", "quedan restituid", "queda indexad", "quedan indexad",
    "queda registrad en la biblioteca", "he guardado", "he archivado",
    "lo he indexado", "la he indexado", "ya esta en la biblioteca",
    "quedan localizables", "queda localizable",
)


def _sin_tildes(texto: str) -> str:
    import unicodedata

    descompuesto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in descompuesto if not unicodedata.combining(c)).casefold()


def citas_de_biblioteca(texto: str) -> List[str]:
    """Identificadores de Biblioteca nombrados en la prosa, en minúsculas."""
    vistos: List[str] = []
    for tipo, digest in _CITA.findall(texto or ""):
        cita = f"{tipo.casefold()}-{digest.casefold()}"
        if cita not in vistos:
            vistos.append(cita)
    return vistos


def citas_inventadas(texto: str, ids_archivados: Iterable[str]) -> List[str]:
    """
    Las citadas que ningún identificador archivado empieza por ellas.

    La resolución es por prefijo y no por igualdad porque una cita abreviada
    correcta no puede contar como invención: eso convertiría el cotejo en ruido
    y a los tres avisos nadie lo leería.
    """
    reales: Set[str] = {str(i).casefold() for i in ids_archivados}
    inventadas = []
    for cita in citas_de_biblioteca(texto):
        if len(cita.split("-", 1)[1]) < _PREFIJO_MINIMO:
            continue
        if not any(real.startswith(cita) for real in reales):
            inventadas.append(cita)
    return inventadas


def dice_haber_archivado(texto: str) -> bool:
    plano = _sin_tildes(texto)
    return any(frase in plano for frase in _DICE_QUE_GUARDO)


def hubo_escritura(evidencia: Iterable[Dict[str, Any]]) -> bool:
    return any(paso.get("tool") in _ESCRITURAS and paso.get("ok")
               for paso in evidencia or ())


def cotejar(respuesta: str, evidencia: Iterable[Dict[str, Any]],
            ids_archivados: Iterable[str]) -> List[str]:
    """Discrepancias comprobables entre lo dicho y lo ejecutado. Vacío si cuadra."""
    evidencia = list(evidencia or ())
    avisos: List[str] = []
    inventadas = citas_inventadas(respuesta, ids_archivados)
    if inventadas:
        avisos.append(
            "He citado " + ", ".join(f"`{c}`" for c in inventadas) +
            ": no está en el índice de Biblioteca. No lo des por archivado."
        )
    if dice_haber_archivado(respuesta) and not hubo_escritura(evidencia):
        avisos.append(
            "He dicho que algo queda guardado y en este turno no se ejecutó ninguna "
            "escritura en Biblioteca. Si quedó archivado, fue antes de ahora."
        )
    return avisos


def bloque_de_correccion(avisos: List[str]) -> str:
    """El aviso viaja con el mensaje. Un log que nadie abre no corrige nada."""
    if not avisos:
        return ""
    return ("\n\n**Cotejo automático — lo dicho no cuadra con lo ejecutado:**\n"
            + "\n".join(f"- {aviso}" for aviso in avisos))
