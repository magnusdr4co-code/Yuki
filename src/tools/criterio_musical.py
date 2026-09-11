"""
Lo que decide Yuki antes de encargar una canción.

El prompt musical era una constante escrita a mano en el adaptador de Discord:
90 segundos, 72 BPM, escala Insen, voz femenina serena. Daba igual la letra que
se pusiera delante. Dos consecuencias medidas el 11 de septiembre:

- el Productor señaló que «se apresuraba el poema» —versos de nueve y de
  diecisiete sílabas metidos en el mismo número de compases—, y nada en el
  código miraba eso;
- Yuki reescribió la letra fijando **68 BPM** y su propia estructura, y el
  encargo siguiente habría vuelto a mandar 72, contradiciéndola en silencio.

Aquí está el criterio. No es un adorno de prosa: produce el prompt que se manda
al motor y el resumen que se dice en el DM **antes** de gastar.

Dos reglas gobiernan todo lo demás:

**Manda la letra.** Si la letra trae sus propias marcas —tempo, compás,
tonalidad, secciones—, se respetan. Son decisiones de quien la escribió, y
pisarlas con un valor por defecto es lo que hacía la constante.

**Lo que se deduce, se dice de dónde salió.** Cada decisión lleva su origen:
`letra` si estaba escrita, `criterio` si la puso este módulo al medirla. Quien
lea el resumen tiene que poder distinguir lo que eligió Yuki de lo que se
dedujo, sin abrir el código.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# Rangos de tempo. No son gusto: son la relación entre sílabas por verso y
# compases disponibles. Una letra densa a 80 BPM obliga a la voz a trotar, que
# es exactamente lo que el Productor oyó.
BPM_MINIMO, BPM_MAXIMO = 58, 96
BPM_POR_DEFECTO = 72

# Umbral de desigualdad métrica. Por encima, los versos no caben iguales en el
# compás y el motor acelera unos para alcanzar el siguiente acorde.
DISPERSION_QUE_ATROPELLA = 3.5

# Escalas del canon japonés que el generador MIDI entiende.
ESCALAS = ("insen", "hirajoshi", "kumoi", "iwato", "yo")

# Marcas de sección reconocidas, en los dos idiomas en que Yuki las escribe.
_SECCION = re.compile(
    r"^\s*#*\s*\[\s*(intro|verse|verso|estrofa|chorus|estribillo|bridge|puente|"
    r"outro|clímax|climax|coda|pre-?chorus)\b[^\]]*\]", re.IGNORECASE | re.MULTILINE)

_VOCALES = "aeiouáéíóúü"
_VOCALES_FUERTES = "aeoáéó"


def _sin_tildes(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in descompuesto if not unicodedata.combining(c)).casefold()


def silabas(verso: str) -> int:
    """
    Sílabas de un verso castellano, **aproximadas y declaradas como tales**.

    Cuenta grupos vocálicos y une los diptongos; no resuelve sinalefa entre
    palabras ni hiatos acentuados, que exigirían un diccionario. Sirve para lo
    que se usa aquí —comparar unos versos con otros— y no para escandir poesía.
    Decir que es exacta sería inventarse una precisión.
    """
    limpio = re.sub(r"[^\w\s]", " ", verso or "", flags=re.UNICODE).strip()
    if not limpio:
        return 0
    total = 0
    for palabra in limpio.split():
        letras = palabra.casefold()
        grupos = 0
        anterior_vocal = False
        for indice, letra in enumerate(letras):
            es_vocal = letra in _VOCALES
            if es_vocal and not anterior_vocal:
                grupos += 1
            elif es_vocal and anterior_vocal:
                # Dos fuertes seguidas son dos sílabas; con una débil, diptongo.
                previa = letras[indice - 1]
                if previa in _VOCALES_FUERTES and letra in _VOCALES_FUERTES:
                    grupos += 1
            anterior_vocal = es_vocal
        total += max(1, grupos)
    return total


def _versos(letra: str) -> List[str]:
    """Líneas que son verso: ni marcas de sección, ni acotaciones, ni vacíos."""
    salida = []
    for linea in (letra or "").splitlines():
        limpia = linea.strip()
        if not limpia or limpia.startswith(("#", "---", "***", ">", "|", "`")):
            continue
        if limpia.startswith("[") or limpia.startswith("("):
            continue
        if _SECCION.match(limpia):
            continue
        salida.append(limpia)
    return salida


def _rima(verso: str) -> str:
    """Terminación asonante: las dos últimas vocales del verso, sin tildes."""
    plano = _sin_tildes(re.sub(r"[^\w\s]", "", verso or ""))
    vocales = [c for c in plano if c in "aeiou"]
    return "".join(vocales[-2:]) if len(vocales) >= 2 else "".join(vocales)


@dataclass
class PlanMusical:
    """La decisión tomada, con el origen de cada pieza."""

    titulo: str
    bpm: int
    compas: str
    tonalidad: str
    escala: str
    duracion_segundos: int
    registro_vocal: str
    secciones: List[str] = field(default_factory=list)
    observaciones: List[str] = field(default_factory=list)
    origen: Dict[str, str] = field(default_factory=dict)

    def _de(self, campo: str) -> str:
        return "de la letra" if self.origen.get(campo) == "letra" else "por criterio"

    def resumen(self) -> str:
        """Lo que ha decidido y por qué, para decirlo antes de gastar."""
        lineas = [
            f"🎼 Criterio para «{self.titulo}»:",
            f"- Tempo {self.bpm} BPM en {self.compas} ({self._de('bpm')}).",
            f"- {self.tonalidad}, escala {self.escala} ({self._de('escala')}).",
            f"- Voz: {self.registro_vocal}.",
        ]
        if self.secciones:
            lineas.append("- Estructura: " + " → ".join(self.secciones)
                          + f" ({self._de('secciones')}).")
        lineas += [f"- {nota}" for nota in self.observaciones]
        return "\n".join(lineas)

    def prompt(self, letra: str, matices: str = "") -> str:
        """
        El encargo que se manda al motor.

        Las indicaciones van **antes** de la letra y la letra entera al final:
        un proveedor que recorte por longitud debe perder el relleno de estilo
        antes que el texto que hay que cantar.
        """
        cabecera = (
            f"Create a sung song in Spanish titled '{self.titulo}'. Not an instrumental: "
            f"the voice must sing the lyrics. {self.registro_vocal}. "
            f"Tempo {self.bpm} BPM, {self.compas}, {self.tonalidad}, {self.escala} scale. "
            "Japanese/Korean neo-traditional palette with shamisen and koto over deep sub-bass; "
            "industrial cold water and rust atmosphere; leave breathing space between phrases."
        )
        if self.secciones:
            cabecera += " Follow this section order: " + ", ".join(self.secciones) + "."
        cuerpo = ("Sing these exact lyrics in Spanish, preserving stanza and chorus structure "
                  "and the section marks written in the text:\n" + (letra or "")[:12000])
        cola = f"\n\nIndicaciones literales del encargo: {matices}" if matices else ""
        return f"{cabecera}\n\n{cuerpo}{cola}"


def _marca(letra: str, patron: str) -> Optional[str]:
    encontrado = re.search(patron, letra or "", re.IGNORECASE)
    return encontrado.group(1).strip() if encontrado else None


def _bpm_por_densidad(medidas: List[int]) -> Tuple[int, str]:
    """
    Tempo deducido de cuánto pesa el verso medio.

    No hay teoría fina detrás: un verso largo necesita más tiempo por compás
    para no atropellarse, y uno corto aguanta más pulso sin sonar arrastrado.
    Se declara así en vez de presentarlo como una regla de armonía.
    """
    if not medidas:
        return BPM_POR_DEFECTO, "sin versos que medir: tempo por defecto"
    medio = sum(medidas) / len(medidas)
    if medio >= 14:
        return 64, f"verso largo (≈{medio:.0f} sílabas): bajo el pulso para que quepa sin correr"
    if medio <= 8:
        return 84, f"verso corto (≈{medio:.0f} sílabas): subo el pulso para que no se arrastre"
    return 72, f"verso de arte menor (≈{medio:.0f} sílabas): pulso medio"


def leer_criterio(letra: str, titulo: str = "", duracion_segundos: int = 90) -> PlanMusical:
    """
    Lee la letra y decide cómo se compone. Manda lo que la letra ya traiga.

    Devuelve siempre un plan: una letra sin marcas no es un error, es una letra
    que deja las decisiones a quien compone.
    """
    origen: Dict[str, str] = {}
    observaciones: List[str] = []

    marcado_bpm = _marca(letra, r"(\d{2,3})\s*BPM")
    versos = _versos(letra)
    medidas = [silabas(v) for v in versos if silabas(v) > 2]

    if marcado_bpm:
        bpm, origen["bpm"] = int(marcado_bpm), "letra"
    else:
        bpm, motivo = _bpm_por_densidad(medidas)
        origen["bpm"] = "criterio"
        observaciones.append(motivo)

    # El recorte al rango útil no puede ser silencioso: si la letra pide 200 BPM
    # y se compone a 96, seguir diciendo «de la letra» sería mentir sobre una
    # decisión que ya no es suya. Se recorta y se cuenta.
    acotado = max(BPM_MINIMO, min(BPM_MAXIMO, bpm))
    if acotado != bpm:
        observaciones.append(
            f"⚠️ {bpm} BPM queda fuera del rango que la paleta sostiene "
            f"({BPM_MINIMO}–{BPM_MAXIMO}): compongo a {acotado}. Por debajo el shamisen se "
            "deshilacha; por encima el bachi suena a percusión de baile.")
        origen["bpm"] = "criterio"
    bpm = acotado

    compas = _marca(letra, r"(\d/\d)\s*(?:time signature)?") or "4/4"
    origen["compas"] = "letra" if _marca(letra, r"(\d/\d)") else "criterio"

    tonalidad = _marca(letra, r"[Kk]ey:\s*([A-G][#b]?\s*(?:minor|major|menor|mayor))")
    origen["tonalidad"] = "letra" if tonalidad else "criterio"
    tonalidad = f"key of {tonalidad}" if tonalidad else "key of D minor"

    escala = next((e for e in ESCALAS if e in _sin_tildes(letra or "")), None)
    origen["escala"] = "letra" if escala else "criterio"
    escala = escala or "insen"

    secciones = [m.group(0).strip().strip("#").strip() for m in _SECCION.finditer(letra or "")]
    secciones = [re.sub(r"\s+", " ", s) for s in secciones]
    origen["secciones"] = "letra" if secciones else "criterio"

    # --- Lo que se mide de la letra, que es el criterio de verdad -----------
    if medidas:
        medio = sum(medidas) / len(medidas)
        dispersion = (sum((m - medio) ** 2 for m in medidas) / len(medidas)) ** 0.5
        if dispersion > DISPERSION_QUE_ATROPELLA:
            observaciones.append(
                f"⚠️ Métrica desigual (de {min(medidas)} a {max(medidas)} sílabas, "
                f"desviación {dispersion:.1f}): el motor acelerará los versos largos para "
                "alcanzar el compás. Para que no se atropelle, igualar las longitudes."
            )
        else:
            observaciones.append(
                f"Métrica pareja (≈{medio:.0f} sílabas, desviación {dispersion:.1f}): "
                "cada verso cabe en su compás sin correr.")

    terminaciones = [_rima(v) for v in versos if _rima(v)]
    if terminaciones:
        repetidas = len(terminaciones) - len(set(terminaciones))
        if repetidas == 0:
            observaciones.append(
                "⚠️ Sin rimas: nada ancla el peso del compás al oído. En el canto la rima "
                "dice dónde cae el golpe; sin ella la voz queda a la deriva.")
        else:
            observaciones.append(
                f"Rima presente ({repetidas} terminación(es) que vuelven): sostiene el golpe.")

    registro = ("female mature voice, low and resonant at the start, opening into a dramatic "
                "chest voice at the peaks, deliberate breath pauses before downbeats")
    if re.search(r"susurr|whisper|quebrad|roto|desgarr", _sin_tildes(letra or "")):
        registro += ", with intentional vocal cracks and a broken whisper where the text asks"
        observaciones.append("La letra pide quiebre: lo llevo al registro vocal.")

    return PlanMusical(
        titulo=titulo or "Sin título",
        bpm=bpm, compas=compas, tonalidad=tonalidad, escala=escala,
        duracion_segundos=duracion_segundos, registro_vocal=registro,
        secciones=secciones, observaciones=observaciones, origen=origen,
    )
