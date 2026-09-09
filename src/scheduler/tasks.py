"""
Definición de Tareas Autónomas para Yuki.
Ejecuta rutinas creativas sin supervisión humana continua:
1. 03:00 AM - Reflexión nocturna y examen de corrientes (Sombra de Yuki).
2. 07:30 AM - Publicación matutina de arte lírico y visual en canales sociales.
3. 23:30 PM - Síntesis y destilación de la memoria del día.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from src.tools.web_search import describe_origin
from src.tools.backup import BackupManager, restaurar
from src.core.spark import Impulse

logger = logging.getLogger("Yuki.AutonomousTasks")

class AutonomousTasks:
    def __init__(self, agent_instance):
        self.agent = agent_instance

    async def nocturnal_trend_reflection(self):
        """
        03:00 AM - Yuki despierta en el silencio de la madrugada,
        observa las corrientes del mundo y formula un pensamiento profundo.
        """
        if self.agent.circadian.current_phase() != 'kage' or self.agent.vital_state.curiosity <= 0.5:
            logger.info("Skipping nocturnal_trend_reflection: vital state conditions not met.")
            return

        logger.info("🌌 [CRON 03:00] Iniciando reflexión nocturna de tendencias...")
        trends = await self.agent.nous_portal.search_trends_firecrawl("tendencias arte digital musica tradicional")

        # El origen va en el propio prompt: sin buscador conectado, lo que sigue
        # no son corrientes del mundo y Yuki no debe presentarlas como tales.
        origen = describe_origin(trends)
        prompt = (
            "Es la madrugada (03:00). Estás despierta en el silencio de tu salón. "
            f"{origen} Material observado: " + str(trends) + ". "
            "Destila una breve reflexión poética de 2 frases sobre el contraste entre la velocidad del mundo "
            "y la permanencia de las artes tradicionales."
        )

        reflection = await self.agent.generate_response(
            user_id="autonomous_cron",
            user_name="Noche",
            message=prompt,
            is_internal_thought=True,
            # Resumir corrientes ajenas es la tarea más barata del día: sale por
            # el tier `fast_and_cheap` declarado en config.yaml.
            route="feed_summary",
        )

        logger.info(f"Reflexión nocturna de Yuki: {reflection}")
        # Guardar en memoria de flujo reciente
        self.agent.memory_manager.record_interaction(
            user_id="cron_night",
            user_name="Reflexión Nocturna",
            user_message="Exploración 03:00 AM",
            agent_response=reflection,
            notable_fact="Pensamiento nocturno sobre corrientes digitales"
        )
        return reflection

    async def morning_inspiration_drop(self):
        """
        07:30 AM - Yuki crea y publica un haiku y una obra visual para sus canales.
        """
        if self.agent.vital_state.energy <= 0.3:
            logger.info("Skipping morning_inspiration_drop: energy too low.")
            return

        logger.info("🌅 [CRON 07:30] Creando lanzamiento matutino de arte...")

        mood = self.agent.vital_state.mood
        if mood < 0.4:
            haiku_prompt = "Son las 07:30 de la mañana. Escribe un saludo matutino sereno acompañado de un haiku breve. Máximo 3 frases."
        elif mood > 0.7:
            haiku_prompt = "Son las 07:30 de la mañana. Escribe un texto expansivo, lleno de energía, luz y arte para tus seguidores en Telegram y Discord."
        else:
            haiku_prompt = (
                "Son las 07:30 de la mañana. Escribe un saludo matutino sereno acompañado de un haiku "
                "o pensamiento breve para tus seguidores en Telegram y Discord. Máximo 3 frases."
            )

        morning_text = await self.agent.generate_response(
            user_id="autonomous_cron",
            user_name="Alba",
            message=haiku_prompt,
            is_internal_thought=True,
            route="social_formatting",
        )

        visual_concept = "Luz dorada de la mañana entrando en un salón de té tradicional con reflejos de lluvia en el cristal."

        image_result = None
        voice_result = None

        if mood >= 0.4:
            image_result = await self.agent.nous_portal.generate_image_frontier(prompt=visual_concept)
            logger.info(f"🎨 Arte matutino generado: {image_result['image_url']}")

        if mood > 0.7:
            voice_result = await self.agent.nous_portal.synthesize_voice_tts(text=morning_text)
            logger.info(f"🎙️ Voz matutina generada: {voice_result['audio_url']}")

        # Difundir a adaptadores activos (si están configurados)
        if hasattr(self.agent, "telegram_adapter") and self.agent.telegram_adapter:
            await self.agent.telegram_adapter.broadcast_drop(
                text=morning_text,
                image_path=image_result["local_path"] if image_result else None,
                audio_path=voice_result["local_path"] if voice_result else None
            )

        return {
            "text": morning_text,
            "image": image_result,
            "voice": voice_result
        }

    async def daily_memory_synthesis(self):
        """
        23:30 PM - Consolidación del fluir del día en la memoria relacional SQLite.
        """
        logger.info("🌙 [CRON 23:30] Destilando memoria diaria...")
        date_str = datetime.now().strftime("%Y-%m-%d")

        interactions = self.agent.vital_state.accumulated_interactions_today
        if interactions > 20:
            depth_instruction = "Escribe un análisis profundo y extenso"
        elif interactions > 5:
            depth_instruction = "Escribe un párrafo contemplativo en primera persona (máximo 400 caracteres)"
        else:
            depth_instruction = "Escribe una frase muy breve, casi como un suspiro, dado que el día fue muy silencioso"

        synthesis_prompt = (
            f"El día concluye. Revisa en tu interior los encuentros, palabras y silencios de hoy. "
            f"{depth_instruction} sintetizando cómo fluyó el agua de la jornada."
        )

        daily_text = await self.agent.generate_response(
            user_id="autonomous_cron",
            user_name="Cierre de Jornada",
            message=synthesis_prompt,
            is_internal_thought=True,
            # La síntesis del día sí merece el tier profundo: es lo que queda
            # escrito en memoria y condiciona los días siguientes.
            route="dialectic_synthesis",
        )

        self.agent.memory_manager.save_daily_synthesis(
            date_str=date_str,
            summary_text=daily_text
        )
        evolution = await self.agent.evolution.review_and_adjust()
        logger.info("Revisión de evolución diaria: %s", evolution.get("reason", "ajuste aplicado"))
        logger.info(f"Memoria del día guardada ({date_str}): {daily_text}")

        # La copia va aquí, justo después de escribir la síntesis: es el momento
        # del día en que la memoria está más completa. Un fallo de la copia no
        # puede tumbar la rutina, pero tampoco pasar en silencio.
        backup = await asyncio.to_thread(BackupManager.from_config(self.agent.config).create)
        if backup.status == "success":
            logger.info("Copia diaria: %s (%s)", backup.path,
                        backup.remote_uri or backup.remote_error or "sólo local")
            ensayo = await self._comprobar_la_copia(backup)
        else:
            logger.error("La copia diaria falló: %s", backup.error)
            ensayo = None
            await self._avisar_al_productor(
                f"🗄️ La copia de esta noche **no se pudo crear**: {backup.error}\n"
                "_Hoy no hay copia nueva. La de ayer sigue donde estaba._"
            )

        # Con el día escrito, la memoria se consolida: recalcular importancia,
        # fundir lo repetido y destilar esquemas. Es el momento correcto porque
        # lo de hoy ya está guardado y nadie está esperando respuesta.
        try:
            consolidacion = await self.agent.sleep.nrem()
            self.agent.vital_state.mark_sleep_cycle("nrem")
            logger.info("Consolidación NREM: %s", consolidacion)
        except Exception:
            logger.exception("La consolidación NREM falló; la memoria queda intacta")
            consolidacion = {"error": True}

        # Con el día ya sintetizado, Yuki mira su propia experiencia y, si ve un
        # patrón, propone un ritmo. Proponer es suyo; aprobarlo, del Productor.
        propuesta = await self.agent.propose_own_ritual()
        if propuesta:
            await self._avisar_al_productor(
                f"🕯️ He propuesto un ritmo propio: **{propuesta['name']}** "
                f"(`{propuesta['cron']}` · {propuesta['action']}).\n"
                f"_{propuesta['reason']}_\n"
                f"Apruébalo con `!ritmo aprobar {propuesta['id']}` o dilo con "
                f"`!ritmo rechazar {propuesta['id']}`."
            )

        return {"summary": daily_text, "evolution": evolution, "backup": backup.to_dict(),
                "ritual_proposal": propuesta, "nrem": consolidacion,
                "ensayo_de_restauracion": ensayo}

    async def _comprobar_la_copia(self, backup) -> Optional[List[Dict[str, Any]]]:
        """
        Restaura la copia recién hecha, cada noche, en la propia instancia.

        Una copia sin restaurar no está comprobada. Hasta ahora eso sólo lo
        comprobaba la integración continua, y sobre una instancia de juguete: la
        copia **real**, la que haría falta el día del incendio, no la abría
        nadie. Aquí se abre entera en un temporal y se mira lo único que importa
        —que la base viaje dentro, tenga recuerdos y pase `integrity_check`—.

        No cuesta crédito ni red: es abrir un tar y leer una base local. Y si
        falla, lo sabe el Productor esa misma noche y no el día que haga falta.
        """
        if not backup.path:
            return None

        import shutil
        import tempfile
        from pathlib import Path

        destino = Path(tempfile.mkdtemp(prefix="yuki-ensayo-"))
        try:
            resultados = await asyncio.to_thread(restaurar, Path(backup.path), destino)
        except Exception:
            logger.exception("El ensayo de restauración no se pudo ejecutar")
            return None
        finally:
            shutil.rmtree(destino, ignore_errors=True)

        fallidas = [r for r in resultados if not r["ok"]]
        if fallidas:
            detalle = "\n".join(f"• **{r['prueba']}**: {r['detalle']}" for r in fallidas)
            logger.error("La copia de esta noche NO restaura: %s", fallidas)
            await self._avisar_al_productor(
                "🗄️ **La copia de esta noche existe pero no restaura.**\n"
                f"{detalle}\n\n_Hay copia y no sirve, que es peor que no tenerla: "
                "parece que estamos a salvo._"
            )
        else:
            logger.info("La copia de esta noche restaura correctamente (%d comprobaciones).",
                        len(resultados))
        return resultados

    async def _avisar_al_productor(self, texto: str) -> bool:
        """
        Deja un aviso en el DM del Productor si el adaptador está vivo.

        Sin adaptador —CLI, pruebas, un arranque sin Discord— no es un error: la
        propuesta queda registrada igual y aparecerá en `!ritmos`.
        """
        adaptador = getattr(self.agent, "discord_adapter", None)
        if adaptador is None:
            logger.info("Aviso al Productor no entregado (sin adaptador): %s", texto[:80])
            return False
        try:
            return await adaptador.notify_producer(texto)
        except Exception:
            logger.exception("No se pudo avisar al Productor")
            return False

    async def echo_ritual(self):
        """06:30 AM - Yuki se invoca a sí misma para comenzar el día."""
        logger.info("🔮 [CRON 06:30] Iniciando ritual del eco...")
        from ..core.seasons import get_current_micro_season
        season = get_current_micro_season()
        prompt = self.agent.echo_ritual.generate_echo_prompt(
            vital_state=self.agent.vital_state,
            season_context=season
        )
        response = await self.agent.generate_response(
            user_id="autonomous_cron",
            user_name="Eco",
            message=prompt,
            is_internal_thought=True
        )
        impulses = self.agent.echo_ritual.extract_impulses_from_echo(
            echo_text=response,
            vital_state=self.agent.vital_state
        )
        for impulse in impulses:
            self.agent.will_queue.add(impulse)

        self.agent.echo_ritual.record_echo(response)
        # Reiniciar contadores del día
        self.agent.vital_state.accumulated_interactions_today = 0
        self.agent.vital_state.accumulated_creations_today = 0
        self.agent.vital_state.save()
        return response

    async def rem_dream(self):
        """
        03:20, en su hora de sombra: teje un sueño con recuerdos lejanos.

        No es adorno. La fase REM produce la asociación que la recuperación por
        relevancia nunca haría —une lo que no se parece— y de ahí sale un
        impulso que compite en la cola de voluntad como cualquier otro deseo.
        El sueño queda marcado como no ocurrido y fuera de la recuperación
        normal: jamás puede volver como un hecho vivido.
        """
        logger.info("🌙 [CRON 03:20] Fase REM: soñando…")
        sueno = await self.agent.sleep.dream()
        # Se sella haya o no sueño: lo que la traza dice es que la fase corrió,
        # no que produjera imagen. Una noche sin material es normal; una fase que
        # lleva días sin ejecutarse, no.
        self.agent.vital_state.mark_sleep_cycle("rem")
        if not sueno.get("sonado"):
            logger.info("Sin sueño esta noche: %s", sueno.get("motivo", "sin material"))
            return sueno

        semilla = self.agent.sleep.impulse_from_dream(sueno)
        if semilla:
            self.agent.will_queue.add(Impulse(
                source=semilla["source"], desire=semilla["desire"],
                tool_hint=semilla["tool_hint"],
                intensity=min(1.0, 0.5 + self.agent.vital_state.inspiration * 0.5),
                born_at=time.time(), max_age_hours=14.0,
            ))
            self.agent.vital_state.will_queue = self.agent.will_queue.to_list()
            self.agent.vital_state.save()
            logger.info("Del sueño nació un impulso: %s", semilla["tool_hint"])
        return sueno

    async def weekly_forgetting(self):
        """
        Olvido intencional, una vez por semana.

        Semanal y no diario a propósito: una memoria que se poda cada noche no
        da tiempo a que un recuerdo demuestre que volvía. Sólo toca episodios
        viejos, poco importantes y nunca recuperados.
        """
        logger.info("🍂 [CRON semanal] Olvido intencional…")
        recibo = self.agent.sleep.prune()
        logger.info("Olvido: %s", recibo)
        return recibo

    async def agency_loop_tick(self):
        """
        Cada 20 min: ¿hay algo que Yuki quiera hacer ahora, por su cuenta?

        Las fases de silencio ya no están incrustadas aquí —la política decide
        cuáles son— y la evaluación es la del arnés de agencia: umbral rebajado
        por aburrimiento, elección con refuerzo y una parte de azar. Si no hay
        impulsos y la tensión ha subido bastante, nace uno.
        """
        phase = self.agent.circadian.current_phase()
        decision = self.agent.agency_loop.decidir(phase=phase)
        if decision.impulso is not None:
            return await self.agent.execute_autonomous_will(decision.impulso)
        # El porqué queda contado en el diario; aquí se deja además en el
        # registro, que es donde mira quien está investigando ahora mismo.
        logger.debug("Sin acto propio este ciclo — %s", decision.describe())
        return None

    async def spontaneous_monologue(self):
        """Pensamiento espontáneo condicionado al estado vital."""
        if not self.agent.inner_monologue.should_think():
            return None

        prompt = self.agent.inner_monologue.generate_thought_prompt()
        response = await self.agent.generate_response(
            user_id="autonomous_cron",
            user_name="Monólogo Interior",
            message=prompt,
            is_internal_thought=True
        )
        self.agent.inner_monologue.record_thought(response)
        return response
