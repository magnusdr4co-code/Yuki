"""Recuperación explícita de obras existentes; no publica mensajes ni genera medios."""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.tools.creation_library import CreationLibrary
from src.adapters.discord_intents import channel_slug


async def recover_discord(library):
    import discord
    allowed = {item.strip() for item in os.getenv("DISCORD_ALLOWED_GUILD_ID", "").split(",") if item.strip()}
    count = 0
    async with discord.Client(intents=discord.Intents.none()) as client:
        await client.login(os.environ["DISCORD_BOT_TOKEN"])
        for guild_id in sorted(allowed):
            guild = await client.fetch_guild(int(guild_id))
            if guild.name != "Dev Server":
                continue
            for channel in await guild.fetch_channels():
                if not isinstance(channel, discord.TextChannel) or channel_slug(channel.name) != "salon":
                    continue
                async for message in channel.history(limit=300, oldest_first=True):
                    if message.author.id != client.user.id or not message.content:
                        continue
                    if message.attachments or message.content.startswith(("⚠", "✅", "⏭", "❌", "🔒", "⛩")):
                        continue  # Adjuntos ya inventariados; avisos no son obras.
                    # Testimonio exacto, no una reconstrucción inventada del poema.
                    library.save_text(
                        f"Salón: mensaje de Yuki {message.id}", message.content,
                        source=f"discord:{guild_id}/{channel.id}/{message.id}",
                    )
                    count += 1
    return count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--recover-discord", action="store_true")
    args = parser.parse_args()
    library = CreationLibrary()
    result = library.inventory()
    if args.recover_discord:
        result["recovered_discord_texts"] = asyncio.run(recover_discord(library))
        result["total"] = library.list_entries()["total"]
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
