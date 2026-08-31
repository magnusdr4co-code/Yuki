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
from ..scheduler.cron_engine import CronEngine, CronParseError
from ..scheduler.tasks import AutonomousTasks
from .prompt_builder import PromptBuilder
from .vital_state import VitalState
from .circadian import CircadianClock
from .spark import WillQueue, EchoRitual, AgencyLoop
from .inner_monologue import InnerMonologue
from .growth_journal import GrowthJournal
from .presence_controller import PresenceController
from .llm_router import LLMRouter

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
        
        # 6. Kokoro Engine (Motor de Vida Interior)
        self.vital_state = VitalState(state_path="data/vital_state.json")
        self.circadian = CircadianClock(tz_name=tz)

        # 7. La Chispa (The Spark)
        self.will_queue = WillQueue()
        if self.vital_state.will_queue:
            self.will_queue = WillQueue.from_list(self.vital_state.will_queue)
        self.growth_journal = GrowthJournal(memory_engine=self.memory_manager.engine)
        self.echo_ritual = EchoRitual(
            memory_manager=self.memory_manager,
            growth_journal=self.growth_journal
        )
        self.agency_loop = AgencyLoop(
            will_queue=self.will_queue,
            vital_state_ref=self.vital_state
        )
        self.inner_monologue = InnerMonologue(
            memory_manager=self.memory_manager,
            vital_state=self.vital_state
        )
        self.presence_controller = PresenceController(
            vital_state=self.vital_state,
            circadian_clock=self.circadian
        )

        # Cadena de pasarelas de lenguaje: Nous Portal → OpenRouter → voz local
        self.llm_router = LLMRouter(config=self.config)

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
                "synthesize_daily_memory": self.tasks.daily_memory_synthesis,
                "echo_ritual": self.tasks.echo_ritual,
                "agency_loop_tick": self.tasks.agency_loop_tick,
                "spontaneous_monologue": self.tasks.spontaneous_monologue
            }

            if action not in func_map:
                logger.warning(f"Acción cron desconocida '{action}' en la tarea '{name}'; se omite.")
                continue

            try:
                self.cron.register_job(name, cron_expr, func_map[action], enabled=enabled)
            except CronParseError as e:
                # Una expresión mal escrita no debe impedir que Yuki despierte:
                # se omite esa tarea y el resto sigue vivo.
                logger.error(f"Expresión cron inválida en la tarea '{name}': {e}")

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
        
        if hasattr(self, 'presence_controller'):
            if not self.presence_controller.should_respond(channel_type):
                return 'NADA_QUE_DECIR'

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
            active_role=active_role,
            vital_state_block=self.vital_state.to_natural_language(),
            echo_impulse=self.echo_ritual.last_echo,
            evolution_context=self.growth_journal.get_evolution_context()
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
            self.vital_state.apply_stimulus('positive_interaction', 0.3)
            
        phase = self.circadian.current_phase()
        self.vital_state.update_tick(phase, 0)
        self.vital_state.will_queue = self.will_queue.to_list()
        self.vital_state.save()

        return response_text

    def _call_llm_inference(self, system_prompt: str, user_message: str) -> str:
        """
        Invocación a la cadena de pasarelas declarada en la arquitectura:
        Nous Portal primero, OpenRouter como agregador, y la voz local de Yuki
        como último recurso cuando no hay red ni claves configuradas.
        """
        response = self.llm_router.generate(system_prompt, user_message)

        if response.simulated:
            logger.info(f"Respuesta simulada por la pasarela '{response.provider}' (sin generación real).")
        else:
            logger.info(f"Respuesta generada por '{response.provider}' con el modelo '{response.model}'.")

        return response.text
        
    async def execute_autonomous_will(self, impulse) -> Dict[str, Any]:
        """Ejecuta un impulso de la Cola de Voluntad por iniciativa propia."""
        logger.info(f"🔥 [CHISPA] Ejecutando voluntad autónoma: {impulse.desire}")
        result = await self.media_creator.create_from_impulse(impulse, self.vital_state)
        self.agency_loop.record_action(impulse, result)
        # Persist updated state
        self.vital_state.will_queue = self.will_queue.to_list()
        self.vital_state.save()
        return result
