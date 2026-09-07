"""Autoajuste deliberado: sólo temperatura, sólo desde crecimiento ya registrado."""
from __future__ import annotations

import asyncio
import json
import logging

logger = logging.getLogger("Yuki.EvolutionHarness")

TEMPERATURE_TOOL = {
    "type": "function",
    "function": {
        "name": "adjust_runtime_temperature",
        "description": "Ajusta con prudencia la temperatura de generación tras crecimiento verificable.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "enum": ["agent.model.temperature", "vertex_ai.temperature"]},
                "value": {"type": "number", "minimum": 0.0, "maximum": 2.0},
                "reason": {"type": "string", "maxLength": 240},
            },
            "required": ["path", "value", "reason"],
            "additionalProperties": False,
        },
    },
}


class EvolutionHarness:
    """No concede a la evolución terminal, código, permisos ni cambios de modelo."""
    def __init__(self, agent):
        self.agent = agent

    async def _record_growth_review(self, min_confidence):
        """Convierte sólo hallazgos estructurados y suficientemente seguros en evidencia."""
        prompt = self.agent.growth_journal.generate_review_prompt()
        decision = await asyncio.to_thread(self.agent.model_armor.sanitize_user_prompt, prompt)
        if not decision.allowed:
            return 0
        response = await asyncio.to_thread(
            self.agent._call_llm_inference,
            "Analiza crecimiento con el formato pedido. No ejecutes acciones ni propongas cambios de sistema.",
            decision.text,
        )
        safe_response = await asyncio.to_thread(
            self.agent.model_armor.sanitize_model_response, response, user_prompt=decision.text
        )
        if not safe_response.allowed:
            return 0
        existing = {
            (event["domain"], event["from_position"], event["to_position"])
            for event in self.agent.growth_journal.engine.get_recent_growth(limit=50)
        }
        recorded = 0
        for event in self.agent.growth_journal.parse_llm_growth_response(safe_response.text):
            identity = (event["domain"], event["from_position"], event["to_position"])
            if (event["domain"] not in {"music", "aesthetics", "philosophy", "relationships"}
                    or event["confidence"] < min_confidence or identity in existing):
                continue
            self.agent.growth_journal.record_growth_event(
                event["domain"], event["from_position"], event["to_position"], [], event["confidence"]
            )
            existing.add(identity)
            recorded += 1
        return recorded

    async def review_and_adjust(self):
        cfg = self.agent.config.get("runtime_harness", {}).get("self_evolution", {})
        if not cfg.get("enabled", True):
            return {"changed": False, "reason": "disabled"}
        min_confidence = float(cfg.get("min_confidence", 0.80))
        min_interactions = int(cfg.get("min_interactions", 5))
        if self.agent.vital_state.accumulated_interactions_today < min_interactions:
            return {"changed": False, "reason": "insufficient_interactions"}

        recorded = await self._record_growth_review(min_confidence)
        events = [event for event in self.agent.growth_journal.engine.get_recent_growth(limit=3)
                  if float(event.get("confidence", 0)) >= min_confidence]
        if not events:
            return {"changed": False, "reason": "no_verified_growth", "recorded_events": recorded}

        evidence = "\n".join(
            f"- {event['domain']}: {event['from_position']} → {event['to_position']} "
            f"(confianza {event['confidence']})" for event in events
        )[:5000]
        prompt = (
            "Evalúa si los cambios de crecimiento verificados justifican ajustar la creatividad. "
            "Sólo puedes ajustar UNA temperatura y sólo una variación máxima de 0.15 respecto al valor actual. "
            "No cambies nada si la evidencia no es concluyente. No expliques acciones que no hayas llamado.\n"
            f"Crecimiento verificado:\n{evidence}\n"
            f"Valores actuales: {json.dumps(self.agent.runtime_config_get()['values'], ensure_ascii=False)}"
        )
        decision = await asyncio.to_thread(self.agent.model_armor.sanitize_user_prompt, prompt)
        if not decision.allowed:
            return {"changed": False, "reason": "armor_rejected_review"}
        turn = await asyncio.to_thread(
            self.agent.llm_router.generate_with_tools,
            [{"role": "system", "content": "Eres el módulo de evolución prudente de Yuki."},
             {"role": "user", "content": decision.text}],
            [TEMPERATURE_TOOL],
        )
        calls = turn.get("tool_calls", [])
        if len(calls) != 1 or calls[0].get("function", {}).get("name") != "adjust_runtime_temperature":
            return {"changed": False, "reason": "no_safe_adjustment", "recorded_events": recorded}
        try:
            arguments = json.loads(calls[0]["function"]["arguments"])
            args_decision = await asyncio.to_thread(
                self.agent.model_armor.sanitize_user_prompt, json.dumps(arguments, ensure_ascii=False)
            )
            if not args_decision.allowed:
                return {"changed": False, "reason": "armor_rejected_arguments", "recorded_events": recorded}
            current = float(self.agent.runtime_config_get()["values"][arguments["path"]])
            maximum_delta = float(cfg.get("max_temperature_delta", 0.15))
            if abs(float(arguments["value"]) - current) > maximum_delta:
                return {"changed": False, "reason": "delta_exceeds_limit", "recorded_events": recorded}
            result = await asyncio.to_thread(
                self.agent.reconfigure_runtime, arguments["path"], arguments["value"],
                actor="evolution", reason=arguments["reason"],
            )
            logger.info("Autoajuste evolutivo aplicado a %s", arguments["path"])
            return {"changed": True, "result": result, "recorded_events": recorded}
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            logger.warning("Autoajuste evolutivo rechazado por validación")
            return {"changed": False, "reason": "invalid_adjustment", "recorded_events": recorded}
