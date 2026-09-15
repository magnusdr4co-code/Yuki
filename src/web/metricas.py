"""
Las métricas del Salón: el estado de Yuki en formato de exposición.

Vive fuera del manejador HTTP porque no es HTTP: no toca `self` ni la petición,
sólo lee ficheros y configuración. Dentro del manejador eran 164 de sus 667
líneas, y añadir una familia obligaba a abrir el servidor entero.

Se construye sin tocar el agente a propósito: una sonda que despertara la
memoria FTS5 o el modelo cambiaría lo que mide y convertiría al scraper en una
fuente de gasto.
"""

from typing import Any, Dict, List


def exposicion() -> str:
    """El texto completo de `/metrics`, listo para servir."""
    import yaml

    from ..core.agency import AgencyLedger, AgencyPolicy
    from ..core.blackbox import BlackBox
    from ..core.brake import NIVELES, Brake
    from ..core.persona_anchor import PersonaAnchor, PersonaPolicy
    from ..core.pulse import GRAVEDAD, Pulse
    from ..core.spark import MOTIVOS
    from ..core.rituals import RitualStore
    from ..core.spend_budget import (
        PREFIJO_RUTA,
        IMAGENES, MUSICA_PISTAS, MUSICA_SEGUNDOS, TOKENS_ENTRADA, TOKENS_SALIDA,
        VIDEO_SEGUNDOS, VOZ_CARACTERES, SpendLedger,
    )
    from ..core.transparency import audit_directory

    try:
        with open("config.yaml", "r", encoding="utf-8") as fichero:
            config = yaml.safe_load(fichero) or {}
    except OSError:
        config = {}

    # Las familias se acumulan y se vuelcan al final: el formato de
    # exposición exige `# HELP` y `# TYPE` **una vez por familia**, antes de
    # todas sus muestras. Repetirlos por muestra —lo natural al escribir el
    # bucle— hace que un parser estricto rechace la página entera.
    familias: Dict[str, Dict[str, Any]] = {}

    def metrica(nombre: str, ayuda: str, valor: Any, tipo: str = "gauge",
                etiquetas: str = "") -> None:
        familia = familias.setdefault(nombre, {"ayuda": ayuda, "tipo": tipo, "muestras": []})
        sufijo = "{" + etiquetas + "}" if etiquetas else ""
        familia["muestras"].append(f"yuki_{nombre}{sufijo} {valor}")

    # Gasto: lo que de verdad puede dejar a Yuki sin crédito.
    libro = SpendLedger.from_config(config)
    consumo = libro.today()
    # Se emiten todas las unidades conocidas aunque hoy valgan cero. Una
    # familia que desaparece cuando no hay consumo deja al scraper sin poder
    # distinguir «no ha gastado nada» de «la sonda está rota», que es
    # justamente la diferencia que uno quiere ver a las cuatro de la mañana.
    unidades = (VIDEO_SEGUNDOS, IMAGENES, MUSICA_PISTAS, MUSICA_SEGUNDOS,
                VOZ_CARACTERES, TOKENS_ENTRADA, TOKENS_SALIDA)
    for unidad in sorted(set(unidades) | set(consumo) | set(libro.limits)):
        # El desglose por tarea va en su propia familia: mezclarlo aquí
        # multiplicaría las series de `gasto_hoy` por cada ruta declarada y
        # rompería la comparación con los límites, que son del total.
        if unidad.startswith(PREFIJO_RUTA):
            continue
        metrica("gasto_hoy", "Consumo del día por unidad", consumo.get(unidad, 0),
                etiquetas=f'unidad="{unidad}"')
    for unidad, limite in sorted(libro.limits.items()):
        metrica("gasto_limite", "Límite diario por unidad", limite,
                etiquetas=f'unidad="{unidad}"')
    metrica("gasto_usd_estimado", "Coste estimado de hoy en USD (música no cotizada)",
            libro.usd_today())
    # Coste por tarea. El enrutado mandaba un resumen de feed a un modelo
    # barato y una síntesis a uno caro, y el gasto caía todo en el mismo
    # montón: no había forma de ver si la separación servía de algo.
    for ruta, fila in sorted(libro.por_ruta().items()):
        metrica("gasto_texto_usd_por_ruta", "Coste estimado de hoy en USD por tarea de texto",
                fila["usd"], etiquetas=f'ruta="{ruta}"')
        metrica("gasto_tokens_por_ruta", "Tokens de hoy por tarea y sentido",
                fila["entrada"], etiquetas=f'ruta="{ruta}",sentido="entrada"')
        metrica("gasto_tokens_por_ruta", "Tokens de hoy por tarea y sentido",
                fila["salida"], etiquetas=f'ruta="{ruta}",sentido="salida"')

    # Albedrío: cuánta iniciativa está teniendo, y con cuánta tensión.
    politica = AgencyPolicy.from_config(config)
    diario = AgencyLedger(timezone_name=politica.timezone)
    datos = diario.snapshot()
    metrica("agencia_actos_hoy", "Actos autónomos ejecutados hoy", diario.acciones_hoy())
    metrica("agencia_actos_limite", "Techo diario de actos autónomos",
            politica.max_actions_per_day)
    metrica("agencia_aburrimiento", "Tensión acumulada sin actuar (0-1)",
            round(float(datos.get("boredom", 0.0)), 4))
    metrica("agencia_esperando_eco", "Actos autónomos aún sin respuesta",
            len(datos.get("pendientes", [])))

    # Persona: si su voz se está yendo hacia el registro de asistente.
    vigia = PersonaAnchor(policy=PersonaPolicy.from_config(config))
    informe = vigia.report()
    # -1 significa «aún no hay muestras»: un valor imposible en el rango real
    # (0-1) que el panel puede filtrar, en vez de una serie que aparece y
    # desaparece según haya hablado o no.
    metrica("persona_registro", "Fidelidad reciente a su registro (0-1; -1 sin muestras)",
            informe["media_reciente"] if informe["media_reciente"] is not None else -1)
    metrica("persona_reanclajes", "Veces que hubo que reanclar la persona",
            informe["anclajes"], tipo="counter")

    # Cumplimiento: material sintético sin marcar.
    auditoria = audit_directory()
    metrica("material_marcado", "Ficheros generados con marca de origen sintético",
            len(auditoria["marcados"]))
    metrica("material_sin_marcar", "Ficheros generados sin marca (incumplimiento)",
            len(auditoria["sin_marcar"]))

    # Ritmos y bitácora.
    ritmos = RitualStore()
    metrica("ritmos_propios", "Ritmos propios activos", len(ritmos.aprobados()))
    # Ya no hay trámite de aprobación: lo que cuente aquí son ritmos que se
    # quedaron esperando un visto bueno de cuando hacía falta y siguen sin
    # sonar. Cero es lo normal; distinto de cero es un ritmo suyo atrapado.
    metrica("ritmos_propuestos", "Ritmos heredados sin activar (esperan `!ritmo aprobar`)",
            len(ritmos.pendientes()))
    # El freno como número: un panel tiene que poder enseñar que Yuki está
    # parada a propósito, o media hora de silencio parece una avería.
    freno = Brake()
    estado_freno = freno.state()
    metrica("freno_nivel",
            "Freno de mano (0 ninguno, 1 publicación, 2 medios, 3 todo)",
            NIVELES.get(estado_freno.nivel, 0))
    for accion in ("publicar", "medios", "iniciativa"):
        metrica("freno_permite", "1 si el freno deja pasar ese tipo de acto",
                1 if freno.permits(accion) else 0, etiquetas=f'accion="{accion}"')

    # Por qué no actuó, en números. Sin esto, `yuki_agencia_actos_hoy == 0`
    # sólo dice que no hizo nada: no si es fase de silencio, freno, techo
    # diario o que el bucle ni siquiera está corriendo.
    censo = diario.censo()
    for motivo in MOTIVOS:
        metrica("albedrio_ciclos", "Ciclos de evaluación por motivo, últimos días",
                censo.get(motivo, 0), tipo="counter", etiquetas=f'motivo="{motivo}"')

    # Signos vitales. La métrica que faltaba: `up` y `/health` sólo dicen que
    # el proceso contesta, y el fallo más silencioso de esta instancia es
    # justamente que conteste mientras ella no hace absolutamente nada.
    lectura = Pulse(config).read()
    metrica("pulso_gravedad",
            "0 viva o nueva, 1 letargo o freno, 2 catatónica, 3 ausente",
            lectura.gravedad)
    for nombre_estado in GRAVEDAD:
        metrica("pulso_estado", "1 en el estado diagnosticado ahora mismo",
                1 if lectura.estado == nombre_estado else 0,
                etiquetas=f'estado="{nombre_estado}"')
    for signo in lectura.signos:
        # -1 y no cero para «nunca»: un cero aquí se leería como
        # «acaba de ocurrir», que es exactamente lo contrario.
        metrica("signo_edad_segundos",
                "Tiempo desde la última vez que se vio ese signo (-1 si nunca)",
                int(signo.edad) if signo.edad is not None else -1,
                etiquetas=f'signo="{signo.id}",tipo="{signo.tipo}"')

    cadena = BlackBox().verify()
    metrica("bitacora_entradas", "Anotaciones en la bitácora encadenada",
            cadena["entradas"], tipo="counter")
    metrica("bitacora_integra", "1 si la cadena de auditoría no ha sido manipulada",
            1 if cadena["integra"] else 0)

    lineas: List[str] = []
    for nombre, familia in familias.items():
        lineas.append(f"# HELP yuki_{nombre} {familia['ayuda']}")
        lineas.append(f"# TYPE yuki_{nombre} {familia['tipo']}")
        lineas.extend(familia["muestras"])
    return "\n".join(lineas) + "\n"
