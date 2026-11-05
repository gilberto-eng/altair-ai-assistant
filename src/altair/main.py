import faulthandler
import ipaddress
import json
import os
import secrets
import socket
import sys
import threading
import webbrowser
from difflib import get_close_matches

try:
    faulthandler.enable(all_threads=True)
except Exception:
    pass

from .paths import ASSETS_DIR, CONFIG_DIR, DATA_DIR, PROJECT_ROOT
from .core.secure_storage import (
    is_protected_secret,
    protect_secret,
    read_secret_file,
    unprotect_secret,
)

if "TCL_LIBRARY" not in os.environ or "TK_LIBRARY" not in os.environ:
    if getattr(sys, "frozen", False):
        base_tcl = os.path.join(getattr(sys, "_MEIPASS", ""), "tcl")
    else:
        base_tcl = os.path.join(sys.base_prefix, "tcl")
    tcl_dir = os.path.join(base_tcl, "tcl8.6")
    tk_dir = os.path.join(base_tcl, "tk8.6")
    if os.path.isdir(tcl_dir):
        os.environ.setdefault("TCL_LIBRARY", tcl_dir)
    if os.path.isdir(tk_dir):
        os.environ.setdefault("TK_LIBRARY", tk_dir)

import atexit
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Dict, Optional

from automacao_core import encerrar_servidor_whatsapp_webjs
from PyQt5.QtCore import QTimer, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QWidget

atexit.register(encerrar_servidor_whatsapp_webjs)

from audio_core import configurar_nome_assistente, configurar_stt_remoto, iniciar_loop_audio
from automacao_core import (
    converter_para_ogg,
    enviar_arquivo_whatsapp_webjs,
    enviar_audio_whatsapp_webjs,
    fechar_driver_whatsapp,
)

atexit.register(fechar_driver_whatsapp)

from app.application.command_service import CommandService
from app.application.context_factory import build_intent_context
from app.application.services.file_memory_service import FileMemoryService
from app.interfaces.desktop_ui import DesktopUI
from app.state.session_state import SessionState
from groq_core import GroqDualLLM
from ia_core import IALocal
from intent_router import executar_intencao, resolver_intencao_comando
from voice import ElevenLabsVoice, PiperVoice


def _project_root() -> str:
    return str(PROJECT_ROOT)


def _abrir_url(url: str) -> None:
    try:
        webbrowser.open_new_tab(url)
    except Exception:
        pass


os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

ALTAIR_VERSION = "1.0.0"

try:
    from app.interfaces.web_api import criar_api_app, criar_api_server

    FASTAPI_DISPONIVEL = True
except Exception:
    FASTAPI_DISPONIVEL = False


MEMORIA_ARQUIVOS_FILE = str(DATA_DIR / "memoria_arquivos.json")
APP_CONFIG_FILE = str(DATA_DIR / "json" / "app_config.json")
state = SessionState()
file_memory_service = FileMemoryService(memory_file=MEMORIA_ARQUIVOS_FILE)


def carregar_memoria_arquivos():
    return file_memory_service.carregar_memoria_arquivos()


def salvar_memoria_arquivos(memoria):
    file_memory_service.salvar_memoria_arquivos(memoria)


def extrair_texto_arquivo(caminho_arquivo, limite_chars=14000):
    return file_memory_service.extrair_texto_arquivo(
        caminho_arquivo, limite_chars=limite_chars
    )


def resumir_texto_arquivo(nome_arquivo, texto, llm):
    return file_memory_service.resumir_texto_arquivo(nome_arquivo, texto, llm)


def analisar_e_memorizar_arquivo(caminho_arquivo, llm):
    return file_memory_service.analisar_e_memorizar_arquivo(caminho_arquivo, llm)


