import threading

from src.altair.core import audio_core


def test_microfone_fecha_stream_quando_loop_e_interrompido(monkeypatch):
    estado = {"fechado": False, "pausas": 0}

    class InputStreamFalso:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            estado["fechado"] = True

    def sleep_interrompivel(_duracao):
        estado["pausas"] += 1
        if estado["pausas"] == 1:
            audio_core._audio_stop_event.set()
        else:
            raise RuntimeError("o stream nao observou o sinal de parada")

    monkeypatch.setattr(audio_core.sd, "InputStream", InputStreamFalso)
    monkeypatch.setattr(audio_core.time, "sleep", sleep_interrompivel)
    monkeypatch.setattr(audio_core, "_audio_stop_event", threading.Event())

    texto = audio_core.ouvir_microfone()

    assert texto == ""
    assert estado["pausas"] == 1
    assert estado["fechado"]


def test_modo_manual_processa_fala_sem_wake_word(monkeypatch):
    recebido = []
    terminou = threading.Event()
    falas = iter(["abra o navegador"])

    class IAFalsa:
        def perguntar(self, texto):
            recebido.append(texto)
            return {"visual": "Comando recebido", "fala": ""}

    def ouvir_uma_fala(**_kwargs):
        try:
            return next(falas)
        except StopIteration:
            audio_core._audio_stop_event.set()
            return ""

    def atualizar_botao(ativo):
        if not ativo:
            terminou.set()

    monkeypatch.setattr(audio_core, "_audio_loop_thread", None)
    monkeypatch.setattr(audio_core, "ouvir_microfone", ouvir_uma_fala)
    monkeypatch.setattr(audio_core, "_audio_stop_event", threading.Event())
    audio_core.set_wake_enabled(True)
    audio_core.set_manual_listen_mode(True)
    try:
        iniciou = audio_core.iniciar_loop_audio(
            app=None,
            ia=IAFalsa(),
            voz=object(),
            adicionar_mensagem=lambda *_args: None,
            atualizar_botao=atualizar_botao,
            trazer_para_frente=lambda: None,
        )

        assert iniciou
        assert terminou.wait(2)
        assert recebido == ["abra o navegador"]
    finally:
        audio_core.set_manual_listen_mode(False)


def test_modo_continuo_aguarda_wake_word(monkeypatch):
    recebido = []
    faladas = []
    terminou = threading.Event()
    falas = iter(["fala sem ativacao", "Altair", "abra o navegador"])

    class IAFalsa:
        def perguntar(self, texto):
            recebido.append(texto)
            return {"visual": "Comando recebido", "fala": ""}

    class VozFalsa:
        def speak(self, texto):
            faladas.append(texto)

    def ouvir_uma_fala(**_kwargs):
        try:
            return next(falas)
        except StopIteration:
            audio_core._audio_stop_event.set()
            return ""

    def atualizar_botao(ativo):
        if not ativo:
            terminou.set()

    monkeypatch.setattr(audio_core, "_audio_loop_thread", None)
    monkeypatch.setattr(audio_core, "ouvir_microfone", ouvir_uma_fala)
    monkeypatch.setattr(audio_core, "_audio_stop_event", threading.Event())
    audio_core.set_wake_enabled(True)
    audio_core.set_manual_listen_mode(False)

    iniciou = audio_core.iniciar_loop_audio(
        app=None,
        ia=IAFalsa(),
        voz=VozFalsa(),
        adicionar_mensagem=lambda *_args: None,
        atualizar_botao=atualizar_botao,
        trazer_para_frente=lambda: None,
    )

    assert iniciou
    assert terminou.wait(2)
    assert recebido == ["abra o navegador"]
    assert faladas == ["Sim senhor."]