import sys
import os
import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.tools.media_creator import MediaCreatorTool

@pytest.fixture
def media_tool():
    return MediaCreatorTool(portal_client=MagicMock())

def test_mood_to_image_params_low(media_tool):
    state = MagicMock(mood=0.2)
    params = media_tool._mood_to_image_params(state)
    assert params["lighting"] == "industrial_rain"

def test_mood_to_image_params_high(media_tool):
    state = MagicMock(mood=0.8)
    params = media_tool._mood_to_image_params(state)
    assert params["lighting"] == "komorebi"

def test_mood_to_image_params_mid(media_tool):
    state = MagicMock(mood=0.5)
    params = media_tool._mood_to_image_params(state)
    assert params["lighting"] == "urushi"

def test_mood_to_music_params_low(media_tool):
    state = MagicMock(mood=0.2)
    params = media_tool._mood_to_music_params(state)
    assert params["bpm"] == 72
    assert params["scale"] == "Insen"

def test_mood_to_music_params_high(media_tool):
    state = MagicMock(mood=0.8)
    params = media_tool._mood_to_music_params(state)
    assert params["bpm"] == 90
    assert params["scale"] == "Yo"

def test_mood_to_voice_params_low(media_tool):
    state = MagicMock(mood=0.2)
    params = media_tool._mood_to_voice_params(state)
    assert params["rate"] == "85%"

def test_mood_to_voice_params_high(media_tool):
    state = MagicMock(mood=0.8)
    params = media_tool._mood_to_voice_params(state)
    assert params["rate"] == "96%"