def _carregar_config_app() -> Dict[str, str]:
    if os.path.exists(APP_CONFIG_FILE):
        try:
            with open(APP_CONFIG_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def _salvar_config_app(cfg: Dict[str, str]) -> None:
    pasta = os.path.dirname(APP_CONFIG_FILE)
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    with open(APP_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


api_lock = threading.Lock()
command_service = None
ia = None
voz = None
ui = None
API_HOST = "127.0.0.1"
API_PORT = 8000


def _env_int(nome: str, padrao: int) -> int:
    valor = os.getenv(nome, str(padrao)).strip()
    try:
        return int(valor)
    except ValueError:
        return padrao


def _descobrir_ip_local() -> str:
    for ip in _descobrir_ips_locais():
        return ip
    return "127.0.0.1"


def _descobrir_ips_locais() -> tuple[str, ...]:
    ips = []
    vistos = set()

    def adicionar_ip(ip: str) -> None:
        if not ip or ip in vistos:
            return
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return
        if addr.version != 4 or addr.is_loopback:
            return
        vistos.add(ip)
        ips.append(ip)

    for alvo in (("8.8.8.8", 80), ("1.1.1.1", 80)):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(alvo)
            adicionar_ip(s.getsockname()[0])
        except Exception:
            pass
        finally:
            s.close()

    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            adicionar_ip(ip)
    except Exception:
        pass

    ips_privados = [ip for ip in ips if ipaddress.ip_address(ip).is_private]
    if ips_privados:
        return tuple(ips_privados)
    return tuple(ips)


def _api_tls_paths() -> tuple[Optional[str], Optional[str]]:
    cert = os.getenv("ALTAIR_API_SSL_CERTFILE", "").strip()
    key = os.getenv("ALTAIR_API_SSL_KEYFILE", "").strip()
    if cert and key and os.path.isfile(cert) and os.path.isfile(key):
        return cert, key
    return None, None


def _is_loopback_host(host: str) -> bool:
    return host.strip().lower() in {"127.0.0.1", "localhost", "::1"}


def _resolver_host_api() -> str:
    host_env = os.getenv("ALTAIR_API_HOST", "").strip() or "127.0.0.1"
    if _is_loopback_host(host_env):
        return host_env
    cert, key = _api_tls_paths()
    if cert and key:
        return host_env
    print("API remota desativada: configure certificado TLS e chave privada validos.")
    return "127.0.0.1"


def _resolver_host_qr() -> str:
    host_qr_env = os.getenv("ALTAIR_QR_HOST", "").strip()
    if host_qr_env:
        return host_qr_env
    return _descobrir_ip_local()


def _montar_url_conexao_remota() -> str:
    base_custom = os.getenv("ALTAIR_REMOTE_PUBLIC_URL", "").strip().rstrip("/")
    if base_custom:
        if not base_custom.lower().startswith("https://"):
            return ""
        base = base_custom
    else:
        host_qr = API_HOST
        if API_HOST in ("0.0.0.0", "::", "127.0.0.1", "localhost", "::1"):
            host_qr = _resolver_host_qr()
        scheme = "https" if not _is_loopback_host(API_HOST) else "http"
        base = f"{scheme}://{host_qr}:{API_PORT}"

    return f"{base}/"


def _carregar_token_remoto() -> str:
    token_env = os.getenv("ALTAIR_REMOTE_TOKEN", "").strip()
    if token_env:
        return token_env

    token_file = os.getenv("ALTAIR_REMOTE_TOKEN_FILE", "").strip() or str(
        CONFIG_DIR / "remote_api_token.txt"
    )
    if token_file and os.path.exists(token_file):
        token = read_secret_file(token_file)
        if token:
            return token
    token = secrets.token_urlsafe(32)
    try:
        os.makedirs(os.path.dirname(os.path.abspath(token_file)), exist_ok=True)
        with open(token_file, "w", encoding="utf-8") as f:
            f.write(protect_secret(token))
    except Exception as e:
        print("Falha ao gravar token remoto protegido:", e)
        return ""
    return token


def _startup_dir() -> str:
    appdata = os.getenv("APPDATA", "")
    if not appdata:
        return ""
    return os.path.join(
        appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
    )


def _startup_cmd_path() -> str:
    pasta = _startup_dir()
    if not pasta:
        return ""
    return os.path.join(pasta, "AltairStartup.cmd")


def _startup_ativo() -> bool:
    caminho = _startup_cmd_path()
    return bool(caminho and os.path.exists(caminho))


def _startup_cmd_content(
    exe_path: str,
    project_root: str,
    module_mode: bool = False,
    script_path: Optional[str] = None,
) -> str:
    lines = ["@echo off", f'cd /d "{project_root}"']
    if module_mode:
        lines.append(f'start "" "{exe_path}" -m run_altair')
    elif script_path:
        lines.append(f'start "" "{exe_path}" "{script_path}"')
    else:
        lines.append(f'start "" "{exe_path}"')
    return "\n".join(lines) + "\n"


def _habilitar_startup(
    exe_path: str,
    project_root: str,
    module_mode: bool = False,
    script_path: Optional[str] = None,
) -> bool:
    pasta = _startup_dir()
    if not pasta:
        return False
    os.makedirs(pasta, exist_ok=True)
    cmd_path = _startup_cmd_path()
    conteudo = _startup_cmd_content(exe_path, project_root, module_mode, script_path)
    try:
        with open(cmd_path, "w", encoding="utf-8") as f:
            f.write(conteudo)
        return True
    except Exception:
        return False


def _desabilitar_startup() -> bool:
    cmd_path = _startup_cmd_path()
    if not cmd_path or not os.path.exists(cmd_path):
        return True
    try:
        os.remove(cmd_path)
        return True
    except Exception:
        return False


def _alternar_startup_windows() -> Optional[bool]:
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if getattr(sys, "frozen", False):
        exe_path = sys.executable
        module_mode = False
        script_path = None
    else:
        exe_path = sys.executable
        module_mode = True
        script_path = None

    if not exe_path or not os.path.exists(exe_path):
        messagebox.showerror("Erro", "Nao consegui localizar o executavel atual.")
        return None

    if _startup_ativo():
        ok = _desabilitar_startup()
        if ok:
            messagebox.showinfo("Startup", "Inicializacao com Windows desativada.")
            return False
        messagebox.showerror("Erro", "Falha ao desativar a inicializacao.")
        return None

    ok = _habilitar_startup(
        exe_path, project_root, module_mode=module_mode, script_path=script_path
    )
    if ok:
        messagebox.showinfo("Startup", "Altair sera iniciado junto com o Windows.")
        return True
    messagebox.showerror("Erro", "Falha ao ativar a inicializacao.")
    return None


def abrir_interface_conexao_remota(app_root: tk.Tk) -> None:
    if not FASTAPI_DISPONIVEL:
        messagebox.showerror(
            "Erro", "FastAPI/uvicorn nao encontrados. API remota desativada."
        )
        return

    if _is_loopback_host(API_HOST):
        messagebox.showinfo(
            "Acesso remoto desativado",
            "Por seguranca, o Altair aceita conexoes apenas deste computador por padrao. "
            "Para habilitar acesso pela rede, configure ALTAIR_API_HOST, "
            "ALTAIR_API_SSL_CERTFILE e ALTAIR_API_SSL_KEYFILE com um certificado TLS confiavel "
            "e reinicie o Altair.",
        )
        return
    if not messagebox.askyesno(
        "Ativar acesso remoto",
        "Dispositivos que possuam o token poderao enviar comandos ao Altair e controlar este PC. "
        "A conexao sera criptografada por TLS. Deseja continuar?",
    ):
        return

    url = _montar_url_conexao_remota()
    if not url:
        messagebox.showerror(
            "URL remota invalida",
            "O endereco remoto precisa usar HTTPS.",
        )
        return

    try:
        import qrcode
        from PIL import ImageTk
    except Exception as e:
        messagebox.showerror(
            "Dependencia ausente",
            "Para gerar QR code, instale 'qrcode' e 'pillow'.\n" f"Detalhe: {e}",
        )
        return

    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    photo = ImageTk.PhotoImage(img)

    win = tk.Toplevel(app_root)
    win.title("Conectar Remotamente")
    win.geometry("430x560")
    win.resizable(False, False)

    tk.Label(
        win,
        text="Escaneie o QR code para conectar no Altair remoto.",
        font=("Segoe UI", 11, "bold"),
        wraplength=390,
        justify="left",
    ).pack(padx=14, pady=(14, 8), anchor="w")

    token_remoto = _carregar_token_remoto()
    aviso_token = "Token de autenticacao (guarde-o com seguranca):"

    tk.Label(win, text=aviso_token, font=("Segoe UI", 9), wraplength=390, justify="left").pack(
        padx=14, pady=(0, 4), anchor="w"
    )
    token_entry = tk.Entry(win, width=58)
    token_entry.pack(padx=14, pady=(0, 10))
    token_entry.insert(0, token_remoto)
    token_entry.configure(state="readonly")

    qr_label = tk.Label(win, image=photo)
    qr_label.image = photo
    qr_label.pack(pady=4)

    entry_url = tk.Entry(win, width=58)
    entry_url.pack(padx=14, pady=(10, 6))
    entry_url.insert(0, url)
    entry_url.configure(state="readonly")

    def copiar_url():
        app_root.clipboard_clear()
        app_root.clipboard_append(url)
        messagebox.showinfo(
            "Copiado", "URL remota copiada para a area de transferencia."
        )

    tk.Button(win, text="Copiar URL", command=copiar_url).pack(pady=(2, 8))

    aviso_host = (
        "Se nao abrir no celular, defina ALTAIR_QR_HOST com o IP do PC na rede Wi-Fi. "
        "Para acesso externo a sua rede, configure ALTAIR_REMOTE_PUBLIC_URL."
    )
    tk.Label(
        win, text=aviso_host, font=("Segoe UI", 9), wraplength=390, justify="left"
    ).pack(padx=14, pady=(2, 0), anchor="w")


def montar_contexto_intencoes() -> Dict:
    return build_intent_context(
        state=state,
        analisar_e_memorizar_arquivo=analisar_e_memorizar_arquivo,
        ia_llm=ia.llm,
        carregar_memoria_arquivos=carregar_memoria_arquivos,
        enviar_arquivo_whatsapp_webjs=enviar_arquivo_whatsapp_webjs,
        voz=voz,
        converter_para_ogg=converter_para_ogg,
        enviar_audio_whatsapp_webjs=enviar_audio_whatsapp_webjs,
        base_dir=__file__,
    )


def processar_comando_altair(comando: str, falar: bool = False) -> Dict[str, str]:
    if command_service is None:
        return {"visual": "Servico de comando ainda nao inicializado.", "fala": ""}
    return command_service.execute(comando, falar=falar)


if FASTAPI_DISPONIVEL:
    API_HOST = _resolver_host_api()
    API_PORT = _env_int("ALTAIR_API_PORT", 8000)
    API_REMOTE_TOKEN = _carregar_token_remoto()
    api_app = criar_api_app(processar_comando_altair, api_lock, token=API_REMOTE_TOKEN)
    _api_cert, _api_key = _api_tls_paths()
    if _is_loopback_host(API_HOST):
        _api_cert, _api_key = None, None
    api_server = criar_api_server(
        api_app,
        API_HOST,
        API_PORT,
        ssl_certfile=_api_cert,
        ssl_keyfile=_api_key,
    )
    api_server_thread = None


wake_words = ["pode acordar", "altair", "alto ai", "assistente", "altai", "bom dia"]


def detectar_wake_word(texto: str) -> bool:
    palavras = texto.split()
    texto_unido = texto.replace(" ", "")
    candidatos = palavras + [texto_unido]

    for palavra in candidatos:
        for wake in wake_words:
            wake_sem_espaco = wake.replace(" ", "")
            parecido = get_close_matches(
                palavra, [wake, wake_sem_espaco], n=1, cutoff=0.6
            )
            if parecido:
                return True
    return False


def iniciar_audio() -> bool:
    return bool(iniciar_loop_audio(
        ui,
        ia,
        voz,
        ui.adicionar_mensagem,
        ui.atualizar_botao_microfone,
        ui.trazer_para_frente,
        on_speak_start=lambda: ui.set_hud_responding(True),
        on_speak_end=lambda: ui.set_hud_responding(False),
        on_listen_level=ui.set_hud_audio_level,
    ))


JSON_FILE = str(CONFIG_DIR / "apps.json")
LLM_CONFIG_FILE = str(DATA_DIR / "json" / "llm_provider_config.json")
VOICE_CONFIG_FILE = str(DATA_DIR / "json" / "voice_config.json")

PROVEDORES_LLM = {
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
    "local": "http://127.0.0.1:11434/v1/chat/completions",
}

if os.path.exists(JSON_FILE):
    with open(JSON_FILE, encoding="utf-8") as f:
        APLICATIVOS_CONHECIDOS = json.load(f)
else:
    APLICATIVOS_CONHECIDOS = {}


def salvar_apps() -> None:
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(APLICATIVOS_CONHECIDOS, f, indent=4, ensure_ascii=False)


def _carregar_api_key_groq_padrao() -> str:
    key_env = os.getenv("GROQ_API_KEY", "").strip()
    if key_env:
        return key_env

    key_file = os.getenv(
        "GROQ_API_KEY_FILE",
        os.path.join(CONFIG_DIR, "groq_api_key.txt"),
    ).strip()
    if key_file and os.path.exists(key_file):
        return read_secret_file(key_file)
    return ""


def _config_llm_padrao() -> Dict[str, str]:
    return {
        "provider": "groq",
        "api_key": _carregar_api_key_groq_padrao(),
        "base_url": PROVEDORES_LLM["groq"],
        "model_main": os.getenv("ALTAIR_GROQ_LARGE_MODEL", "llama-3.3-70b-versatile"),
        "model_router": os.getenv("ALTAIR_GROQ_SMALL_MODEL", ""),
    }


def carregar_config_llm() -> Dict[str, str]:
    cfg = _config_llm_padrao()
    migrate_key = False
    if os.path.exists(LLM_CONFIG_FILE):
        try:
            with open(LLM_CONFIG_FILE, encoding="utf-8") as f:
                dados = json.load(f)
            if isinstance(dados, dict):
                for k in (
                    "provider",
                    "api_key",
                    "base_url",
                    "model_main",
                    "model_router",
                ):
                    if k in dados and isinstance(dados[k], str):
                        raw_value = dados[k].strip()
                        if k == "api_key":
                            cfg[k] = unprotect_secret(raw_value)
                            migrate_key = bool(raw_value) and not is_protected_secret(raw_value)
                        else:
                            cfg[k] = raw_value
        except Exception as e:
            print("Aviso: falha ao carregar configuracao de LLM:", e)

    prov = cfg.get("provider", "groq").strip().lower()
    if prov not in {"groq", "openai", "local", "custom"}:
        prov = "groq"
    cfg["provider"] = prov

    if prov != "custom":
        cfg["base_url"] = PROVEDORES_LLM[prov]

    if not cfg.get("model_main"):
        cfg["model_main"] = _config_llm_padrao()["model_main"]

    if not cfg.get("model_router"):
        cfg["model_router"] = cfg["model_main"]

    if migrate_key:
        salvar_config_llm(cfg)

    return cfg


def salvar_config_llm(cfg: Dict[str, str]) -> None:
    pasta = os.path.dirname(LLM_CONFIG_FILE)
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    dados = dict(cfg)
    dados["api_key"] = protect_secret(str(dados.get("api_key", "")))
    with open(LLM_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)


def criar_llm_por_config(cfg: Dict[str, str]) -> GroqDualLLM:
    prov = (cfg.get("provider") or "groq").strip().lower()
    base_url = (cfg.get("base_url") or "").strip()
    if prov in PROVEDORES_LLM:
        base_url = PROVEDORES_LLM[prov]
    if not base_url:
        base_url = PROVEDORES_LLM["groq"]

    model_main = (cfg.get("model_main") or "").strip()
    model_router = (cfg.get("model_router") or "").strip() or model_main

    return GroqDualLLM(
        api_key=(cfg.get("api_key") or "").strip(),
        base_url=base_url,
        large_model=model_main,
        small_model=model_main,
        router_model=model_router,
        require_api_key=(prov != "local"),
    )


def aplicar_config_llm(cfg: Dict[str, str]) -> None:
    ia.llm = criar_llm_por_config(cfg)


def abrir_interface_llm_config(app_root: tk.Tk) -> None:
    cfg_atual = carregar_config_llm()

    win = tk.Toplevel(app_root)
    win.title("Configurar API e Modelos")
    win.geometry("560x400")
    win.resizable(False, False)

    tk.Label(win, text="Provedor").pack(anchor="w", padx=14, pady=(12, 2))
    prov_var = tk.StringVar(value=cfg_atual["provider"])
    prov_menu = tk.OptionMenu(win, prov_var, "groq", "openai", "local", "custom")
    prov_menu.config(width=18)
    prov_menu.pack(anchor="w", padx=14)

    tk.Label(win, text="API Key").pack(anchor="w", padx=14, pady=(10, 2))
    row_key = tk.Frame(win)
    row_key.pack(anchor="w", padx=14, fill="x")
    entry_key = tk.Entry(row_key, width=72, show="*")
    entry_key.insert(0, cfg_atual.get("api_key", ""))
    entry_key.pack(side="left", fill="x", expand=True)
    tk.Button(row_key, text="Link para criar sua API", command=lambda: _abrir_url("https://console.groq.com/keys")).pack(side="left", padx=(8, 0))

    tk.Label(win, text="Base URL (custom/local)").pack(
        anchor="w", padx=14, pady=(10, 2)
    )
    entry_base = tk.Entry(win, width=72)
    entry_base.insert(0, cfg_atual.get("base_url", ""))
    entry_base.pack(anchor="w", padx=14)

    tk.Label(win, text="Modelo principal (respostas)").pack(
        anchor="w", padx=14, pady=(10, 2)
    )
    entry_main = tk.Entry(win, width=72)
    entry_main.insert(0, cfg_atual.get("model_main", ""))
    entry_main.pack(anchor="w", padx=14)

    tk.Label(win, text="Modelo menor (interpretar comandos) - opcional").pack(
        anchor="w", padx=14, pady=(10, 2)
    )
    entry_router = tk.Entry(win, width=72)
    entry_router.insert(0, cfg_atual.get("model_router", ""))
    entry_router.pack(anchor="w", padx=14)

    aviso = tk.Label(
        win,
        text="Se o modelo menor ficar vazio, o principal sera usado automaticamente.",
        fg="#6a6a6a",
    )
    aviso.pack(anchor="w", padx=14, pady=(8, 0))

    def atualizar_base_url(*_args):
        prov = prov_var.get().strip().lower()
        if prov in {"groq", "openai"}:
            entry_base.delete(0, tk.END)
            entry_base.insert(0, PROVEDORES_LLM[prov])
            entry_base.config(state="readonly")
        else:
            entry_base.config(state="normal")
            if prov == "local" and not entry_base.get().strip():
                entry_base.insert(0, PROVEDORES_LLM["local"])

    prov_var.trace_add("write", atualizar_base_url)
    atualizar_base_url()

    def salvar_llm():
        prov = prov_var.get().strip().lower()
        api_key = entry_key.get().strip()
        base_url = entry_base.get().strip()
        model_main = entry_main.get().strip()
        model_router = entry_router.get().strip()

        if prov not in {"groq", "openai", "local", "custom"}:
            messagebox.showerror("Erro", "Provedor invalido.")
            return
        if not model_main:
            messagebox.showerror("Erro", "Informe o modelo principal.")
            return
        if prov in {"custom", "local"} and not base_url:
            messagebox.showerror(
                "Erro", "Informe a Base URL para provedor custom/local."
            )
            return
        if not model_router:
            model_router = model_main

        cfg_novo = {
            "provider": prov,
            "api_key": api_key,
            "base_url": (
                base_url if prov in {"custom", "local"} else PROVEDORES_LLM[prov]
            ),
            "model_main": model_main,
            "model_router": model_router,
        }
        salvar_config_llm(cfg_novo)
        aplicar_config_llm(cfg_novo)
        if ui:
            ui.set_ia_status("IA: API/modelos atualizados")
            QTimer.singleShot(1800, lambda: ui.set_ia_status("IA: Pronta"))
        messagebox.showinfo("Sucesso", "Configuracao aplicada com sucesso.")
        win.destroy()

    tk.Button(win, text="Salvar e aplicar", command=salvar_llm).pack(
        anchor="e", padx=14, pady=14
    )


def _config_voz_padrao() -> Dict[str, str]:
    base_dir = _project_root()
    eleven_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    return {
        "provider": "elevenlabs",
        "assistant_name": os.getenv("ALTAIR_ASSISTANT_NAME", "Altair").strip() or "Altair",
        "piper_model": os.path.join(
            ASSETS_DIR, "piper", "voices", "pt_BR-faber-medium.onnx"
        ),
        "piper_length_scale": "1.08",
        "piper_noise_scale": "0.38",
        "piper_noise_w": "0.52",
        "piper_modo_pro": "1",
        "eleven_api_key": eleven_key,
        "eleven_voice_id": os.getenv("ELEVENLABS_VOICE_ID", "").strip(),
        "eleven_model_id": os.getenv(
            "ELEVENLABS_MODEL_ID", "eleven_multilingual_v2"
        ).strip(),
        "stt_remote_url": os.getenv("ALTAIR_STT_REMOTE_URL", "https://api.elevenlabs.io/v1/speech-to-text").strip(),
        "stt_remote_api_key": os.getenv("ALTAIR_STT_REMOTE_API_KEY", eleven_key).strip(),
        "stt_remote_model": os.getenv("ALTAIR_STT_REMOTE_MODEL", "scribe_v1").strip(),
        "stt_remote_language": os.getenv("ALTAIR_STT_REMOTE_LANGUAGE", "pt").strip(),
        "stt_remote_timeout": os.getenv("ALTAIR_STT_REMOTE_TIMEOUT", "60").strip(),
    }


def carregar_config_voz() -> Dict[str, str]:
    cfg = _config_voz_padrao()
    migrate_secret = False
    if os.path.exists(VOICE_CONFIG_FILE):
        try:
            with open(VOICE_CONFIG_FILE, encoding="utf-8") as f:
                dados = json.load(f)
            if isinstance(dados, dict):
                for k in cfg:
                    if k in dados and isinstance(dados[k], str):
                        raw_value = dados[k].strip()
                        if k in {"eleven_api_key", "stt_remote_api_key"}:
                            cfg[k] = unprotect_secret(raw_value)
                            migrate_secret = migrate_secret or (
                                bool(raw_value) and not is_protected_secret(raw_value)
                            )
                        else:
                            cfg[k] = raw_value
        except Exception as e:
            print("Aviso: falha ao carregar configuracao de voz:", e)

    if not cfg.get("stt_remote_api_key"):
        cfg["stt_remote_api_key"] = cfg.get("eleven_api_key", "")
    if not cfg.get("stt_remote_url"):
        cfg["stt_remote_url"] = "https://api.elevenlabs.io/v1/speech-to-text"
    if not cfg.get("stt_remote_model"):
        cfg["stt_remote_model"] = "scribe_v1"
    if not cfg.get("stt_remote_language"):
        cfg["stt_remote_language"] = "pt"
    if not cfg.get("stt_remote_timeout"):
        cfg["stt_remote_timeout"] = "60"

    prov = cfg.get("provider", "elevenlabs").strip().lower()
    if prov != "elevenlabs":
        prov = "elevenlabs"
    cfg["provider"] = prov
    if migrate_secret:
        salvar_config_voz(cfg)
    return cfg


def salvar_config_voz(cfg: Dict[str, str]) -> None:
    pasta = os.path.dirname(VOICE_CONFIG_FILE)
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    dados = dict(cfg)
    for key in ("eleven_api_key", "stt_remote_api_key"):
        dados[key] = protect_secret(str(dados.get(key, "")))
    with open(VOICE_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)


def _to_float(valor: str, padrao: float) -> float:
    try:
        return float((valor or "").strip())
    except Exception:
        return float(padrao)


def criar_voz_por_config(cfg: Dict[str, str]):
    return ElevenLabsVoice(
        api_key=(cfg.get("eleven_api_key") or "").strip(),
        voice_id=(cfg.get("eleven_voice_id") or "").strip(),
        model_id=(cfg.get("eleven_model_id") or "eleven_multilingual_v2").strip(),
        fallback_voice=None,
    )


def aplicar_config_voz(cfg: Dict[str, str]) -> None:
    global voz
    voz = criar_voz_por_config(cfg)
    ia.piper = voz
    configurar_nome_assistente(cfg.get("assistant_name", "Altair"))

    for chave, nome_env in {
        "stt_remote_url": "ALTAIR_STT_REMOTE_URL",
        "stt_remote_api_key": "ALTAIR_STT_REMOTE_API_KEY",
        "stt_remote_model": "ALTAIR_STT_REMOTE_MODEL",
        "stt_remote_language": "ALTAIR_STT_REMOTE_LANGUAGE",
        "stt_remote_timeout": "ALTAIR_STT_REMOTE_TIMEOUT",
        "eleven_api_key": "ELEVENLABS_API_KEY",
        "eleven_voice_id": "ELEVENLABS_VOICE_ID",
        "eleven_model_id": "ELEVENLABS_MODEL_ID",
    }.items():
        valor = (cfg.get(chave) or "").strip()
        if valor:
            os.environ[nome_env] = valor
        elif nome_env in os.environ:
            os.environ.pop(nome_env, None)

    if not os.getenv("ALTAIR_STT_REMOTE_API_KEY") and os.getenv("ELEVENLABS_API_KEY"):
        os.environ["ALTAIR_STT_REMOTE_API_KEY"] = os.environ["ELEVENLABS_API_KEY"]
    if not os.getenv("ALTAIR_STT_REMOTE_URL"):
        os.environ["ALTAIR_STT_REMOTE_URL"] = "https://api.elevenlabs.io/v1/speech-to-text"
    if not os.getenv("ALTAIR_STT_REMOTE_MODEL"):
        os.environ["ALTAIR_STT_REMOTE_MODEL"] = "scribe_v1"
    if not os.getenv("ALTAIR_STT_REMOTE_LANGUAGE"):
        os.environ["ALTAIR_STT_REMOTE_LANGUAGE"] = "pt"
    if not os.getenv("ALTAIR_STT_REMOTE_TIMEOUT"):
        os.environ["ALTAIR_STT_REMOTE_TIMEOUT"] = "60"

    if command_service:
        command_service.voz = voz
    if ui:
        ui.atualizar_callback_voz(voz.speak, voz.stop)


def salvar_nome_assistente(nome: str) -> None:
    cfg = carregar_config_voz()
    cfg["assistant_name"] = nome.strip() or "Altair"
    salvar_config_voz(cfg)
    configurar_nome_assistente(cfg["assistant_name"])


def abrir_interface_voz_config(app_root: tk.Tk) -> None:
    cfg_atual = carregar_config_voz()

    win = tk.Toplevel(app_root)
    win.title("Configurar Voz")
    win.geometry("620x520")
    win.resizable(False, False)

    tk.Label(win, text="Provedor de voz").pack(anchor="w", padx=14, pady=(12, 2))
    prov_var = tk.StringVar(value="elevenlabs")
    prov_menu = tk.OptionMenu(win, prov_var, "elevenlabs")
    prov_menu.config(width=18)
    prov_menu.pack(anchor="w", padx=14)

    tk.Label(win, text="ElevenLabs - API Key").pack(anchor="w", padx=14, pady=(14, 2))
    eleven_key = tk.Entry(win, width=80, show="*")
    eleven_key.insert(0, cfg_atual.get("eleven_api_key", ""))
    eleven_key.pack(anchor="w", padx=14)

    tk.Label(win, text="ElevenLabs - Voice ID").pack(anchor="w", padx=14, pady=(10, 2))
    eleven_voice = tk.Entry(win, width=80)
    eleven_voice.insert(0, cfg_atual.get("eleven_voice_id", ""))
    eleven_voice.pack(anchor="w", padx=14)

    tk.Label(win, text="ElevenLabs - Model ID").pack(anchor="w", padx=14, pady=(10, 2))
    eleven_model = tk.Entry(win, width=80)
    eleven_model.insert(0, cfg_atual.get("eleven_model_id", "eleven_multilingual_v2"))
    eleven_model.pack(anchor="w", padx=14)

    tk.Label(win, text="STT remoto - URL").pack(anchor="w", padx=14, pady=(14, 2))
    stt_url = tk.Entry(win, width=80)
    stt_url.insert(0, cfg_atual.get("stt_remote_url", "https://api.elevenlabs.io/v1/speech-to-text"))
    stt_url.pack(anchor="w", padx=14)

    tk.Label(win, text="STT remoto - API Key (opcional; usa ElevenLabs se vazio)").pack(anchor="w", padx=14, pady=(10, 2))
    stt_key = tk.Entry(win, width=80, show="*")
    stt_key.insert(0, cfg_atual.get("stt_remote_api_key", cfg_atual.get("eleven_api_key", "")))
    stt_key.pack(anchor="w", padx=14)

    tk.Label(win, text="STT remoto - Modelo").pack(anchor="w", padx=14, pady=(10, 2))
    stt_model = tk.Entry(win, width=80)
    stt_model.insert(0, cfg_atual.get("stt_remote_model", "scribe_v1"))
    stt_model.pack(anchor="w", padx=14)

    tk.Label(win, text="STT remoto - Idioma").pack(anchor="w", padx=14, pady=(10, 2))
    stt_lang = tk.Entry(win, width=80)
    stt_lang.insert(0, cfg_atual.get("stt_remote_language", "pt"))
    stt_lang.pack(anchor="w", padx=14)

    tk.Label(win, text="STT remoto - Timeout (segundos)").pack(anchor="w", padx=14, pady=(10, 2))
    stt_timeout = tk.Entry(win, width=80)
    stt_timeout.insert(0, cfg_atual.get("stt_remote_timeout", "60"))
    stt_timeout.pack(anchor="w", padx=14)

    aviso = tk.Label(
        win,
        text=(
            "Troca aplicada na hora. Para ElevenLabs, informe API Key e Voice ID. "
            "Para transcricao de fala do usuario, use a mesma chave do ElevenLabs ou defina "
            "um endpoint remoto diferente."
        ),
        fg="#6a6a6a",
    )
    aviso.pack(anchor="w", padx=14, pady=(10, 0))

    def salvar_voz():
        prov = prov_var.get().strip().lower()
        cfg_novo = {
            "provider": "elevenlabs",
            "assistant_name": cfg_atual.get("assistant_name", "Altair"),
            "piper_model": "",
            "piper_length_scale": "1.08",
            "piper_noise_scale": "0.38",
            "piper_noise_w": "0.52",
            "piper_modo_pro": "1",
            "eleven_api_key": eleven_key.get().strip(),
            "eleven_voice_id": eleven_voice.get().strip(),
            "eleven_model_id": eleven_model.get().strip() or "eleven_multilingual_v2",
            "stt_remote_url": stt_url.get().strip() or "https://api.elevenlabs.io/v1/speech-to-text",
            "stt_remote_api_key": stt_key.get().strip() or eleven_key.get().strip(),
            "stt_remote_model": stt_model.get().strip() or "scribe_v1",
            "stt_remote_language": stt_lang.get().strip() or "pt",
            "stt_remote_timeout": stt_timeout.get().strip() or "60",
        }

        if prov != "elevenlabs":
            messagebox.showerror("Erro", "Provedor de voz invalido.")
            return
        if not cfg_novo["eleven_api_key"]:
            messagebox.showerror("Erro", "Informe a API Key do ElevenLabs.")
            return
        if not cfg_novo["eleven_voice_id"]:
            messagebox.showerror("Erro", "Informe o Voice ID do ElevenLabs.")
            return

        salvar_config_voz(cfg_novo)
        aplicar_config_voz(cfg_novo)
        if ui:
            ui.set_ia_status("IA: Voz atualizada")
            QTimer.singleShot(1800, lambda: ui.set_ia_status("IA: Pronta"))
        messagebox.showinfo("Sucesso", "Configuracao de voz aplicada.")
        win.destroy()

    tk.Button(win, text="Salvar e aplicar", command=salvar_voz).pack(
        anchor="e", padx=14, pady=14
    )


def abrir_interface_cadastro(app_root: tk.Tk) -> None:
    cadastro_win = tk.Toplevel(app_root)
    cadastro_win.title("Cadastro de Aplicativos ALTAIR")
    cadastro_win.geometry("400x250")

    tk.Label(cadastro_win, text="Nome do aplicativo:").pack(pady=5)
    entry_nome = tk.Entry(cadastro_win, width=40)
    entry_nome.pack(pady=5)

    label_status = tk.Label(
        cadastro_win, text=f"{len(APLICATIVOS_CONHECIDOS)} apps cadastrados"
    )
    label_status.pack(pady=5)

    def adicionar_app():
        caminho = filedialog.askopenfilename(
            title="Escolha o executavel do app", filetypes=[("Executaveis", "*.exe")]
        )
        if not caminho:
            return

        nome = entry_nome.get().strip().lower()
        if not nome:
            messagebox.showerror("Erro", "Digite um nome para o aplicativo")
            return

        APLICATIVOS_CONHECIDOS[nome] = caminho
        salvar_apps()
        messagebox.showinfo("Sucesso", f"Aplicativo '{nome}' adicionado!")
        entry_nome.delete(0, tk.END)
        label_status.config(text=f"{len(APLICATIVOS_CONHECIDOS)} apps cadastrados")

    tk.Button(
        cadastro_win, text="Escolher executavel e adicionar", command=adicionar_app
    ).pack(pady=10)


def atualizar_arquivo_selecionado(caminho: str) -> None:
    state.arquivo_selecionado_envio = caminho


def processar_comando_ui(comando: str) -> Dict[str, str]:
    with api_lock:
        return processar_comando_altair(comando, falar=False)


def _qt_message_box(parent, icon, title: str, text: str) -> None:
    from PyQt5.QtWidgets import QMessageBox

    box = QMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(title)
    box.setText(text)
    box.exec_()


def abrir_interface_conexao_remota(parent: QWidget) -> None:
    from io import BytesIO

    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QPixmap
    from PyQt5.QtWidgets import (
        QApplication,
        QDialog,
        QLabel,
        QLineEdit,
        QMessageBox,
        QPushButton,
        QVBoxLayout,
    )

    if not FASTAPI_DISPONIVEL:
        _qt_message_box(
            parent,
            QMessageBox.Critical,
            "Erro",
            "FastAPI/uvicorn nao encontrados. API remota desativada.",
        )
        return

    try:
        import qrcode
    except Exception as e:
        _qt_message_box(
            parent,
            QMessageBox.Critical,
            "Dependencia ausente",
            "Para gerar QR code, instale 'qrcode' e 'pillow'.\n" f"Detalhe: {e}",
        )
        return

    url = _montar_url_conexao_remota()
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    buf = BytesIO()
    img.save(buf, format="PNG")
    photo = QPixmap()
    photo.loadFromData(buf.getvalue(), "PNG")

    win = QDialog(parent)
    win.setWindowTitle("Conectar Remotamente")
    win.resize(430, 560)
    layout = QVBoxLayout(win)

    title = QLabel("Escaneie o QR code para conectar no Altair remoto.")
    title.setWordWrap(True)
    layout.addWidget(title)

    token_remoto = _carregar_token_remoto()
    aviso_token = (
        "Token remoto ativo. Informe o token no app remoto."
        if token_remoto
        else "A conexao remota esta sem token de autenticacao."
    )
    aviso = QLabel(aviso_token)
    aviso.setWordWrap(True)
    layout.addWidget(aviso)

    qr_label = QLabel()
    qr_label.setAlignment(Qt.AlignCenter)
    qr_label.setPixmap(photo)
    layout.addWidget(qr_label)

    entry_url = QLineEdit(url)
    entry_url.setReadOnly(True)
    layout.addWidget(entry_url)

    def copiar_url() -> None:
        QApplication.clipboard().setText(url)
        _qt_message_box(
            parent,
            QMessageBox.Information,
            "Copiado",
            "URL remota copiada para a area de transferencia.",
        )

    btn = QPushButton("Copiar URL")
    btn.clicked.connect(copiar_url)
    layout.addWidget(btn)

    aviso_host = QLabel(
        "Se nao abrir no celular, defina ALTAIR_QR_HOST com o IP do PC na rede Wi-Fi. "
        "Para acesso externo a sua rede, configure ALTAIR_REMOTE_PUBLIC_URL."
    )
    aviso_host.setWordWrap(True)
    layout.addWidget(aviso_host)

    win.exec_()


def abrir_interface_llm_config(parent: QWidget) -> None:
    from PyQt5.QtWidgets import (
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMessageBox,
        QPushButton,
        QVBoxLayout,
    )

    cfg_atual = carregar_config_llm()
    win = QDialog(parent)
    win.setWindowTitle("Configurar API e Modelos")
    win.resize(560, 400)

    layout = QVBoxLayout(win)
    form = QFormLayout()
    layout.addLayout(form)

    prov_var = QComboBox(win)
    prov_var.addItems(["groq", "openai", "local", "custom"])
    prov_var.setCurrentText(cfg_atual["provider"])
    form.addRow("Provedor", prov_var)

    entry_key = QLineEdit(cfg_atual.get("api_key", ""))
    entry_key.setEchoMode(QLineEdit.Password)
    key_row = QHBoxLayout()
    key_row.addWidget(entry_key)
    btn_groq_key = QPushButton("Link para criar sua API")
    btn_groq_key.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://console.groq.com/keys")))
    key_row.addWidget(btn_groq_key)
    form.addRow("API Key", key_row)

    entry_base = QLineEdit(cfg_atual.get("base_url", ""))
    form.addRow("Base URL (custom/local)", entry_base)

    entry_main = QLineEdit(cfg_atual.get("model_main", ""))
    form.addRow("Modelo principal (respostas)", entry_main)

    entry_router = QLineEdit(cfg_atual.get("model_router", ""))
    form.addRow("Modelo menor (interpretar comandos)", entry_router)

    aviso = QLabel(
        "Se o modelo menor ficar vazio, o principal sera usado automaticamente."
    )
    aviso.setStyleSheet("color: #6a6a6a;")
    layout.addWidget(aviso)

    def atualizar_base_url(*_args) -> None:
        prov = prov_var.currentText().strip().lower()
        if prov in {"groq", "openai"}:
            entry_base.setText(PROVEDORES_LLM[prov])
            entry_base.setReadOnly(True)
        else:
            entry_base.setReadOnly(False)
            if prov == "local" and not entry_base.text().strip():
                entry_base.setText(PROVEDORES_LLM["local"])

    prov_var.currentTextChanged.connect(lambda _text: atualizar_base_url())
    atualizar_base_url()

    buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
    layout.addWidget(buttons)

    def salvar_llm() -> None:
        prov = prov_var.currentText().strip().lower()
        api_key = entry_key.text().strip()
        base_url = entry_base.text().strip()
        model_main = entry_main.text().strip()
        model_router = entry_router.text().strip()

        if prov not in {"groq", "openai", "local", "custom"}:
            _qt_message_box(win, QMessageBox.Critical, "Erro", "Provedor invalido.")
            return
        if not model_main:
            _qt_message_box(
                win, QMessageBox.Critical, "Erro", "Informe o modelo principal."
            )
            return
        if prov in {"custom", "local"} and not base_url:
            _qt_message_box(
                win,
                QMessageBox.Critical,
                "Erro",
                "Informe a Base URL para provedor custom/local.",
            )
            return
        if not model_router:
            model_router = model_main

        cfg_novo = {
            "provider": prov,
            "api_key": api_key,
            "base_url": (
                base_url if prov in {"custom", "local"} else PROVEDORES_LLM[prov]
            ),
            "model_main": model_main,
            "model_router": model_router,
        }
        salvar_config_llm(cfg_novo)
        aplicar_config_llm(cfg_novo)
        if ui:
            ui.set_ia_status("IA: API/modelos atualizados")
            QTimer.singleShot(1800, lambda: ui.set_ia_status("IA: Pronta"))
        _qt_message_box(
            win,
            QMessageBox.Information,
            "Sucesso",
            "Configuracao aplicada com sucesso.",
        )
        win.accept()

    buttons.accepted.connect(salvar_llm)
    buttons.rejected.connect(win.reject)
    win.exec_()


def abrir_interface_voz_config(parent: QWidget) -> None:
    from PyQt5.QtWidgets import (
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFileDialog,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMessageBox,
        QPushButton,
        QVBoxLayout,
    )

    cfg_atual = carregar_config_voz()
    win = QDialog(parent)
    win.setWindowTitle("Configurar Voz")
    win.resize(620, 520)

    layout = QVBoxLayout(win)
    form = QFormLayout()
    layout.addLayout(form)

    prov_var = QComboBox(win)
    prov_var.addItems(["elevenlabs"])
    prov_var.setCurrentText("elevenlabs")
    form.addRow("Provedor de voz", prov_var)

    eleven_key = QLineEdit(cfg_atual.get("eleven_api_key", ""))
    eleven_key.setEchoMode(QLineEdit.Password)
    eleven_voice = QLineEdit(cfg_atual.get("eleven_voice_id", ""))
    eleven_model = QLineEdit(cfg_atual.get("eleven_model_id", "eleven_multilingual_v2"))
    eleven_key_row = QHBoxLayout()
    eleven_key_row.addWidget(eleven_key)
    btn_eleven_key = QPushButton("Link para criar sua API")
    btn_eleven_key.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://elevenlabs.io/app/sign-in?redirect=%2Fapp%2Fdevelopers%2Fapi-keys")))
    eleven_key_row.addWidget(btn_eleven_key)
    form.addRow("ElevenLabs API Key", eleven_key_row)
    form.addRow("ElevenLabs Voice ID", eleven_voice)
    form.addRow("ElevenLabs Model ID", eleven_model)

    stt_url = QLineEdit(cfg_atual.get("stt_remote_url", "https://api.elevenlabs.io/v1/speech-to-text"))
    stt_key = QLineEdit(cfg_atual.get("stt_remote_api_key", cfg_atual.get("eleven_api_key", "")))
    stt_key.setEchoMode(QLineEdit.Password)
    stt_model = QLineEdit(cfg_atual.get("stt_remote_model", "scribe_v1"))
    stt_lang = QLineEdit(cfg_atual.get("stt_remote_language", "pt"))
    stt_timeout = QLineEdit(cfg_atual.get("stt_remote_timeout", "60"))
    form.addRow("STT remoto - URL", stt_url)
    form.addRow("STT remoto - API Key", stt_key)
    form.addRow("STT remoto - Modelo", stt_model)
    form.addRow("STT remoto - Idioma", stt_lang)
    form.addRow("STT remoto - Timeout", stt_timeout)

    aviso = QLabel(
        "Troca aplicada na hora. Para ElevenLabs, informe API Key e Voice ID. "
        "Para transcricao da fala do usuario, use a mesma chave do ElevenLabs ou configure "
        "um endpoint remoto diferente."
    )
    aviso.setWordWrap(True)
    layout.addWidget(aviso)

    buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
    layout.addWidget(buttons)

    def salvar_voz() -> None:
        prov = prov_var.currentText().strip().lower()
        cfg_novo = {
            "provider": "elevenlabs",
            "assistant_name": cfg_atual.get("assistant_name", "Altair"),
            "piper_model": "",
            "piper_length_scale": "1.08",
            "piper_noise_scale": "0.38",
            "piper_noise_w": "0.52",
            "piper_modo_pro": "1",
            "eleven_api_key": eleven_key.text().strip(),
            "eleven_voice_id": eleven_voice.text().strip(),
            "eleven_model_id": eleven_model.text().strip() or "eleven_multilingual_v2",
            "stt_remote_url": stt_url.text().strip() or "https://api.elevenlabs.io/v1/speech-to-text",
            "stt_remote_api_key": stt_key.text().strip() or eleven_key.text().strip(),
            "stt_remote_model": stt_model.text().strip() or "scribe_v1",
            "stt_remote_language": stt_lang.text().strip() or "pt",
            "stt_remote_timeout": stt_timeout.text().strip() or "60",
        }

        if prov != "elevenlabs":
            _qt_message_box(
                win, QMessageBox.Critical, "Erro", "Provedor de voz invalido."
            )
            return
        if not cfg_novo["eleven_api_key"]:
            _qt_message_box(
                win,
                QMessageBox.Critical,
                "Erro",
                "Informe a API Key do ElevenLabs.",
            )
            return
        if not cfg_novo["eleven_voice_id"]:
            _qt_message_box(
                win,
                QMessageBox.Critical,
                "Erro",
                "Informe o Voice ID do ElevenLabs.",
            )
            return

        salvar_config_voz(cfg_novo)
        aplicar_config_voz(cfg_novo)
        if ui:
            ui.set_ia_status("IA: Voz atualizada")
            QTimer.singleShot(1800, lambda: ui.set_ia_status("IA: Pronta"))
        _qt_message_box(
            win, QMessageBox.Information, "Sucesso", "Configuracao de voz aplicada."
        )
        win.accept()

    buttons.accepted.connect(salvar_voz)
    buttons.rejected.connect(win.reject)
    win.exec_()


def abrir_interface_cadastro(parent: QWidget) -> None:
    from PyQt5.QtWidgets import (
        QDialog,
        QFileDialog,
        QLabel,
        QLineEdit,
        QMessageBox,
        QPushButton,
        QVBoxLayout,
    )

    win = QDialog(parent)
    win.setWindowTitle("Cadastro de Aplicativos ALTAIR")
    win.resize(400, 250)

    layout = QVBoxLayout(win)
    layout.addWidget(QLabel("Nome do aplicativo:"))
    entry_nome = QLineEdit()
    layout.addWidget(entry_nome)
    label_status = QLabel(f"{len(APLICATIVOS_CONHECIDOS)} apps cadastrados")
    layout.addWidget(label_status)

    def adicionar_app() -> None:
        caminho, _ = QFileDialog.getOpenFileName(
            win, "Escolha o executavel do app", filter="Executaveis (*.exe)"
        )
        if not caminho:
            return
        nome = entry_nome.text().strip().lower()
        if not nome:
            _qt_message_box(
                win, QMessageBox.Critical, "Erro", "Digite um nome para o aplicativo"
            )
            return
        APLICATIVOS_CONHECIDOS[nome] = caminho
        salvar_apps()
        _qt_message_box(
            win, QMessageBox.Information, "Sucesso", f"Aplicativo '{nome}' adicionado!"
        )
        entry_nome.clear()
        label_status.setText(f"{len(APLICATIVOS_CONHECIDOS)} apps cadastrados")

    btn = QPushButton("Escolher executavel e adicionar")
    btn.clicked.connect(adicionar_app)
    layout.addWidget(btn)
    win.exec_()


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
cfg_voz_inicial = carregar_config_voz()
configurar_stt_remoto(cfg_voz_inicial)
configurar_nome_assistente(cfg_voz_inicial.get("assistant_name", "Altair"))
voz = criar_voz_por_config(cfg_voz_inicial)
cfg_llm_inicial = carregar_config_llm()
llm_groq = criar_llm_por_config(cfg_llm_inicial)
if not llm_groq.disponivel():
    print("AVISO: API key nao configurada. O fallback local continuara ativo.")

ia = IALocal(voz, llm_groq)
command_service = CommandService(
    ia=ia,
    voz=voz,
    resolver_intencao_comando=resolver_intencao_comando,
    executar_intencao=executar_intencao,
    montar_contexto_intencoes=montar_contexto_intencoes,
)

ui = DesktopUI(
    process_command=processar_comando_ui,
    speak_text=voz.speak,
    on_audio_start=iniciar_audio,
    on_file_selected=atualizar_arquivo_selecionado,
    app_title=f"{cfg_voz_inicial.get('assistant_name', 'Altair')} v{ALTAIR_VERSION}",
    assistant_name=cfg_voz_inicial.get("assistant_name", "Altair"),
    on_assistant_name_changed=salvar_nome_assistente,
    stop_speech=voz.stop,
    on_toggle_startup=(
        None if os.getenv("ALTAIR_STORE_PACKAGE") == "1" else _alternar_startup_windows
    ),
    on_open_apps_register=abrir_interface_cadastro,
    on_open_remote_connect=abrir_interface_conexao_remota,
    on_open_llm_config=abrir_interface_llm_config,
    on_open_voice_config=abrir_interface_voz_config,
)

if FASTAPI_DISPONIVEL:
    api_server_thread = threading.Thread(target=api_server.run, daemon=True)
    api_server_thread.start()
    if _is_loopback_host(API_HOST):
        print(f"API local iniciada em http://{API_HOST}:{API_PORT} (autenticacao ativa)")
    else:
        print(f"API remota TLS iniciada em https://{API_HOST}:{API_PORT} (autenticacao ativa)")
else:
    print("FastAPI/uvicorn nao encontrados. API remota desativada.")

welcome_text = ia.responder("saudacao")
ui.adicionar_mensagem(welcome_text, "ia")
voz.speak(welcome_text)

ui.run()
