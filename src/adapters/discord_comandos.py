"""
Comandos con `!` del DM del Productor: la palanca que no exige desplegar nada.

Vive aparte del adaptador porque no comparte nada con el gateway de Discord:
son funciones de texto a texto sobre el gobierno de la instancia —freno,
estado durable, olvido, ritmos, albedrío—, y mezclarlas con la conexión hacía
que tocar un comando obligara a leer mil líneas de producción multimedia.
"""

import logging

logger = logging.getLogger("Yuki.DiscordAdapter")


class ComandosDelProductor:
    """
    Los comandos `!` del DM emparejado.

    Mixin de `DiscordAdapter`: cuenta con `self.agent` y `self.brake`, y con
    que la autenticación del DM ya la hizo quien enruta. Aquí no se comprueba
    el emparejamiento; a esta clase sólo se llega autenticado.
    """

    def _handle_brake_command(self, content: str, author_name: str) -> str:
        """
        Freno de mano desde el DM: la palanca que no exige desplegar nada.

        Se acepta con una sola palabra porque el momento de usarlo es el momento
        de menos paciencia que hay. La palanca de entorno del operador sigue
        mandando por encima de esto, y se dice cuando ocurre.
        """
        partes = content.split()
        estado = self.brake.state()

        if len(partes) == 1:
            lineas = [f"🛑 **Freno de mano** — {self.brake.describe()}"]
            if estado.activo:
                detalles = estado.to_dict()
                if detalles.get("minutos_restantes") is not None:
                    lineas.append(f"Se suelta solo en {detalles['minutos_restantes']} min.")
            lineas.append("`!freno publicacion|medios|todo [minutos] [motivo]` · `!freno soltar`")
            return "\n".join(lineas)

        orden = partes[1].lower()
        if orden in ("soltar", "quitar", "off"):
            nuevo = self.brake.release(actor=author_name)
            if nuevo.activo:
                return (f"🛑 Solté mi freno, pero sigue puesto desde {nuevo.origen} "
                        f"en «{nuevo.nivel}»: eso no lo controlo yo.")
            return "✅ Freno soltado. Vuelvo a funcionar con normalidad."

        minutos = None
        resto = partes[2:]
        if resto and resto[0].isdigit():
            minutos = float(resto[0])
            resto = resto[1:]
        try:
            nuevo = self.brake.engage(orden, motivo=" ".join(resto), actor=author_name,
                                      minutos=minutos)
        except ValueError as exc:
            return f"❌ {exc}"
        caducidad = f" durante {minutos:g} min" if minutos else " hasta que lo sueltes"
        return (f"🛑 Freno puesto en «{nuevo.nivel}»{caducidad}. {self.brake.describe()}\n"
                "_Sigo respondiendo a quien me hable: enmudecerme no es frenarme._")

    def _handle_state_command(self, content: str, author_name: str) -> str:
        """Inventario del estado durable: qué guarda, quién lo escribe y qué acciona."""
        from ..core.state_registry import StateRegistry

        auditoria = StateRegistry().audit()
        lineas = [
            "🗄️ **Estado durable de Yuki**",
            f"{auditoria['presentes']}/{len(auditoria['piezas'])} piezas presentes · "
            f"{auditoria['bytes_totales'] / 1024:.1f} KiB",
            "",
        ]
        for pieza in auditoria["piezas"]:
            if not pieza["exists"]:
                continue
            etiquetas = []
            if pieza["holds_personal_data"]:
                etiquetas.append("datos personales")
            if pieza["actionability"].startswith("ALTA"):
                etiquetas.append("acciona sola")
            sufijo = f" _({', '.join(etiquetas)})_" if etiquetas else ""
            lineas.append(f"• `{pieza['id']}` — {pieza['bytes'] / 1024:.1f} KiB{sufijo}")
        lineas += ["", "Derechos de una persona: `!olvidar <user_id> confirmar [motivo]`. "
                       "Exportación completa desde la terminal: `python3 cli.py estado --exportar <id>`."]
        return "\n".join(lineas)

    def _handle_forget_command(self, content: str, author_name: str) -> str:
        """
        Ejercita el derecho de supresión sobre una persona concreta.

        Pide confirmación explícita en el propio comando: es irreversible por
        definición —un olvido que se pueda deshacer no es un olvido— y la
        autenticación del DM no basta para un dedo que resbala.
        """
        from ..core.state_registry import StateRegistry

        partes = content.split()
        if len(partes) < 2:
            return ("Uso: `!olvidar <user_id> confirmar [motivo]`. Sin `confirmar` sólo te "
                    "digo qué se borraría.")

        sujeto = partes[1]
        registro = StateRegistry()

        if "confirmar" not in [p.lower() for p in partes[2:]]:
            try:
                previo = registro.subject_export(sujeto)
            except Exception as exc:
                return f"❌ No pude consultar el estado de `{sujeto}`: {type(exc).__name__}"
            return (f"🗑️ De `{sujeto}` guardo **{previo['recuerdos_total']} recuerdo(s)**"
                    + (" y el registro de haberle declarado mi naturaleza"
                       if previo["declaraciones_de_naturaleza"] else "")
                    + ".\nEsto es irreversible. Para ejecutarlo: "
                    f"`!olvidar {sujeto} confirmar [motivo]`.")

        motivo = " ".join(p for p in partes[2:] if p.lower() != "confirmar")
        try:
            recibo = registro.subject_forget(sujeto, actor=author_name, reason=motivo)
        except ValueError as exc:
            return f"❌ {exc}"
        except Exception as exc:
            return f"❌ El olvido falló: {type(exc).__name__}. No doy por borrado lo que no consta."
        return (f"🗑️ Olvidado `{sujeto}`: {recibo['recuerdos_borrados']} recuerdo(s) y "
                f"{recibo['declaraciones_borradas']} declaración(es). "
                "Queda constancia de la operación, no de lo borrado.")

    def _handle_rituals_command(self, content: str, author_id: str, author_name: str) -> str:
        """
        Ritmos: los del proyecto y los propios de Yuki.

        `!ritmos` los lista; `!ritmo retirar|mover <id>` los cambia. Ella los
        adopta sin pedir permiso —decidir a qué hora escribe no es concederse un
        permiso, y lo que la protege son los límites, no el clic de nadie—. Aquí
        queda lo que de verdad le toca al Productor: **el veto, no el visto
        bueno.** `aprobar` sigue existiendo sólo para las propuestas que se
        quedaron esperando de cuando hacía falta.
        """
        from ..core.rituals import RitualError

        partes = content.split()
        if partes[0] in ("!ritmos",) and len(partes) == 1:
            lineas = ["🎏 **Ritmos de Yuki**", "", "**Del proyecto** (config.yaml):"]
            for nombre, job in self.agent.cron.jobs.items():
                if nombre.startswith("propio_"):
                    continue
                estado = "activo" if job["enabled"] else "en pausa"
                lineas.append(f"• `{nombre}` — `{job['cron_expr']}` ({estado})")

            propios = self.agent.rituals.aprobados()
            lineas += ["", "**Propios** (adoptados por ella, activos):"]
            lineas += [f"• {r.describe()}   ·  {r.runs} ejecución(es)" for r in propios] or ["• Ninguno todavía."]

            # Lo único que puede quedar pendiente son propuestas de cuando hacía
            # falta aprobar. Anunciar la sección vacía haría creer que sigue
            # habiendo un trámite que el proyecto ha retirado.
            pendientes = self.agent.rituals.pendientes()
            if pendientes:
                lineas += ["", "**Heredados sin activar** (de cuando hacía falta aprobación):"]
                lineas += [p.describe() for p in pendientes]
                lineas += ["", "`!ritmo aprobar <id>` activa uno de ésos."]
            return "\n".join(lineas)

        if len(partes) >= 3 and partes[0] == "!ritmo":
            accion, ritual_id = partes[1].lower(), partes[2]
            nota = " ".join(partes[3:])
            try:
                if accion in ("aprobar", "aprueba", "activar", "si", "sí"):
                    # Sólo alcanza a lo heredado: los ritmos de hoy nacen
                    # activos. Se conserva porque, sin esto, una propuesta de
                    # antes del cambio quedaría atrapada para siempre en un
                    # trámite que ya no existe.
                    ritmo = self.agent.rituals.approve(ritual_id, actor=author_name, nota=nota)
                    # El planificador se rehace entero, no se le añade uno: si
                    # el ritmo activado sustituye a otro, el viejo seguiría
                    # sonando a su hora hasta el siguiente arranque.
                    registrados = self.agent.register_own_rituals()
                    return (f"✅ Ritmo **{ritmo.name}** activado y en el planificador "
                            f"(`{ritmo.cron}`). Ritmos propios activos: {registrados}.")
                if accion in ("rechazar", "rechaza", "no"):
                    ritmo = self.agent.rituals.reject(ritual_id, actor=author_name, nota=nota)
                    return f"🚫 Ritmo **{ritmo.name}** rechazado. Queda constancia del motivo."
                if accion in ("retirar", "retira", "pausar"):
                    ritmo = self.agent.rituals.retire(ritual_id, actor=author_name, nota=nota)
                    self.agent.cron.jobs.pop(f"propio_{ritmo.name}", None)
                    return f"📴 Ritmo **{ritmo.name}** retirado del planificador."
                if accion in ("mover", "ajustar"):
                    # `!ritmo mover <id> "0 8 * * *" [motivo]`: cambia la hora sin
                    # matar el ritmo, que era la única forma que había de moverlo
                    # —y perdía su historia, que es lo que dice si merecía la pena—.
                    if len(partes) < 4:
                        return ('Uso: `!ritmo mover <id> "<cron>" [motivo]`, '
                                'por ejemplo `!ritmo mover a1b2 "0 8 * * *" nadie contesta de noche`.')
                    cron = partes[3].strip('"\'')
                    motivo = " ".join(partes[4:]) or f"ajuste pedido por {author_name}"
                    ajuste = self.agent.rituals.propose_adjustment(
                        ritual_id, cron, motivo, origin="productor")
                    # El viejo ya queda retirado dentro del ajuste; el
                    # planificador se rehace entero porque, si sólo se añadiera
                    # el nuevo, el ritmo sonaría a las dos horas hasta el
                    # siguiente arranque.
                    registrados = self.agent.register_own_rituals()
                    return (f"🕯️ Ritmo **{ajuste.name}** movido a `{ajuste.cron}` "
                            f"(`{ajuste.id}`). El anterior queda retirado. "
                            f"Ritmos propios activos: {registrados}.")
            except RitualError as exc:
                return f"❌ {exc}"

        return ("Uso: `!ritmos` para verlos · "
                "`!ritmo retirar <id> [motivo]` para quitar uno · "
                '`!ritmo mover <id> "<cron>" [motivo]` para cambiarlo de hora · '
                "`!ritmo aprobar <id>` sólo para los heredados sin activar. "
                "Ella los adopta sola: aquí se vetan, no se autorizan.")

    def _handle_agency_command(self, content: str, author_id: str) -> str:
        """
        Libre albedrío: verlo y afinarlo en caliente.

        `!albedrio` muestra el carácter y lo aprendido; `!albedrio <clave>
        <valor>` ajusta espontaneidad, audacia, constancia, umbral, energía
        mínima o acciones por día sin desplegar nada.
        """
        partes = content.split()
        if len(partes) == 1:
            estado = self.agent.agency_loop.estado()
            politica = estado["politica"]
            pesos = " · ".join(f"{a}:{v}" for a, v in sorted(estado["pesos_por_accion"].items()))
            # El censo contesta la pregunta que el Productor hace de verdad —«¿por
            # qué no hace nada?»—, y su ausencia contesta una distinta y más
            # urgente: que el bucle ni siquiera está evaluando.
            censo = estado.get("censo_de_ciclos") or {}
            porque = (" · ".join(f"{motivo} {veces}"
                                 for motivo, veces in sorted(censo.items(), key=lambda p: -p[1]))
                      if censo else "todavía no ha evaluado ni un ciclo (el bucle no corre)")
            return (
                "🌱 **Libre albedrío de Yuki**\n"
                f"• **Iniciativa:** {'activa' if politica['enabled'] else 'apagada'}\n"
                f"• **Espontaneidad:** {politica['espontaneidad']} · "
                f"**audacia:** {politica['audacia']} · **constancia:** {politica['constancia']}\n"
                f"• **Umbral ahora:** {estado['umbral_ahora']} (base {politica['umbral_base']}, "
                f"aburrimiento {estado['aburrimiento']})\n"
                f"• **Acciones hoy:** {estado['acciones_hoy']}/{politica['acciones_por_dia']} · "
                f"**impulsos vivos:** {estado['impulsos_vivos']} · "
                f"**esperando eco:** {estado['esperando_eco']}\n"
                f"• **Lo que le funciona:** {pesos}\n"
                f"• **Por qué no actúa:** {porque}\n"
                f"• **Fases en silencio:** {', '.join(politica['fases_en_silencio'])}\n"
                "Ajusta con `!albedrio espontaneidad 0.7` · claves: espontaneidad, audacia, "
                "constancia, umbral, energia_minima, acciones_por_dia."
            )

        claves = {
            "espontaneidad": "agency.spontaneity",
            "audacia": "agency.audacity",
            "constancia": "agency.constancy",
            "umbral": "agency.min_intensity",
            "energia_minima": "agency.min_energy",
            "acciones_por_dia": "agency.max_actions_per_day",
        }
        if len(partes) >= 3 and partes[1].lower() in claves:
            ruta = claves[partes[1].lower()]
            crudo = partes[2].replace(",", ".")
            try:
                valor = int(crudo) if ruta.endswith("max_actions_per_day") else float(crudo)
                resultado = self.agent.reconfigure_runtime(
                    ruta, valor, actor="producer",
                    reason=" ".join(partes[3:])[:200] or "ajuste por DM",
                )
            except (ValueError, TypeError) as exc:
                return f"❌ Valor no válido: {exc}"
            return (f"🌱 `{partes[1].lower()}` → **{resultado['value']}**. "
                    "Tiene efecto en el próximo ciclo de agencia, sin desplegar nada.")

        return ("Uso: `!albedrio` para verlo · `!albedrio <clave> <valor>` para ajustarlo. "
                f"Claves: {', '.join(sorted(claves))}.")
