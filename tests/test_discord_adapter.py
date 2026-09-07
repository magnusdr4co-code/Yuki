import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.adapters.discord_intents import (
    channel_slug,
    extract_production_target,
    looks_like_discord_production_request,
    looks_like_media_delivery_request,
)
from src.adapters.discord_text import split_discord_text


def test_production_request_is_detected_only_for_explicit_channel_request():
    request = (
        'Crea un canal nuevo en el servidor "Dev Server", llamado "Salón". '
        "Dispon una presentación."
    )
    assert looks_like_discord_production_request(request)
    assert not looks_like_discord_production_request("Escribe un poema sobre el salón.")


def test_media_delivery_request_requires_creation_media_and_delivery():
    assert looks_like_media_delivery_request("Crea la canción y el vídeo, y pásamelos por aquí.")
    assert looks_like_media_delivery_request("Genera un mp3 y adjúntalo aquí")
    assert not looks_like_media_delivery_request("El vídeo anterior duró tres segundos.")


def test_production_target_and_channel_slug_are_stable():
    guild, channel = extract_production_target(
        'Crea un canal nuevo en el servidor "Dev Server", llamado "Salón".'
    )
    assert guild == "Dev Server"
    assert channel == "Salón"
    assert channel_slug(channel) == "salon"


def test_permission_gate_reports_manage_channels_and_attachments():
    pytest.importorskip("discord")
    from src.adapters.discord_bot import DiscordAdapter

    class Permissions:
        manage_channels = True
        send_messages = True
        attach_files = False

    class Member:
        guild_permissions = Permissions()

    class Guild:
        me = Member()

    assert DiscordAdapter._permission_names(Guild()) == {
        "manage_channels",
        "send_messages",
    }


def test_long_discord_text_is_split_without_loss():
    original = " ".join(f"token-{index}" for index in range(1000))
    chunks = split_discord_text(original, limit=1900)

    assert len(chunks) > 1
    assert all(len(chunk) <= 1900 for chunk in chunks)
    assert " ".join(chunks) == original
