import os

from src.altair.core import audio_core


def test_extract_remote_stt_text_supports_openai_payload():
    payload = {"text": "Bom dia, Altair."}
    assert audio_core._extract_remote_stt_text(payload) == "Bom dia, Altair."


def test_extract_remote_stt_text_supports_huggingface_payload():
    payload = {"generated_text": "fala capturada"}
    assert audio_core._extract_remote_stt_text(payload) == "fala capturada"


def test_desenha_config_de_stt_remoto_para_openai_compat():
    cfg = audio_core._get_remote_stt_config()
    assert isinstance(cfg["url"], str)
    assert isinstance(cfg["model"], str)
    assert cfg["headers"]["Accept"] == "application/json"


def test_desenha_config_de_stt_remoto_para_elevenlabs_usando_mesma_chave():
    os.environ["ELEVENLABS_API_KEY"] = "abc123"
    os.environ.pop("ALTAIR_STT_REMOTE_API_KEY", None)
    os.environ.pop("ALTAIR_STT_REMOTE_URL", None)
    try:
        cfg = audio_core._get_remote_stt_config()
        assert cfg["url"] == "https://api.elevenlabs.io/v1/speech-to-text"
        assert cfg["model"] == "scribe_v1"
        assert cfg["headers"]["xi-api-key"] == "abc123"
    finally:
        os.environ.pop("ELEVENLABS_API_KEY", None)


def test_configuracao_carregada_habilita_stt_sem_salvar_no_menu(monkeypatch):
    monkeypatch.delenv("ALTAIR_STT_REMOTE_URL", raising=False)
    monkeypatch.delenv("ALTAIR_STT_REMOTE_API_KEY", raising=False)
    monkeypatch.delenv("ALTAIR_STT_REMOTE_MODEL", raising=False)

    audio_core.configurar_stt_remoto(
        {"eleven_api_key": "salva-no-json", "eleven_voice_id": "voice-id"}
    )

    assert audio_core._remote_stt_enabled()
    cfg = audio_core._get_remote_stt_config()
    assert cfg["headers"]["xi-api-key"] == "salva-no-json"
    assert cfg["model"] == "scribe_v1"


def test_audio_core_nao_contem_backend_whisper_local():
    assert not hasattr(audio_core, "_probe_whisper_runtime")
    assert not hasattr(audio_core, "_transcrever_audio_subprocess")


def test_detecta_saudacao_como_palavra_de_ativacao():
    assert audio_core.detectar_wake_word("Olá, chefe")
    assert audio_core.detectar_wake_word("OLA CHEFE!")


def test_nome_personalizado_funciona_como_palavra_de_ativacao():
    audio_core.configurar_nome_assistente("Nébula")
    try:
        assert audio_core.detectar_wake_word("Nébula")
    finally:
        audio_core.configurar_nome_assistente("Altair")
