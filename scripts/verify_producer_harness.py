"""Sonda real del DM sin publicar: usa el pairing existente y archiva sólo obras existentes."""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.core.agent import YukiAgent
from src.adapters.discord_bot import DiscordAdapter, DEFAULT_PAIRED_PRODUCER_ID


async def main():
    logging.basicConfig(level=logging.INFO)
    agent = YukiAgent()
    adapter = DiscordAdapter(agent)
    denied = await adapter.handle_producer_dm("unauthorized-probe", "Probe", "crea biblioteca")
    assert "requiere" in denied
    assert adapter._is_paired(DEFAULT_PAIRED_PRODUCER_ID), "El productor no está emparejado"
    result = await adapter.handle_producer_dm(
        DEFAULT_PAIRED_PRODUCER_ID, "Productor",
        "Organiza ya la Biblioteca por tipo y estado: ejecuta library_inventory para archivar "
        "las piezas existentes. Conserva los originales y no inventes piezas ni marques terminado. "
        "Confirma con el total real y la ruta del índice.",
    )
    assert "✓ library_inventory" in result, "El modelo no ejecutó el inventario"
    total = agent.creation_library.list_entries()["total"]
    assert total > 0, "Inventario vacío"
    print(f"LIVE_DM_TOOL_LOOP_OK total={total}")
    print(result.split("**Registro de ejecución:**")[-1])
    await adapter.close()


if __name__ == "__main__":
    asyncio.run(main())
