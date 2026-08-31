"""
Definición de Tareas Autónomas para Yuki.
Ejecuta rutinas creativas sin supervisión humana continua:
1. 03:00 AM - Reflexión nocturna y examen de corrientes (Sombra de Yuki).
2. 07:30 AM - Publicación matutina de arte lírico y visual en canales sociales.
3. 23:30 PM - Síntesis y destilación de la memoria del día.
"""

import logging
from datetime import datetime
from typing import Optional

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
        
        prompt = (
            "Es la madrugada (03:00). Estás despierta en el silencio de tu salón. "
            "Has observado estas corrientes en el mundo: " + str(trends) + ". "
            "Destila una breve reflexión poética de 2 frases sobre el contraste entre la velocidad del mundo "
            "y la permanencia de las artes tradicionales."
        )
        
        reflection = await self.agent.generate_response(
            user_id="autonomous_cron",
            user_name="Noche",
            message=prompt,
            is_internal_thought=True
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
            is_internal_thought=True
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
            is_internal_thought=True
        )

        self.agent.memory_manager.save_daily_synthesis(
            date_str=date_str,
            summary_text=daily_text
        )
        logger.info(f"Memoria del día guardada ({date_str}): {daily_text}")
        return daily_text

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

    async def agency_loop_tick(self):
        """Cada 15-30 min - Evalúa impulsos y decide actuar."""
        phase = self.agent.circadian.current_phase()
        if phase in ['kage']:
            return None
            
        action_decision = self.agent.agency_loop.evaluate()
        if action_decision:
            return await self.agent.execute_autonomous_will(action_decision)
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
