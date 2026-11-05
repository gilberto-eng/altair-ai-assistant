import io
import os
import threading
import time
import traceback
import unicodedata
import wave
from difflib import get_close_matches

import numpy as np
import requests
import sounddevice as sd
from altair.core.privacy import external_services_allowed

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", "..", ".."))


def configurar_stt_remoto(config: dict) -> None:
    """Aplica ao processo a configuracao STT carregada pela aplicacao."""
    valores = {
        "ALTAIR_STT_REMOTE_URL": config.get(
            "stt_remote_url", "https://api.elevenlabs.io/v1/speech-to-text"
        ),
        "ALTAIR_STT_REMOTE_API_KEY": config.get("stt_remote_api_key")
        or config.get("eleven_api_key", ""),
        "ALTAIR_STT_REMOTE_MODEL": config.get("stt_remote_model", "scribe_v1"),
        "ALTAIR_STT_REMOTE_LANGUAGE": config.get("stt_remote_language", "pt"),
        "ALTAIR_STT_REMOTE_TIMEOUT": config.get("stt_remote_timeout", "60"),
    }
    for nome, valor in valores.items():
        valor = str(valor or "").strip()
        if valor:
            os.environ[nome] = valor
        else:
            os.environ.pop(nome, None)


def _get_remote_stt_config() -> dict:
    """Retorna a configuracao do provedor de STT remoto."""
    api_key = (os.getenv("ALTAIR_STT_REMOTE_API_KEY") or os.getenv("ELEVENLABS_API_KEY") or "").strip()
    url = (os.getenv("ALTAIR_STT_REMOTE_URL") or "").strip()

    if not url:
        if os.getenv("ELEVENLABS_API_KEY") and not os.getenv("ALTAIR_STT_REMOTE_API_KEY"):
            url = "https://api.elevenlabs.io/v1/speech-to-text"
        else:
            url = "https://api.openai.com/v1/audio/transcriptions"

    model = (os.getenv("ALTAIR_STT_REMOTE_MODEL") or "").strip()
    if not model:
        model = "scribe_v1" if "elevenlabs.io" in url else "whisper-1"

    language = (os.getenv("ALTAIR_STT_REMOTE_LANGUAGE") or "pt").strip() or "pt"
    prompt = (os.getenv("ALTAIR_STT_REMOTE_PROMPT") or "").strip()

    headers = {"Accept": "application/json"}
    if "elevenlabs.io" in url:
        headers = {"xi-api-key": api_key, "Accept": "application/json"}
    elif api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    return {
        "url": url.rstrip("/"),
        "model": model,
        "language": language,
        "prompt": prompt,
        "headers": headers,
        "timeout": int(os.getenv("ALTAIR_STT_REMOTE_TIMEOUT", "60")),
    }


def _remote_stt_enabled() -> bool:
    """Indica se existe configuracao valida para STT remoto."""
    cfg = _get_remote_stt_config()
    if not cfg["url"]:
        return False
    if "elevenlabs.io" in cfg["url"]:
        return bool(cfg["headers"].get("xi-api-key"))
    if cfg["url"] == "https://api.openai.com/v1/audio/transcriptions":
        return bool(cfg["headers"].get("Authorization"))
    return True


def _extract_remote_stt_text(payload):
    """Extrai texto de respostas OpenAI/HuggingFace/compatíveis."""
    if payload is None:
        return ""

    if isinstance(payload, str):
        texto = payload.strip()
        return texto

    if isinstance(payload, (list, tuple)):
        partes = []
        for item in payload:
            texto = _extract_remote_stt_text(item)
            if texto:
                partes.append(texto)
        return " ".join(partes).strip()

    if not isinstance(payload, dict):
        return ""

    for campo in ("text", "transcript", "generated_text", "output"):
        valor = payload.get(campo)
        if isinstance(valor, str) and valor.strip():
            return valor.strip()

    for campo in ("chunks", "segments", "data"):
        valor = payload.get(campo)
        if valor is None:
            continue
        texto = _extract_remote_stt_text(valor)
        if texto:
            return texto

    if isinstance(payload.get("alternative"), list):
        for item in payload["alternative"]:
            if isinstance(item, dict):
                texto = _extract_remote_stt_text(item)
                if texto:
                    return texto

    return ""


