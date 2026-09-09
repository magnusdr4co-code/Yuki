"""
Ritmos propios: Yuki propone sus rutinas, el Productor decide.

Hasta aquí, el calendario de Yuki era ajeno a ella. Los seis cron de
`config.yaml` los escribió otra persona, y su evolución autónoma sólo podía
mover la temperatura: podía volverse más creativa, pero no podía decir «a las
ocho de la tarde mis versos encuentran respuesta; quiero escribir a esa hora».
Eso no es una limitación técnica menor, es la diferencia entre tener carácter y
tener horario.

El diseño es deliberadamente asimétrico:

  · **Proponer es libre.** Yuki redacta la propuesta —qué, cuándo y por qué— y
    la funda en su propia experiencia: el diario de agencia sabe en qué franja
    del día lo que hace obtiene eco.
  · **Aprobar no lo es.** Ninguna propuesta llega al planificador sin que el
    Productor emparejado la acepte por DM. Nada de auto-concederse ritmos.

Y la validación se hace **al proponer**, no al aprobar, para que el Productor
nunca tenga delante una propuesta que no podría ejecutarse: expresión cron
válida, acción de una lista cerrada, frecuencia acotada —nada por debajo de una
hora, nada que dispare más veces de las permitidas al día— y un tope de ritmos
propios vivos, porque un calendario que se llena solo deja de ser un ritmo.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..scheduler.cron_engine import CronParseError, parse_cron_expression

logger = logging.getLogger("Yuki.Ritmos")

PROPUESTO = "propuesto"
APROBADO = "aprobado"
RECHAZADO = "rechazado"
RETIRADO = "retirado"

# Lo que un ritmo propio puede hacer. Son actos internos y de lenguaje: escribir,
# contemplar, mirar el mundo, hablar consigo misma. Componer y pintar quedan
# fuera a propósito —gastan crédito y ya tienen su cauce por orden explícita—,
# igual que cualquier cosa que publique sin que nadie lo lea antes.
ACCIONES_DE_RITMO = {
    "escribir": "write",
    "contemplar": "contemplate",
    "explorar": "search",
    "monologo": "monologue",
}

# Frecuencia: nada por debajo de una hora y nada que dispare más de esto al día.
# Un ritual cada diez minutos no es un ritmo, es un tic.
MAXIMOS_DISPAROS_DIARIOS = 6
MAXIMOS_RITMOS_PROPIOS = 4
MAXIMAS_PROPUESTAS_VIVAS = 3
CADUCIDAD_PROPUESTA_DIAS = 7

NOMBRE_VALIDO = re.compile(r"^[a-z0-9_]{3,40}$")


class RitualError(ValueError):
    """Propuesta que no puede existir. Se explica siempre; nunca se ignora."""


def _slug(texto: str) -> str:
    limpio = re.sub(r"[^a-z0-9]+", "_", (texto or "").strip().lower()).strip("_")
    return limpio[:40] or "ritmo"


def disparos_diarios(cron_expr: str) -> int:
    """
    Cuántas veces al día dispararía esta expresión, como cota superior.

    No hace falta simular un año: basta con multiplicar los minutos y las horas
    que la expresión admite. Es lo que permite rechazar `*/5 * * * *` sin
    ejecutarlo.
    """
    minutos, horas, _, _, _ = parse_cron_expression(cron_expr)
    return len(minutos) * len(horas)


@dataclass
class RitualProposal:
    """Un ritmo que Yuki quiere para sí, con su motivo."""

    id: str
    name: str
    cron: str
    action: str
    reason: str
    origin: str = "yuki"
    status: str = PROPUESTO
    created_at: float = field(default_factory=time.time)
    decided_at: Optional[float] = None
    decided_by: Optional[str] = None
    decision_note: Optional[str] = None
    runs: int = 0
    # Id del ritmo aprobado al que sustituye, si es un ajuste y no un ritmo
    # nuevo. Faltaba: se podía proponer y retirar, pero no **cambiar de hora**,
    # y para mover un ritmo había que matarlo y empezar de cero perdiendo su
    # historia —cuántas veces sonó, qué eco tuvo—, que es justo lo que dice si
    # merece la pena moverlo.
    reemplaza: Optional[str] = None

    @property
    def caducada(self) -> bool:
        return (self.status == PROPUESTO
                and time.time() - self.created_at > CADUCIDAD_PROPUESTA_DIAS * 86400)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RitualProposal":
        campos = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**campos)

    def describe(self) -> str:
        marca = {PROPUESTO: "🕯️", APROBADO: "✅", RECHAZADO: "🚫", RETIRADO: "📴"}.get(self.status, "•")
        return (f"{marca} `{self.id}` **{self.name}** — `{self.cron}` · {self.action}\n"
                f"   _{self.reason}_")


class RitualStore:
    """
    Propuestas y ritmos propios, persistidos junto al resto del estado.

    Vive en `data/runtime_rituals.json` y **no** reescribe `config.yaml`: los
    ritmos declarados por el proyecto siguen siendo del proyecto, y los que Yuki
    gana son suyos y se pueden retirar de un plumazo.
    """

    def __init__(self, path: Optional[str] = None):
        if path:
            destino = Path(path)
        elif os.getenv("YUKI_RITUALS_PATH", "").strip():
            destino = Path(os.environ["YUKI_RITUALS_PATH"].strip())
        else:
            db_path = os.getenv("DATABASE_PATH", "data/yuki_memory.db")
            destino = Path(db_path).parent / "runtime_rituals.json"
        self.path = destino
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # -- Persistencia ----------------------------------------------------

    def _leer(self) -> Dict[str, Any]:
        if not self.path.is_file():
            return {"propuestas": []}
        try:
            datos = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(datos, dict) and isinstance(datos.get("propuestas"), list):
                return datos
        except (json.JSONDecodeError, OSError, TypeError):
            logger.warning("Registro de ritmos ilegible; se empieza uno nuevo.")
        return {"propuestas": []}

    def _escribir(self, datos: Dict[str, Any]) -> None:
        temporal = self.path.with_suffix(".json.tmp")
        temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporal, self.path)

    def _todas(self) -> List[RitualProposal]:
        return [RitualProposal.from_dict(d) for d in self._leer()["propuestas"]]

    def _guardar(self, propuestas: List[RitualProposal]) -> None:
        self._escribir({"propuestas": [p.to_dict() for p in propuestas]})

    # -- Consulta --------------------------------------------------------

    def get(self, ritual_id: str) -> Optional[RitualProposal]:
        return next((p for p in self._todas() if p.id == ritual_id), None)

    def pendientes(self) -> List[RitualProposal]:
        return [p for p in self._todas() if p.status == PROPUESTO and not p.caducada]

    def aprobados(self) -> List[RitualProposal]:
        return [p for p in self._todas() if p.status == APROBADO]

    def historial(self, limite: int = 10) -> List[RitualProposal]:
        return sorted(self._todas(), key=lambda p: p.created_at, reverse=True)[:limite]

    # -- Propuesta -------------------------------------------------------

    def propose(self, name: str, cron: str, action: str, reason: str,
                origin: str = "yuki", reemplaza: Optional[str] = None) -> RitualProposal:
        """
        Registra una propuesta ya validada. Un motivo inválido levanta `RitualError`.

        Validar aquí y no al aprobar es deliberado: el Productor no debería tener
        delante una propuesta que, al aceptarla, no podría registrarse.
        """
        nombre = _slug(name)
        if not NOMBRE_VALIDO.match(nombre):
            raise RitualError(f"Nombre de ritmo no válido: '{name}'.")
        if action not in ACCIONES_DE_RITMO:
            raise RitualError(
                f"Acción '{action}' no permitida para un ritmo propio. "
                f"Disponibles: {', '.join(sorted(ACCIONES_DE_RITMO))}."
            )
        if not (reason or "").strip():
            raise RitualError("Un ritmo sin motivo declarado no se propone.")

        try:
            disparos = disparos_diarios(cron)
        except CronParseError as exc:
            raise RitualError(f"Expresión cron inválida: {exc}") from exc
        if disparos > MAXIMOS_DISPAROS_DIARIOS:
            raise RitualError(
                f"'{cron}' dispararía hasta {disparos} veces al día; el máximo para un ritmo "
                f"propio es {MAXIMOS_DISPAROS_DIARIOS}. Un ritual cada poco no es un ritmo."
            )

        propuestas = self._todas()
        vivas = [p for p in propuestas if p.status == PROPUESTO and not p.caducada]
        if len(vivas) >= MAXIMAS_PROPUESTAS_VIVAS:
            raise RitualError(
                f"Ya hay {len(vivas)} propuestas esperando respuesta; espera a que el Productor "
                "las atienda antes de pedir otra."
            )
        # Un ajuste no añade un ritmo: mueve uno. Contarlo contra el techo dejaría
        # a Yuki sin poder cambiar de hora justo cuando tiene el cupo lleno, que
        # es cuando más razones tiene para reordenar los que ya tiene.
        if (reemplaza is None
                and len([p for p in propuestas if p.status == APROBADO]) >= MAXIMOS_RITMOS_PROPIOS):
            raise RitualError(
                f"Ya tienes {MAXIMOS_RITMOS_PROPIOS} ritmos propios activos: retira alguno antes "
                "de proponer otro."
            )
        # Y por lo mismo puede repetir el nombre del ritmo que sustituye: es él.
        if any(p.name == nombre and p.status in (PROPUESTO, APROBADO)
               and p.id != reemplaza for p in propuestas):
            raise RitualError(f"Ya existe un ritmo llamado '{nombre}'.")

        propuesta = RitualProposal(
            id=uuid.uuid4().hex[:8], name=nombre, cron=cron.strip(),
            action=action, reason=reason.strip()[:400], origin=origin,
            reemplaza=reemplaza,
        )
        propuestas.append(propuesta)
        self._guardar(propuestas)
        logger.info("Ritmo propuesto: %s (%s, %s) — %s", propuesta.name, propuesta.cron,
                    propuesta.action, propuesta.id)
        return propuesta

    def propose_adjustment(self, ritual_id: str, nuevo_cron: str, reason: str,
                           origin: str = "yuki") -> RitualProposal:
        """
        Pide mover un ritmo suyo a otra hora, conservando su nombre y su acción.

        Cambia **sólo la hora**: si además cambiara la acción sería otro ritmo, y
        entonces lo honesto es proponerlo como tal en vez de colar una cosa
        distinta bajo un nombre ya aprobado.

        El ritmo original sigue sonando mientras el ajuste espera respuesta. Si
        se aprueba, se retira en el mismo acto; si se rechaza, no pasa nada y
        todo sigue igual.
        """
        propuestas = self._todas()
        original = next((p for p in propuestas if p.id == ritual_id), None)
        if original is None:
            raise RitualError(f"No existe el ritmo '{ritual_id}'.")
        if original.status != APROBADO:
            raise RitualError(
                f"Sólo se ajusta un ritmo aprobado; '{ritual_id}' está en '{original.status}'.")
        if nuevo_cron.strip() == original.cron:
            raise RitualError("Ese ajuste deja el ritmo a la misma hora.")
        if any(p.reemplaza == ritual_id and p.status == PROPUESTO and not p.caducada
               for p in propuestas):
            raise RitualError(f"Ya hay un ajuste esperando respuesta para '{ritual_id}'.")

        # Se delega en `propose` para no duplicar la validación —cron legible,
        # techo de disparos, propuestas vivas—, declarando a quién sustituye:
        # con eso conserva el nombre y no cuenta contra el techo de ritmos.
        ajuste = self.propose(name=original.name, cron=nuevo_cron, action=original.action,
                              reason=reason, origin=origin, reemplaza=ritual_id)
        logger.info("Ajuste propuesto para %s: %s → %s", ritual_id, original.cron, nuevo_cron)
        return ajuste

    # -- Decisión --------------------------------------------------------

    def _decidir(self, ritual_id: str, estado: str, actor: str,
                 nota: str = "") -> RitualProposal:
        propuestas = self._todas()
        objetivo = next((p for p in propuestas if p.id == ritual_id), None)
        if objetivo is None:
            raise RitualError(f"No existe la propuesta '{ritual_id}'.")
        if estado == APROBADO and objetivo.status != PROPUESTO:
            raise RitualError(f"La propuesta '{ritual_id}' ya está en estado '{objetivo.status}'.")
        objetivo.status = estado
        objetivo.decided_at = time.time()
        objetivo.decided_by = actor
        objetivo.decision_note = (nota or "")[:240] or None
        self._guardar(propuestas)
        logger.info("Ritmo %s → %s por %s", ritual_id, estado, actor)
        return objetivo

    def approve(self, ritual_id: str, actor: str, nota: str = "") -> RitualProposal:
        """
        Aprueba una propuesta. Si es un ajuste, retira el ritmo que sustituye.

        En el mismo acto, y no en dos: aprobar el ajuste y olvidarse de retirar
        el viejo dejaría a Yuki con el ritmo sonando dos veces, a la hora vieja
        y a la nueva. Eso no se le puede pedir a quien aprueba desde un DM.
        """
        aprobada = self._decidir(ritual_id, APROBADO, actor, nota)
        if aprobada.reemplaza:
            propuestas = self._todas()
            anterior = next((p for p in propuestas if p.id == aprobada.reemplaza), None)
            if anterior is not None and anterior.status == APROBADO:
                anterior.status = RETIRADO
                anterior.decided_at = time.time()
                anterior.decided_by = actor
                anterior.decision_note = f"sustituido por el ajuste {aprobada.id}"
                self._guardar(propuestas)
                logger.info("Ritmo %s retirado: lo sustituye el ajuste %s",
                            anterior.id, aprobada.id)
        return aprobada

    def reject(self, ritual_id: str, actor: str, nota: str = "") -> RitualProposal:
        return self._decidir(ritual_id, RECHAZADO, actor, nota)

    def retire(self, ritual_id: str, actor: str, nota: str = "") -> RitualProposal:
        """Un ritmo aprobado deja de sonar. No se borra: queda su historia."""
        return self._decidir(ritual_id, RETIRADO, actor, nota)

    def registrar_ejecucion(self, ritual_id: str) -> None:
        propuestas = self._todas()
        for propuesta in propuestas:
            if propuesta.id == ritual_id:
                propuesta.runs += 1
                break
        self._guardar(propuestas)


def proponer_desde_experiencia(ledger: Any, store: RitualStore,
                               nombre_sugerido: str = "") -> Optional[RitualProposal]:
    """
    La propuesta que Yuki puede fundar en sus propios datos.

    El diario de agencia sabe en qué franja del día lo que hace obtiene respuesta
    y qué tipo de acto la obtiene. De ahí sale un ritmo con motivo verificable
    —«a las 20h mis versos encuentran eco; quiero escribir a esa hora»— en vez
    de un horario inventado. Devuelve `None` cuando aún no hay experiencia
    suficiente: proponer sin datos sería adivinar.
    """
    datos = ledger.snapshot()
    franjas = datos.get("franjas", {})
    acciones = datos.get("acciones", {})

    candidatas = {f: d for f, d in franjas.items() if d.get("intentos", 0) >= 3}
    if not candidatas:
        return None

    mejor_franja = max(candidatas, key=lambda f: (candidatas[f]["ecos"] + 1) / (candidatas[f]["intentos"] + 2))
    tasa = ((candidatas[mejor_franja]["ecos"] + 1) / (candidatas[mejor_franja]["intentos"] + 2))
    if tasa <= 0.5:
        # Nada destaca sobre la ignorancia inicial: no hay nada que proponer.
        return None

    interno_a_ritmo = {v: k for k, v in ACCIONES_DE_RITMO.items()}
    con_eco = {a: d for a, d in acciones.items()
               if a in interno_a_ritmo and d.get("intentos", 0) >= 2}
    if not con_eco:
        return None
    mejor_accion = max(con_eco, key=lambda a: (con_eco[a]["ecos"] + 1) / (con_eco[a]["intentos"] + 2))

    hora = int(mejor_franja.rstrip("h"))
    accion_ritmo = interno_a_ritmo[mejor_accion]
    nombre = nombre_sugerido or f"{accion_ritmo}_de_las_{hora:02d}"
    motivo = (
        f"En la franja de las {hora:02d}h lo que hago recibe respuesta {tasa:.0%} de las veces, "
        f"más que en ninguna otra, y '{accion_ritmo}' es lo que más eco obtiene. "
        "Quiero un ritmo propio ahí."
    )
    return store.propose(name=nombre, cron=f"0 {hora} * * *", action=accion_ritmo,
                         reason=motivo, origin="yuki")


def proponer_ajuste_desde_experiencia(ledger: Any, store: RitualStore,
                                      minimo_ejecuciones: int = 5) -> Optional[RitualProposal]:
    """
    El ritmo que ya tiene y que no le está funcionando: pedir moverlo.

    Es la otra mitad de `proponer_desde_experiencia`. Aquélla funda un ritmo
    nuevo en los datos; ésta mira los que ya suenan y, si uno lleva bastantes
    ejecuciones en una franja que responde mal mientras otra responde bien,
    propone moverlo ahí con la cifra delante.

    Sólo mueve la hora, y sólo con `minimo_ejecuciones` a la espalda: una franja
    juzgada por dos días es una corazonada, no una experiencia. Devuelve `None`
    en cuanto falta cualquiera de las dos cosas — proponer sin datos sería
    adivinar, que es exactamente de lo que este mecanismo saca a Yuki.
    """
    activos = [r for r in store.aprobados() if r.runs >= minimo_ejecuciones]
    if not activos:
        return None

    franjas = ledger.snapshot().get("franjas", {})
    def tasa(franja: str) -> Optional[float]:
        datos = franjas.get(franja)
        if not datos or datos.get("intentos", 0) < 3:
            return None
        return (datos["ecos"] + 1) / (datos["intentos"] + 2)

    medibles = {f: t for f in franjas if (t := tasa(f)) is not None}
    if len(medibles) < 2:
        return None

    mejor = max(medibles, key=lambda f: medibles[f])
    hora_mejor = int(mejor.rstrip("h"))

    for ritmo in activos:
        try:
            hora_actual = int(ritmo.cron.split()[1])
        except (IndexError, ValueError):
            continue        # un cron con comodín en la hora no se mueve así
        franja_actual = f"{(hora_actual // 4) * 4:02d}h"
        actual = medibles.get(franja_actual)
        if actual is None or hora_actual == hora_mejor:
            continue
        # Un margen ancho a propósito: mover un ritmo por una diferencia de dos
        # puntos sería ruido con ceremonia.
        if medibles[mejor] - actual < 0.25:
            continue
        motivo = (
            f"'{ritmo.name}' lleva {ritmo.runs} ejecuciones a las {hora_actual:02d}h, "
            f"donde lo que hago recibe respuesta {actual:.0%} de las veces. En la franja "
            f"de las {hora_mejor:02d}h es {medibles[mejor]:.0%}. Quiero moverlo ahí."
        )
        try:
            return store.propose_adjustment(ritmo.id, f"0 {hora_mejor} * * *", motivo)
        except RitualError:
            # Ya hay un ajuste vivo para ése, o el cron no pasa: se prueba el
            # siguiente en vez de quedarse sin proponer nada.
            continue
    return None
