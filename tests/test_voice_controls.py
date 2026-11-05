import threading

from src.altair.core import voice as voice_module


def test_piper_stop_cancels_speech_and_stops_playback(monkeypatch):
    voice = voice_module.PiperVoice.__new__(voice_module.PiperVoice)
    voice._stop_event = threading.Event()
    stopped = []
    monkeypatch.setattr(voice_module.pygame.mixer.music, "stop", lambda: stopped.append(True))

    voice.stop()

    assert voice._stop_event.is_set()
    assert stopped == [True]


def test_elevenlabs_stop_cancels_speech_and_stops_fallback(monkeypatch):
    voice = voice_module.ElevenLabsVoice.__new__(voice_module.ElevenLabsVoice)
    voice._stop_event = threading.Event()
    voice.fallback_voice = None
    stopped = []
    monkeypatch.setattr(voice_module.pygame.mixer.music, "stop", lambda: stopped.append(True))

    voice.stop()

    assert voice._stop_event.is_set()
    assert stopped == [True]