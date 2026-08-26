"""
Despliegue Serverless en Modal para Yuki.
Permite ejecutar a la Diva Digital sin costes fijos de servidor (Zero Idle Cost).
Despierta instantáneamente ante webhooks de Telegram o Discord.
"""

import os

# Configuración condicional para ejecución local o en entorno Modal
try:
    import modal
    app = modal.App("yuki-digital-diva")
    
    # Imagen de ejecución optimizada con dependencias
    image = (
        modal.Image.debian_slim(python_version="3.11")
        .apt_install("sqlite3", "ffmpeg")
        .pip_install(
            "pydantic",
            "pyyaml",
            "anthropic",
            "openai",
            "aiohttp",
            "sqlite-utils",
            "APScheduler"
        )
    )

    # Volumen persistente para almacenar SQLite FTS5 de memoria y caché de medios
    volume = modal.Volume.from_name("yuki-memory-storage", create_if_missing=True)

    @app.function(
        image=image,
        volumes={"/data": volume},
        secrets=[modal.Secret.from_dotenv()],
        keep_warm=0, # Apaga completamente cuando no hay peticiones
        timeout=60
    )
    @modal.web_endpoint(method="POST")
    async def telegram_webhook(payload: dict):
        """Punto de entrada serverless para webhooks de Telegram."""
        from ..core.agent import YukiAgent
        
        agent = YukiAgent()
        message = payload.get("message", {})
        text = message.get("text", "")
        from_user = message.get("from", {})
        user_id = str(from_user.get("id", "guest"))
        user_name = from_user.get("first_name", "Visitante")

        response = await agent.generate_response(
            user_id=user_id,
            user_name=user_name,
            message=text,
            channel_type="telegram_webhook"
        )
        
        return {"status": "ok", "reply": response}

    @app.function(
        image=image,
        volumes={"/data": volume},
        secrets=[modal.Secret.from_dotenv()],
        schedule=modal.Cron("0 3 * * *") # 03:00 AM Cron
    )
    async def modal_cron_night():
        """Ejecuta la tarea autónoma nocturna en la nube sin servidor dedicado."""
        from ..core.agent import YukiAgent
        agent = YukiAgent()
        await agent.tasks.nocturnal_trend_reflection()

except ImportError:
    # Modal no instalado localmente; stub informativo
    pass
