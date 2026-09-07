import asyncio
import json
from types import SimpleNamespace

import pytest

from src.tools.creation_library import CreationLibrary
from src.core.producer_harness import ProducerHarness


def test_library_import_preserves_original_and_is_idempotent(tmp_path):
    music = tmp_path / "music"
    music.mkdir()
    original = music / "piece.mid"
    original.write_bytes(b"MThd\x00\x00\x00\x06")
    (music / "fake.mp3").write_bytes(b"YUKI MOCK AUDIO")
    lib = CreationLibrary(tmp_path)
    assert lib.inventory()["total"] == 1
    assert lib.inventory()["total"] == 1
    item = lib.list_entries()["entries"][0]
    assert item["state"] == "en-desarrollo"
    assert (lib.root / item["path"]).read_bytes() == original.read_bytes()
    lib.set_status(item["id"], "terminado")
    assert original.exists()
    assert lib.list_entries()["entries"][0]["state"] == "terminado"
    assert "sonora" in (lib.root / "INDEX.md").read_text()


def test_library_rejects_escape_and_omits_external_symlinks(tmp_path):
    output = tmp_path / "output"
    (output / "art").mkdir(parents=True)
    secret = tmp_path / "outside.png"
    secret.write_bytes(b"outside")
    (output / "art" / "linked.png").symlink_to(secret)
    lib = CreationLibrary(output)
    assert lib.inventory()["total"] == 0
    with pytest.raises(ValueError):
        lib._path("../../outside.png")
    with pytest.raises(ValueError):
        lib.save_text("title", "body", "../../escape")


def test_text_versions_and_corruption_are_not_silently_overwritten(tmp_path):
    lib = CreationLibrary(tmp_path)
    first = lib.save_text("Poema", "texto original")
    second = lib.save_text("Poema", "texto nuevo")
    assert first["id"] != second["id"]
    assert lib.read_entry(first["id"])["content"] == "texto original"
    (lib.root / first["path"]).write_text("corrupto")
    with pytest.raises(ValueError):
        lib.save_text("Poema", "texto original")


def call(name, arguments=None):
    return {"id": "call-1", "type": "function", "function": {
        "name": name, "arguments": json.dumps(arguments or {})}}


def agent_for(tmp_path, turns, allowed=True):
    class Router:
        def generate_with_tools(self, messages, tools):
            if len(messages) > 2:
                assert messages[-1]["tool_call_id"] == "call-1"
            return turns.pop(0)
    armor = SimpleNamespace(sanitize_user_prompt=lambda text: SimpleNamespace(allowed=allowed, text=text))
    return SimpleNamespace(creation_library=CreationLibrary(tmp_path), llm_router=Router(), model_armor=armor)


def test_harness_executes_then_returns_receipt(tmp_path):
    turns = [{"role": "assistant", "content": "", "tool_calls": [call("library_save_text", {"title": "Poema", "content": "agua y acero"})]},
             {"role": "assistant", "content": "Guardado."}]
    agent = agent_for(tmp_path, turns)
    answer = asyncio.run(ProducerHarness(agent).run("Yuki", "Guarda el poema"))
    assert "✓ library_save_text" in answer
    assert agent.creation_library.list_entries()["total"] == 1


@pytest.mark.parametrize("tool,allowed", [("shell", True), ("library_inventory", False)])
def test_harness_denies_unknown_tools_and_rejected_arguments(tmp_path, tool, allowed):
    turns = [{"role": "assistant", "content": "", "tool_calls": [call(tool)]},
             {"role": "assistant", "content": "No ejecutado."}]
    agent = agent_for(tmp_path, turns, allowed)
    answer = asyncio.run(ProducerHarness(agent).run("Yuki", "petición"))
    assert "✗" in answer
    assert not agent.creation_library.root.exists()


def test_harness_reports_limit_and_no_background_work(tmp_path):
    turns = [{"role": "assistant", "content": "", "tool_calls": [call("library_list")]} for _ in range(6)]
    answer = asyncio.run(ProducerHarness(agent_for(tmp_path, turns)).run("Yuki", "lista"))
    assert "límite de pasos" in answer
    assert "ninguna tarea ejecutándose" in answer


def test_dm_requires_pairing_even_on_direct_method_call(tmp_path):
    pytest.importorskip("discord")
    from src.adapters.discord_bot import DiscordAdapter
    adapter = DiscordAdapter(SimpleNamespace())
    adapter.pairing_path = tmp_path / "absent.json"
    answer = asyncio.run(adapter.handle_producer_dm("235796491988369408", "Producer", "organiza biblioteca"))
    assert "requiere" in answer


def test_router_transmits_native_tools_and_preserves_call_ids():
    from src.core.llm_router import LLMRouter, OpenRouterProvider
    captured = {}
    tool = call("library_list")
    class Client:
        def __init__(self):
            self.chat = SimpleNamespace(completions=self)
        def with_options(self, **kwargs):
            return self
        def create(self, **kwargs):
            captured.update(kwargs)
            message = SimpleNamespace(content=None, tool_calls=[SimpleNamespace(model_dump=lambda **kw: tool)])
            return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="tool_calls")])
    provider = OpenRouterProvider(api_key="test-fixture")
    provider._client = lambda: Client()
    messages = [{"role": "user", "content": "Lista las obras"}]
    result = LLMRouter(providers=[provider]).generate_with_tools(messages, [{"type": "function"}])
    assert captured["messages"] == messages
    assert captured["tools"] == [{"type": "function"}]
    assert result["tool_calls"][0]["id"] == "call-1"
