import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.adapters.discord_intents import (
    channel_slug,
    extract_production_target,
    looks_like_discord_production_request,
)


def test_production_request_is_detected_only_for_explicit_channel_request():
    request = (
        'Crea un canal nuevo en el servidor "Dev Server", llamado "Salón". '
        "Dispon una presentación."
    )
    assert looks_like_discord_production_request(request)
    assert not looks_like_discord_production_request("Escribe un poema sobre el salón.")


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
