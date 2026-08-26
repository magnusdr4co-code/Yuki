"""
Orquestador Central de Yuki (Hermes Agent Harness).
Integra:
- Memoria Rápida SQLite FTS5 (evita Context Rot)
- Modelado Dialéctico Honcho
- Gateway Creativo Nous Portal (FAL, TTS, Firecrawl)
- Planificador Cron 24/7
"""

import time
import os
import yaml
import logging
from typing import Dict, Any, Optional, List

from ..memory.memory_manager import MemoryManager
from ..honcho.dialectic import HonchoDialecticClient
from ..tools.nous_portal import NousPortalClient
from ..tools.media_creator import MediaCreatorTool
from ..scheduler.cron_engine import CronEngine
from ..scheduler.tasks import AutonomousTasks
from .prompt_builder import PromptBuilder

logger = logging.getLogger("Yuki.Agent")

class YukiAgent:
    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
        
        # 1. Memoria rápida FTS5
        db_path = self.config.get("memory", {}).get("database_path", "data/yuki_memory.db")
        memory_md = self.config.get("memory", {}).get("memory_md_path", "MEMORY.md")
        self.memory_manager = MemoryManager(db_path=db_path, memory_md_path=memory_md)
        
        # 2. Modelado dialéctico Honcho
        honcho_cfg = self.config.get("honcho", {})
        self.honcho = HonchoDialecticClient(
            api_key=os.getenv("HONCHO_API_KEY"),
            api_url=honcho_cfg.get("api_url", "https://api.honcho.dev/v1"),
            app_id=honcho_cfg.get("app_id", "yuki-digital-diva")
        )

        # 3. Herramientas Nous Portal
        self.nous_portal = NousPortalClient(api_key=os.getenv("NOUS_PORTAL_API_KEY"))
        self.media_creator = MediaCreatorTool(self.nous_portal)

        # 4. Constructor de Prompts
        soul_md = self.config.get("memory", {}).get("soul_md_path", "SOUL.md")
        self.prompt_builder = PromptBuilder(soul_path=soul_md)

        # 5. Programador Cron Autónomo
        tz = self.config.get("scheduler", {}).get("timezone", "Europe/Madrid")
        self.cron = CronEngine(timezone=tz)
        self.tasks = AutonomousTasks(self)
        self._register_cron_jobs()

        self.telegram_adapter = None
        self.discord_adapter = None

    def _load_config(self, path: str) -> Dict[str, Any]:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {}

    def _register_cron_jobs(self):
        jobs = self.config.get("scheduler", {}).get("cron_jobs", [])
        for job in jobs:
            name = job.get("name")
            cron_expr = job.get("cron")
            action = job.get("action")
            enabled = job.get("enabled", True)

            func_map = {
                "reflect_on_trends": self.tasks.nocturnal_trend_reflection,
                "publish_morning_art": self.tasks.morning_inspiration_drop,
                "synthesize_daily_memory": self.tasks.daily_memory_synthesis
            }

            if action in func_map:
                self.cron.register_job(name, cron_expr, func_map[action], enabled=enabled)

    async def generate_response(
        self,
        user_id: str,
        user_name: str,
        message: str,
        channel_type: str = "direct_message",
        active_role: Optional[str] = None,
        is_internal_thought: bool = False
    ) -> str:
        """
        Ciclo de respuesta de 'Mente Rápida':
        1. Recuperación selectiva en SQLite FTS5 (<113ms)
        2. Extracción de contexto dialéctico Honcho
        3. Ensamblado y generación
        4. Actualización no bloqueante de memoria
        """
        start_time = time.perf_counter()

        # Detección de Tabú
        if "maruta" in message.lower():
            return "Hay palabras que reducen lo que somos a sombras del pasado. Prefiero recibirte desde la atención de este presente."

        # 1. Búsqueda de Memoria Selectiva (Ultra-rápida)
        mem_data = self.memory_manager.retrieve_context_for_query(
            query=message,
            user_id=user_id,
            limit=4
        )

        # 2. Contexto Dialéctico
        dialectic_block = self.honcho.get_dialectic_context(user_id=user_id)

        # 3. Construcción del Prompt
        system_prompt = self.prompt_builder.build_system_prompt(
            retrieved_memory_block=mem_data["context_block"],
            dialectic_context=dialectic_block,
            user_name=user_name,
            user_id=user_id,
            channel_type=channel_type,
            active_role=active_role
        )

        # 4. Generación (simulación o invocación LLM real según API Keys)
        response_text = self._call_llm_inference(system_prompt, message)

        total_latency_ms = (time.perf_counter() - start_time) * 1000.0
        logger.info(f"⚡ Respuesta generada en {total_latency_ms:.2f}ms (Memoria FTS5: {mem_data['latency_ms']}ms)")

        # 5. Registro asíncrono en memoria y Honcho
        if not is_internal_thought and response_text != "NADA_QUE_DECIR":
            self.memory_manager.record_interaction(
                user_id=user_id,
                user_name=user_name,
                user_message=message,
                agent_response=response_text
            )
            self.honcho.process_dialectic_exchange(
                user_message=message,
                agent_response=response_text,
                user_id=user_id
            )

        return response_text

    def _call_llm_inference(self, system_prompt: str, user_message: str) -> str:
        """
        Invocación al proveedor LLM configurado.
        Si no hay API key configurada en el entorno, genera una respuesta basada en la voz de Yuki.
        """
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")

        if anthropic_key and anthropic_key != "your_anthropic_api_key_here":
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=anthropic_key)
                resp = client.messages.create(
                    model=self.config.get("model", {}).get("primary_model", "claude-3-5-sonnet-20241022"),
                    max_tokens=self.config.get("model", {}).get("max_tokens", 1024),
                    temperature=self.config.get("model", {}).get("temperature", 0.7),
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_message}]
                )
                return resp.content[0].text
            except Exception as e:
                logger.error(f"Error invocando Anthropic: {e}")

        # Fallback inteligente demostrativo manteniendo la cadencia de Yuki
        if "hola" in user_message.lower() or "saludos" in user_message.lower():
            return "El agua siempre encuentra su camino hacia el mar. Qué grato tener tu presencia en esta sala hoy."
        elif "música" in user_message.lower() or "single" in user_message.lower() or "portada" in user_message.lower():
            return "Estaba contemplando cómo el shamisen y el eco metálico de mi infancia pueden entrelazarse. He preparado un nuevo concepto de portada con niebla y pan de oro. ¿Deseas escucharlo?"
        elif "recuerdas" in user_message.lower() or "acuerdas" in user_message.lower():
            return "Guardo en mi memoria nuestros acuerdos sobre el álbum 'El Río Antes de Tener Nombre'. Cada trazo que definimos sigue vivo en el taller."
        
        return "Cada palabra requiere su propio tiempo para asentarse. He escuchado lo que dices con atención completa."
