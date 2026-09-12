"""
El cuaderno de taller: qué se intentó en un compás, y por qué no cuajó.

La Biblioteca guarda **obras**: ficheros con su hash, su tipo y su estado. La
receta guarda **cómo se hizo** una pista que sí llegó a generarse. La memoria
guarda **lo vivido**. Ninguna de las tres guarda lo que más se pierde entre una
sesión y la siguiente: un motivo a medio pulir, una tensión métrica que no se
resolvió, una afinación que se probó y sonaba mal, un esquema rítmico que
merece una segunda lectura dentro de tres semanas.

Eso no cabía en ningún sitio, y no por falta de hueco:

  · **En la Biblioteca, no**, porque un apunte no es una obra. Ni siquiera
    `semilla`, que es una idea *que ya existe como fichero*. Una tensión métrica
    sin resolver no tiene fichero, y fabricarle uno para archivarla sería
    presentar como obra lo que es una nota al margen. Por eso este cuaderno no
    guarda rutas, ni contenido de obras, ni ficheros: sólo el apunte. Un texto
    que merezca conservarse va a `library_save_text`, y `anotar` lo dice con un
    error cuando alguien intenta pegar aquí una letra entera.

  · **En la memoria, tampoco**, y ésta es la razón que importa: **el olvido**.
    El ciclo de sueño suelta lo viejo, leve y nunca recuperado, y un apunte de
    taller es exactamente eso durante meses —no se recuerda una tensión del
    compás siete hasta que se vuelve a tocar esa pieza—. La quinta invariante
    protege canon, síntesis, crecimiento y lo fijado; no protege apuntes. Un
    cuaderno construido sobre la memoria se iría borrando justo por donde más
    falta hace. Aquí no puede pasar: vive en su propio fichero, y el ciclo de
    sueño no lo alcanza porque no está en la base que recorre.

  · **En la receta, sólo a medias.** La receta sabe con qué parámetros salió una
    pista, pero no si valió la pena. No tiene juicio, y sólo existe para lo que
    llegó a generarse — y lo que no cuajó, muchas veces, no llegó a generarse.

**Lo que este cuaderno no es.** No alimenta un generador de coincidencias. Lo
que sabe llega a los criterios de las artes por `observaciones` —el canal de
`criterio_base` para lo que se dice en voz alta antes de gastar— y nunca por un
parámetro. Un apunte no baja un BPM ni cambia una tonalidad a espaldas de nadie:
aparece escrito en el resumen, y decide ella. Ésa es la diferencia entre un
cuaderno y un piloto automático, y `avisos_para` está escrito para no poder
hacer lo segundo: devuelve texto.

Un apunte acumula intentos en vez de sustituirlos. «Qué se intentó» es plural a
lo largo del tiempo, y quedarse sólo con el último borra precisamente la serie
que enseña algo.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core import estado_json
from ..core.rutas import datos as _datos

logger = logging.getLogger("Yuki.Cuaderno")

ABIERTO = "abierto"
RESUELTO = "resuelto"
ABANDONADO = "abandonado"

# Las artes del canon de la Biblioteca, más la voz, que allí vive bajo `sonora`
# pero en el taller se trabaja aparte: una tensión de fraseo vocal no se parece
# en nada a una de arreglo.
ARTES = ("sonora", "visual", "palabra", "audiovisual", "voz")

# Un apunte es una nota al margen, no una obra. El tope no es decorativo: es lo
# que impide que el cuaderno se convierta en una segunda Biblioteca peor hecha,
# sin hash ni estado ni marca de origen.
MAXIMO_APUNTE = 400
MAXIMO_PARAMETROS = 12


class CuadernoError(ValueError):
    """Apunte que no puede existir. Se explica siempre, y se dice dónde va."""


@dataclass
class Intento:
    """Algo que se probó, y por qué no cuajó. Lo segundo es lo que vale."""

    que: str
    por_que_no: str
    at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Intento":
        return cls(que=d.get("que", ""), por_que_no=d.get("por_que_no", ""),
                   at=float(d.get("at", 0.0)))


@dataclass
class Apunte:
    """Una cuestión abierta del taller, con su serie de intentos."""

    id: str
    obra: str
    cuestion: str
    arte: str = "sonora"
    pasaje: str = ""
    parametros: Dict[str, Any] = field(default_factory=dict)
    intentos: List[Intento] = field(default_factory=list)
    estado: str = ABIERTO
    resolucion: str = ""
    relecturas: int = 0
    ultima_relectura: Optional[float] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    cerrado_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["intentos"] = [i.to_dict() for i in self.intentos]
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Apunte":
        datos = dict(d)
        datos["intentos"] = [Intento.from_dict(i) for i in d.get("intentos", [])]
        campos = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in datos.items() if k in campos})

    @property
    def dias(self) -> float:
        """Cuánto lleva abierto. «Hace semanas» es el dato que pedía la idea."""
        return (time.time() - self.created_at) / 86400

    def describe(self) -> str:
        marca = {ABIERTO: "○", RESUELTO: "●", ABANDONADO: "·"}.get(self.estado, "·")
        donde = f" · {self.pasaje}" if self.pasaje else ""
        return (f"{marca} `{self.id}` {self.obra}{donde} — {self.cuestion} "
                f"({len(self.intentos)} intento(s), {self.dias:.0f}d)")

    def como_aviso(self) -> str:
        """
        Cómo se le cuenta a un criterio. Siempre en pasado y siempre con el
        último «por qué no»: un aviso que sólo dijera «hay algo sin resolver»
        obligaría a abrir el cuaderno para saber qué, y nadie lo abriría.
        """
        donde = f" ({self.pasaje})" if self.pasaje else ""
        if self.intentos:
            ultimo = self.intentos[-1]
            return (f"Del cuaderno, hace {self.dias:.0f} día(s){donde}: {self.cuestion}. "
                    f"Se probó «{ultimo.que}» y no cuajó: {ultimo.por_que_no}.")
        return f"Del cuaderno, hace {self.dias:.0f} día(s){donde}: {self.cuestion}. Sin intentos aún."


def _slug(texto: str) -> str:
    limpio = "".join(c if c.isalnum() else "_" for c in (texto or "").strip().lower())
    return "_".join(p for p in limpio.split("_") if p)[:60]


def _acotar(valor: str, campo: str) -> str:
    """
    Un apunte largo no es un apunte: es una obra buscando archivo equivocado.

    El error nombra la Biblioteca porque, si no, quien se lo encuentre recortará
    el texto para que quepa —y entonces el cuaderno sí habrá empezado a guardar
    obra, sólo que mutilada—.
    """
    texto = (valor or "").strip()
    if len(texto) > MAXIMO_APUNTE:
        raise CuadernoError(
            f"El campo '{campo}' tiene {len(texto)} caracteres y el tope del cuaderno es "
            f"{MAXIMO_APUNTE}: esto ya no es un apunte de taller, es una obra. "
            "Guárdala en la Biblioteca (`library_save_text`) y anota aquí la cuestión."
        )
    return texto


class Cuaderno:
    """
    Los apuntes de taller, en su propio fichero y fuera del alcance del olvido.

    No vive en la memoria a propósito (ver el docstring del módulo) y no guarda
    obra: si un día empieza a guardar rutas de fichero, es que se ha convertido
    en una Biblioteca paralela y hay que quitárselo.
    """

    def __init__(self, path: Optional[str] = None):
        if path:
            destino = Path(path)
        elif os.getenv("YUKI_CUADERNO_PATH", "").strip():
            destino = Path(os.getenv("YUKI_CUADERNO_PATH", "").strip())
        else:
            destino = _datos("cuaderno_taller.json")
        self.path = destino

    # -- Persistencia ----------------------------------------------------

    def _leer(self) -> Dict[str, Any]:
        return estado_json.leer(self.path, lambda: {"apuntes": []})

    def _todos(self) -> List[Apunte]:
        return [Apunte.from_dict(d) for d in self._leer().get("apuntes", [])]

    def _guardar(self, apuntes: List[Apunte]) -> None:
        estado_json.escribir(self.path, {"apuntes": [a.to_dict() for a in apuntes]})

    # -- Escribir --------------------------------------------------------

    def anotar(self, obra: str, cuestion: str, arte: str = "sonora",
               pasaje: str = "", parametros: Optional[Dict[str, Any]] = None) -> Apunte:
        """Abre una cuestión. Sin obra y sin cuestión no hay apunte que valga."""
        pieza = _slug(obra)
        if not pieza:
            raise CuadernoError("Un apunte sin obra no se puede releer: ¿de qué pieza es?")
        if arte not in ARTES:
            raise CuadernoError(f"Arte '{arte}' desconocida. Disponibles: {', '.join(ARTES)}.")
        texto = _acotar(cuestion, "cuestion")
        if not texto:
            raise CuadernoError("Un apunte sin cuestión no dice qué quedó sin resolver.")

        params = dict(parametros or {})
        if len(params) > MAXIMO_PARAMETROS:
            raise CuadernoError(
                f"{len(params)} parámetros en un apunte; el tope es {MAXIMO_PARAMETROS}. "
                "Los parámetros de una pista generada están en su receta, no aquí."
            )

        apunte = Apunte(id=uuid.uuid4().hex[:8], obra=pieza, cuestion=texto,
                        arte=arte, pasaje=_acotar(pasaje, "pasaje"), parametros=params)
        apuntes = self._todos()
        apuntes.append(apunte)
        self._guardar(apuntes)
        logger.info("Cuaderno: apunte %s abierto sobre %s (%s)", apunte.id, pieza, arte)
        return apunte

    def intentar(self, apunte_id: str, que: str, por_que_no: str) -> Apunte:
        """
        Añade un intento fallido. **Acumula, no sustituye.**

        Guardar sólo el último borraría la serie, que es lo único que enseña algo:
        tres intentos por la misma razón no son tres fracasos, son un diagnóstico.
        """
        apuntes = self._todos()
        apunte = next((a for a in apuntes if a.id == apunte_id), None)
        if apunte is None:
            raise CuadernoError(f"No existe el apunte '{apunte_id}'.")
        if apunte.estado != ABIERTO:
            raise CuadernoError(
                f"El apunte '{apunte_id}' está '{apunte.estado}': reábrelo o abre uno nuevo.")
        intento = Intento(que=_acotar(que, "que"),
                          por_que_no=_acotar(por_que_no, "por_que_no"))
        if not intento.por_que_no:
            raise CuadernoError(
                "Un intento sin «por qué no cuajó» no sirve dentro de tres semanas: "
                "es justo lo que no se recuerda.")
        apunte.intentos.append(intento)
        apunte.updated_at = time.time()
        self._guardar(apuntes)
        logger.info("Cuaderno: intento %d en %s", len(apunte.intentos), apunte_id)
        return apunte

    def _cerrar(self, apunte_id: str, estado: str, nota: str) -> Apunte:
        apuntes = self._todos()
        apunte = next((a for a in apuntes if a.id == apunte_id), None)
        if apunte is None:
            raise CuadernoError(f"No existe el apunte '{apunte_id}'.")
        apunte.estado = estado
        apunte.resolucion = _acotar(nota, "resolucion")
        apunte.cerrado_at = time.time()
        apunte.updated_at = apunte.cerrado_at
        self._guardar(apuntes)
        logger.info("Cuaderno: apunte %s → %s", apunte_id, estado)
        return apunte

    def resolver(self, apunte_id: str, resolucion: str) -> Apunte:
        """Cierra una cuestión diciendo qué la resolvió. No se borra: se cierra."""
        if not (resolucion or "").strip():
            raise CuadernoError("Resolver sin decir qué funcionó pierde justo lo que valía.")
        return self._cerrar(apunte_id, RESUELTO, resolucion)

    def abandonar(self, apunte_id: str, motivo: str = "") -> Apunte:
        """Deja de estar abierta sin haberse resuelto. También es información."""
        return self._cerrar(apunte_id, ABANDONADO, motivo)

    def releer(self, apunte_id: str) -> Apunte:
        """
        Marca que se volvió sobre él. «Merece una segunda lectura» es una promesa
        vacía si nadie sabe cuáles se releyeron nunca: este contador es lo que
        distingue un cuaderno vivo de un cajón.
        """
        apuntes = self._todos()
        apunte = next((a for a in apuntes if a.id == apunte_id), None)
        if apunte is None:
            raise CuadernoError(f"No existe el apunte '{apunte_id}'.")
        apunte.relecturas += 1
        apunte.ultima_relectura = time.time()
        self._guardar(apuntes)
        return apunte

    # -- Consultar -------------------------------------------------------

    def abiertos(self, obra: str = "", arte: str = "") -> List[Apunte]:
        """Lo que sigue sin resolver, lo más viejo primero: es lo que se olvida."""
        pieza = _slug(obra) if obra else ""
        return sorted(
            [a for a in self._todos()
             if a.estado == ABIERTO
             and (not pieza or a.obra == pieza)
             and (not arte or a.arte == arte)],
            key=lambda a: a.created_at)

    def sobre(self, obra: str) -> List[Apunte]:
        """Todo lo de una pieza, abierto y cerrado. Lo cerrado también enseña."""
        pieza = _slug(obra)
        return sorted([a for a in self._todos() if a.obra == pieza],
                      key=lambda a: a.created_at)

    def get(self, apunte_id: str) -> Optional[Apunte]:
        return next((a for a in self._todos() if a.id == apunte_id), None)

    def buscar(self, texto: str) -> List[Apunte]:
        """Búsqueda llana sobre lo escrito. Sin FTS5: son decenas, no miles."""
        aguja = (texto or "").strip().lower()
        if not aguja:
            return []
        def coincide(a: Apunte) -> bool:
            campos = [a.obra, a.cuestion, a.pasaje, a.resolucion]
            campos += [i.que for i in a.intentos] + [i.por_que_no for i in a.intentos]
            return any(aguja in (c or "").lower() for c in campos)
        return sorted([a for a in self._todos() if coincide(a)],
                      key=lambda a: a.created_at)

    def obras(self) -> Dict[str, int]:
        """Piezas con cuestiones abiertas y cuántas. Para saber por dónde volver."""
        cuenta: Dict[str, int] = {}
        for apunte in self.abiertos():
            cuenta[apunte.obra] = cuenta.get(apunte.obra, 0) + 1
        return dict(sorted(cuenta.items(), key=lambda par: -par[1]))


def avisos_para(obra: str, arte: str = "", limite: int = 3,
                cuaderno: Optional[Cuaderno] = None) -> List[str]:
    """
    Lo que el cuaderno tiene que decir antes de rehacer algo. **Texto, nunca un
    parámetro.**

    Devuelve frases para `Criterio.observaciones`, que es el canal de
    `criterio_base` para lo que se declara en voz alta antes de gastar. Que la
    firma no pueda devolver otra cosa es deliberado: si esto devolviera un dict
    de ajustes, el cuaderno habría dejado de ser un cuaderno para convertirse en
    el generador de coincidencias que la idea descartaba expresamente.

    Se acota a `limite` porque un resumen con nueve avisos no se lee, y se
    marcan como releídos: preguntar por ellos *es* volver sobre ellos.
    """
    libreta = cuaderno or Cuaderno()
    abiertos = libreta.abiertos(obra=obra, arte=arte)[:max(0, limite)]
    for apunte in abiertos:
        libreta.releer(apunte.id)
    return [apunte.como_aviso() for apunte in abiertos]


def anotar_en_criterio(criterio: Any, obra: str, arte: str = "", limite: int = 3) -> int:
    """
    Cuelga los avisos del cuaderno de las observaciones de un criterio.

    Es el único puente entre el cuaderno y la producción, y va en un sentido:
    **escribe en `observaciones`, que es texto que se lee en voz alta antes de
    gastar, y no toca ni un parámetro.** Así el aviso llega a la misma línea
    donde se dice el BPM y la tonalidad, y quien lo lee decide; sin esto el
    cuaderno sería otra facultad escrita, correcta y que no actúa, que es el
    patrón que este repositorio lleva contado cuatro veces.

    Nunca levanta: un cuaderno ilegible no puede impedir entregar una obra. Que
    falle en silencio es aceptable aquí y sólo aquí, porque lo que se pierde es
    un recordatorio, no una garantía — y queda en el log.
    """
    try:
        avisos = avisos_para(obra, arte=arte, limite=limite)
    except Exception as exc:  # noqa: BLE001 — ver el docstring
        logger.warning("Cuaderno ilegible, se sigue sin sus avisos: %s", exc)
        return 0
    criterio.observaciones.extend(avisos)
    return len(avisos)
