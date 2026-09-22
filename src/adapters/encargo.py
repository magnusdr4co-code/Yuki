"""
Qué pide realmente un encargo multimedia, leído del texto del pedido.

Los pasos del trabajo durable eran una tupla fija —canción, cuatro clips,
montaje, entrega— y el texto del pedido se guardaba en `order` sin gobernar
nada. El incidente del 9 de septiembre (`docs/INCIDENTE_ENCARGO_MULTIMEDIA.md`)
midió las dos consecuencias:

- se pidió **una portada** y no existía paso capaz de producirla, así que no
  salió y nadie dijo que no iba a salir; `create_single_cover` llevaba meses
  implementado, pero fuera del trabajo;
- «vuelve a hacerlo, esta vez con X» devolvía lo mismo **por construcción**,
  porque ni el prompt de la canción ni el de los clips leían el pedido. No era
  terquedad del modelo: era una constante.

Aquí el pedido se traduce a un plan: qué pasos hay, cuántos segmentos y qué
indicaciones literales viajan a cada prompt. El plan es determinista sobre el
mismo texto, y eso es lo que permite que una reanudación tras un reinicio
recomponga exactamente los mismos identificadores de paso: si cambiaran, el
trabajo reanudado consideraría «no hecho» lo ya pagado.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .discord_intents import fold as _fold
from .discord_intents import ordena_producir, solo_pregunta

# Recorte de las indicaciones que se incrustan en un prompt. No es censura: es
# que un pedido largo desplaza al guion y a la letra dentro de la ventana del
# proveedor, y entonces el encargo sale *menos* parecido a lo pedido.
MAX_MATICES = 700

_PIEZAS = {
    "cancion": (
        "cancion", "cancione", "canta", "cantad", "cantar", "musica", "musical",
        "audio", "pista", "maqueta", "banda sonora", "instrumental",
    ),
    "video": (
        "video", "videos", "clip", "clips", "segmento", "audiovisual",
        "montaje", "metraje", "corto", "cortometraje", "secuencia",
    ),
    "portada": (
        "portada", "portadas", "caratula", "cover", "artwork", "ilustracion",
        "imagen", "imagenes", "foto", "fotos", "retrato", "dibujo", "avatar", "estampa",
    ),
}

# Sólo hasta donde llega el guion: pedir seis segmentos de un guion de cuatro
# sería prometer metraje que nadie ha escrito.
_NUMEROS = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4,
            "cinco": 5, "seis": 6, "siete": 7, "ocho": 8}


@dataclass(frozen=True)
class Encargo:
    """Plan de un encargo: qué se produce y con qué indicaciones."""

    cancion: bool
    video: bool
    portada: bool
    segmentos: int
    matices: str

    def steps(self) -> List[Tuple[str, str]]:
        """Pasos facturables en orden de ejecución, como los espera `MediaJobStore`."""
        pasos: List[Tuple[str, str]] = []
        if self.cancion:
            pasos.append(("cancion", "cancion"))
        if self.portada:
            pasos.append(("portada", "portada"))
        if self.video:
            pasos.extend((f"clip_{i}", "clip") for i in range(1, self.segmentos + 1))
            pasos.append(("montaje", "montaje"))
        pasos.append(("entrega", "entrega"))
        return pasos

    def resumen(self) -> str:
        """Lo que se va a producir, dicho antes de gastar. Sin adornos."""
        partes = []
        if self.cancion:
            partes.append("la canción")
        if self.portada:
            partes.append("una portada")
        if self.video:
            partes.append(f"{self.segmentos} segmento(s) de vídeo y su montaje")
        return ", ".join(partes) if partes else "nada"

    def con_matices(self, prompt: str) -> str:
        """
        Añade al prompt las indicaciones literales del pedido.

        Van **al final** y anunciadas: un proveedor que recorte por longitud
        debe perder antes el relleno de estilo que lo que el Productor acaba de
        pedir. El texto es suyo y sólo suyo —el camino entero está reservado al
        Productor emparejado—, así que se manda tal cual en vez de reescribirlo:
        reescribirlo es exactamente cómo se perdía el matiz.
        """
        if not self.matices:
            return prompt
        return f"{prompt}\n\nIndicaciones literales del encargo: {self.matices}"


# «sin vídeo» nombra el vídeo. Sin esto, negar una pieza la encargaba: la regla
# de alcance mira si la palabra aparece, y aparecer es justo lo que hace.
_NEGACION = re.compile(r"\b(?:sin|ni)\b(?:\s+\w{1,4}){0,2}\s*$")


def _menciona(texto: str, palabras: Tuple[str, ...]) -> bool:
    for palabra in palabras:
        for encontrada in re.finditer(rf"\b{re.escape(palabra)}", texto):
            if not _NEGACION.search(texto[:encontrada.start()]):
                return True
    return False


def _segmentos_pedidos(texto: str, tope: int) -> int:
    """Cuántos clips pide el texto. Sin número explícito, el guion entero."""
    match = re.search(r"\b(\d{1,2}|" + "|".join(_NUMEROS) + r")\s+(?:segmentos?|clips?|planos?)\b",
                      texto)
    if not match:
        return tope
    bruto = match.group(1)
    cantidad = int(bruto) if bruto.isdigit() else _NUMEROS[bruto]
    return max(1, min(cantidad, tope))


def leer_encargo(pedido: str, segmentos_disponibles: int) -> Encargo:
    """
    Traduce el texto de un pedido en un plan de producción.

    La regla de alcance: si el pedido **nombra** alguna pieza (canción, vídeo,
    portada), se producen sólo las nombradas; si no nombra ninguna, se hace el
    encargo completo de siempre —canción y vídeo— porque ése era el
    comportamiento anterior y quitarlo en silencio rompería encargos en curso.
    """
    texto = _fold(pedido or "")
    pedidas = {pieza: _menciona(texto, palabras) for pieza, palabras in _PIEZAS.items()}
    if not any(pedidas.values()):
        pedidas = {"cancion": True, "video": True, "portada": False}
    return Encargo(
        cancion=pedidas["cancion"],
        video=pedidas["video"],
        portada=pedidas["portada"],
        segmentos=_segmentos_pedidos(texto, segmentos_disponibles),
        matices=(pedido or "").strip()[:MAX_MATICES],
    )


# --- Imagen suelta: no es un encargo durable --------------------------------
#
# El 22 de septiembre Yuki escribió en el DM tres composiciones en prosa para
# sus avatares y el Productor pidió «genera tres imágenes con esas
# composiciones». El pedido entró por aquí —`imagen` acababa de sumarse al
# vocabulario de portada— y salió **una** portada de sencillo de *Herrumbre y
# Escarcha*: el encargo durable no ve la conversación, así que «esas
# composiciones» no significaba nada, y la única materia que tenía a mano era
# la última letra de la Biblioteca. Dos veces seguidas, con la imagen pagada.
#
# Una imagen suelta cabe entera en un turno del arnés, que sí lee el contexto
# reciente y tiene `avatar_generate` e `image_generate`. Al encargo durable sólo
# va la portada **de una obra sonora o audiovisual**: la que se pinta leyendo su
# letra.

_IMAGEN = (
    "imagen", "imagenes", "foto", "fotos", "retrato", "retratos", "dibujo", "dibujos",
    "avatar", "avatares", "ilustracion", "ilustraciones", "estampa", "estampas",
    "portada", "portadas", "caratula", "lamina", "laminas",
)

# Verbos que ya son el encargo aunque no digan «genera»: «píntame», «dibújala».
_ORDENA_PINTAR = ("pinta", "dibuja", "ilustra", "retrata")

# Lo que ata la imagen a una obra de la Biblioteca: entonces es la portada de
# esa obra y la pinta el encargo durable a partir de su letra.
_OBRA_DE_ORIGEN = (_PIEZAS["cancion"] + _PIEZAS["video"]
                   + ("sencillo", "single", "album", "disco", "letra", "poema"))
_ID_DE_BIBLIOTECA = re.compile(r"\b(?:palabra|sonora|visual|audiovisual)-[0-9a-f]{6,}\b")

_CONTABLES = ("imagenes", "imagen", "fotos", "foto", "retratos", "retrato", "dibujos",
              "dibujo", "avatares", "avatar", "ilustraciones", "ilustracion", "estampas",
              "estampa", "composiciones", "composicion", "versiones", "version",
              "variantes", "variante", "propuestas", "propuesta", "portadas", "portada")


@dataclass(frozen=True)
class PedidoDeImagen:
    """
    Una orden de imagen suelta. `cantidad` es la pedida, o `None` si el pedido
    dice «imágenes» sin número: entonces decide quien pinta, y lo dice.
    """

    cantidad: Optional[int]

    def describir(self) -> str:
        if self.cantidad is None:
            return "varias imágenes, sin número dicho"
        return f"{self.cantidad} " + ("imagen" if self.cantidad == 1 else "imágenes")


def _cantidad_de_imagenes(texto: str) -> Optional[int]:
    numeros = "|".join(sorted(_NUMEROS, key=len, reverse=True))
    match = re.search(rf"\b(\d{{1,2}}|{numeros})\s+(?:\w+\s+)?(?:{'|'.join(_CONTABLES)})\b",
                      texto)
    if match:
        bruto = match.group(1)
        return int(bruto) if bruto.isdigit() else _NUMEROS[bruto]
    plural = ("imagenes", "fotos", "retratos", "dibujos", "avatares", "ilustraciones",
              "estampas", "portadas", "laminas", "composiciones")
    return None if _menciona(texto, plural) else 1


def pedido_de_imagen(pedido: str) -> Optional[PedidoDeImagen]:
    """
    Si el pedido es una imagen suelta —no la portada de una obra—, cuántas.

    Devuelve `None` cuando no manda pintar nada, cuando sólo pregunta si se
    podría, o cuando la imagen es la portada de una canción, un vídeo o una obra
    designada por su identificador: eso sigue siendo del encargo durable.
    """
    texto = _fold(pedido or "")
    if not (ordena_producir(texto) or any(verbo in texto for verbo in _ORDENA_PINTAR)):
        return None
    if solo_pregunta(texto) or not _menciona(texto, _IMAGEN):
        return None
    if _menciona(texto, _OBRA_DE_ORIGEN) or _ID_DE_BIBLIOTECA.search(texto):
        return None
    return PedidoDeImagen(cantidad=_cantidad_de_imagenes(texto))