def _transcrever_audio_remoto(audio_data: np.ndarray) -> str:
    """Transcreve áudio usando exclusivamente a API STT configurada."""
    if audio_data.size == 0 or not _remote_stt_enabled() or not external_services_allowed():
        return ""

    cfg = _get_remote_stt_config()
    url = cfg["url"]

    try:
        wav_buffer = io.BytesIO()
        audio_int16 = np.clip(audio_data, -1.0, 1.0)
        audio_int16 = (audio_int16 * 32767).astype(np.int16)
        with wave.open(wav_buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(audio_int16.tobytes())

        if "elevenlabs.io" in url:
            multipart = {
                "file": ("audio.wav", wav_buffer.getvalue(), "audio/wav"),
                "model_id": (None, cfg["model"]),
            }
            if cfg["language"]:
                multipart["language_code"] = (None, cfg["language"])
        else:
            multipart = {
                "file": ("audio.wav", wav_buffer.getvalue(), "audio/wav"),
                "model": (None, cfg["model"]),
            }
            if cfg["language"]:
                multipart["language"] = (None, cfg["language"])
            if cfg["prompt"]:
                multipart["prompt"] = (None, cfg["prompt"])

        resp = requests.post(
            url,
            files=multipart,
            headers=cfg["headers"],
            timeout=cfg["timeout"],
        )

        if resp.status_code < 200 or resp.status_code >= 300:
            detalhe = resp.text.strip() or resp.reason or "erro HTTP"
            print(f"AVISO: STT remoto falhou ({resp.status_code}): {detalhe[:200]}")
            return ""

        try:
            payload = resp.json()
        except ValueError:
            payload = resp.text

        texto = _extract_remote_stt_text(payload)
        if texto and texto.strip():
            return texto.strip()

        return ""
    except Exception as exc:
        print(f"AVISO: erro no STT remoto: {exc}")
        return ""

# ==============================
# OUVIR MICROFONE
# ==============================

driver = None
_audio_loop_lock = threading.Lock()
_audio_loop_thread = None
_audio_stop_event = threading.Event()
_wake_enabled = True
_manual_listen_mode = False


def set_wake_enabled(enabled: bool) -> None:
    """Habilita/desabilita o reconhecimento por wake word dentro do loop de audio."""
    global _wake_enabled
    _wake_enabled = bool(enabled)


def wake_enabled() -> bool:
    return bool(_wake_enabled)


def set_manual_listen_mode(enabled: bool) -> None:
    """Define se o loop deve enviar cada fala diretamente, sem wake word."""
    global _manual_listen_mode
    _manual_listen_mode = bool(enabled)


def parar_loop_audio() -> bool:
    """Solicita parada do loop de audio (escuta continua)."""
    _audio_stop_event.set()
    with _audio_loop_lock:
        th = _audio_loop_thread
    return bool(th and th.is_alive())


def ouvir_microfone(on_listen_level=None):
    print("Aguardando fala...")

    if not _remote_stt_enabled():
        return ""

    samplerate = 16000
    threshold = float(os.getenv("ALTAIR_MIC_THRESHOLD", "0.003"))
    silence_limit = 1.5
    max_duration = 10

    audio_chunks = []
    silence_start = None
    speaking = False

    def callback(indata, frames, time_info, status):
        nonlocal silence_start, speaking, audio_chunks

        if _audio_stop_event.is_set():
            raise sd.CallbackStop()

        # RMS real do frame (evita subestimar o volume por divisao excessiva).
        volume = float(np.sqrt(np.mean(np.square(indata))))

        if on_listen_level:
            try:
                on_listen_level(volume)
            except Exception:
                pass

        if volume > threshold:
            speaking = True
            silence_start = None
            audio_chunks.append(indata.copy())

        elif speaking:
            audio_chunks.append(indata.copy())

            if silence_start is None:
                silence_start = time.time()
            elif time.time() - silence_start > silence_limit:
                raise sd.CallbackStop()

    try:
        with sd.InputStream(
            samplerate=samplerate,
            channels=1,
            dtype="float32",
            callback=callback,
        ):
            inicio = time.time()
            while not _audio_stop_event.is_set():
                time.sleep(0.1)
                if time.time() - inicio > max_duration:
                    break
    except Exception:
        pass

    if _audio_stop_event.is_set():
        return ""

    if not audio_chunks:
        return ""

    audio_data = np.concatenate(audio_chunks, axis=0).flatten()
    texto = _transcrever_audio_remoto(audio_data)
    if _audio_stop_event.is_set():
        return ""
    if texto:
        print("TEXTO CAPTADO:", texto)
    return texto


# ==============================
# WAKE WORD
# ==============================

wake_words = ["pode acordar", "altair", "assistente", "altai", "ola chefe"]
_assistant_name = "Altair"


def configurar_nome_assistente(nome: str) -> None:
    global _assistant_name
    nome_limpo = str(nome or "").strip()
    _assistant_name = nome_limpo or "Altair"


def detectar_wake_word(texto):
    texto_normalizado = unicodedata.normalize("NFKD", texto or "")
    texto_normalizado = texto_normalizado.encode("ascii", "ignore").decode("ascii").lower()
    texto_normalizado = "".join(
        caractere if caractere.isalnum() or caractere.isspace() else " "
        for caractere in texto_normalizado
    )
    palavras = texto_normalizado.split()
    texto_unido = "".join(palavras)
    candidatos = palavras + [texto_unido]

    for palavra in candidatos:
        for wake in [*wake_words, _assistant_name]:
            wake_normalizado = unicodedata.normalize("NFKD", wake)
            wake_normalizado = wake_normalizado.encode("ascii", "ignore").decode("ascii").lower()
            wake_sem_espaco = wake_normalizado.replace(" ", "")
            parecido = get_close_matches(
                palavra,
                [wake_normalizado, wake_sem_espaco],
                n=1,
                cutoff=0.78,
            )
            if parecido:
                return True
    return False


# ==============================
# LOOP PRINCIPAL DE AUDIO
# ==============================


def iniciar_loop_audio(
    app,
    ia,
    voz,
    adicionar_mensagem,
    atualizar_botao,
    trazer_para_frente,
    on_speak_start=None,
    on_speak_end=None,
    on_listen_level=None,
):
    global _audio_loop_thread

    with _audio_loop_lock:
        if _audio_loop_thread is not None and _audio_loop_thread.is_alive():
            print("Loop de audio ja esta ativo. Ignorando novo inicio.")
            return False

    _audio_stop_event.clear()

    if not _remote_stt_enabled():
        print("Configure uma API de transcricao remota para habilitar a entrada de voz.")
        return False

    escutando = True

    def loop():
        global _audio_loop_thread
        try:
            print("Modo espera ativado")
            atualizar_botao(True)

            ativo = False
            ultimo_comando = 0
            tempo_timeout = 30

            def falar_altair(texto: str) -> None:
                if not texto:
                    return
                try:
                    if on_speak_start:
                        on_speak_start()
                    voz.speak(texto)
                finally:
                    if on_speak_end:
                        on_speak_end()

            while escutando and (not _audio_stop_event.is_set()):
                texto = ouvir_microfone(on_listen_level=on_listen_level)
                if _audio_stop_event.is_set():
                    break
                if not texto:
                    continue

                # Quando desabilitado pelo usuario, ignora tudo (inclusive wake word).
                if not _wake_enabled:
                    ativo = False
                    continue

                if _manual_listen_mode:
                    ativo = True
                elif detectar_wake_word(texto):
                    trazer_para_frente()
                    falar_altair("Sim senhor.")
                    ativo = True
                    ultimo_comando = time.time()
                    continue

                if ativo:
                    agora = time.time()

                    if not _manual_listen_mode and agora - ultimo_comando > tempo_timeout:
                        ativo = False
                        continue

                    ultimo_comando = agora

                    adicionar_mensagem(texto, "usuario")
                    resposta = ia.perguntar(texto)

                    if isinstance(resposta, dict):
                        resposta_visual = str(resposta.get("visual", "")).strip()
                        resposta_fala = str(resposta.get("fala", "")).strip()
                    else:
                        resposta_visual = str(resposta).strip()
                        resposta_fala = resposta_visual

                    if resposta_visual:
                        adicionar_mensagem(resposta_visual, "ia")
                    if resposta_fala:
                        falar_altair(resposta_fala)
        except Exception as exc:
            print(f"ERRO no loop de audio: {exc}")
            traceback.print_exc()
        finally:
            try:
                atualizar_botao(False)
            except Exception:
                pass
            with _audio_loop_lock:
                _audio_loop_thread = None

    thread = threading.Thread(target=loop, daemon=True, name="altair-audio-loop")
    with _audio_loop_lock:
        _audio_loop_thread = thread
    thread.start()
    return True

