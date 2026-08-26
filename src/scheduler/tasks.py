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
        logger.info("🌅 [CRON 07:30] Creando lanzamiento matutino de arte...")
        
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
        image_result = await self.agent.nous_portal.generate_image_fal(prompt=visual_concept)
        voice_result = await self.agent.nous_portal.synthesize_voice_tts(text=morning_text)

        logger.info(f"🎨 Arte matutino generado: {image_result['image_url']}")
        logger.info(f"🎙️ Voz matutina generada: {voice_result['audio_url']}")

        # Difundir a adaptadores activos (si están configurados)
        if hasattr(self.agent, "telegram_adapter") and self.agent.telegram_adapter:
            await self.agent.telegram_adapter.broadcast_drop(
                text=morning_text,
                image_path=image_result["local_path"],
                audio_path=voice_result["local_path"]
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
        
        synthesis_prompt = (
            "El día concluye. Revisa en tu interior los encuentros, palabras y silencios de hoy. "
            "Escribe un párrafo contemplativo en primera persona (máximo 400 caracteres) sintetizando "
            "cómo fluyó el agua de la jornada."
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
