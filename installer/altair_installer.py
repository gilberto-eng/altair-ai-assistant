from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable
import zipfile
import urllib.request
import threading




INSTALL_SUMMARY = "Chat e IA  |  Voz por API  |  Automacao  |  Matematica"
OFFLINE_BUNDLE_DIR = Path(__file__).resolve().parent / "offline_bundle"
OFFLINE_PYTHON_INSTALLER = OFFLINE_BUNDLE_DIR / "python" / "python-3.10.0-amd64.exe"
OFFLINE_WHEELS_DIR = OFFLINE_BUNDLE_DIR / "wheels"


def _run(
    cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None
) -> tuple[int, str]:
    p = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    out = (p.stdout or "") + ("\n" + p.stderr if p.stderr else "")
    return p.returncode, out.strip()


def _py() -> str:
    # Usa o python do proprio instalador (se for exe via PyInstaller, ainda funciona).
    return sys.executable


def _default_install_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "Altair"


def _copy_payload(dest: Path) -> None:
    """Instala o payload (codigo/recursos) na pasta de destino.

    - Distribuicao (.exe): extrai payload.zip embutido no executavel.
    - Dev (repo): copia pastas do projeto.
    """
    dest.mkdir(parents=True, exist_ok=True)

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        payload_zip = Path(str(meipass)) / "payload.zip"
        if not payload_zip.exists():
            raise RuntimeError("payload.zip nao encontrado dentro do instalador.")
        with zipfile.ZipFile(payload_zip, "r") as zf:
            zf.extractall(dest)
    else:
        here = Path(__file__).resolve().parents[1]
        run_altair = here / "run_altair.py"
        if not run_altair.exists():
            raise RuntimeError("run_altair.py nao encontrado. Rode o instalador a partir da pasta do projeto.")

        for name in ("src", "assets", "scripts", "data", "json", "tools"):
            src_path = here / name
            if not src_path.exists():
                continue
            dst_path = dest / name
            shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
        offline_bundle_src = here / "installer" / "offline_bundle"
        if offline_bundle_src.exists():
            shutil.copytree(offline_bundle_src, dest / "offline_bundle", dirs_exist_ok=True)
        shutil.copy2(run_altair, dest / "run_altair.py")
        run_macro = here / "run_macro.py"
        if run_macro.exists():
            shutil.copy2(run_macro, dest / "run_macro.py")
        for name in (
            "package.json",
            "package-lock.json",
            "macro.json",
            "Modelfile",
            ".env.example",
        ):
            src_path = here / name
            if src_path.exists():
                shutil.copy2(src_path, dest / name)
        requirements = here / "requirements.txt"
        if requirements.exists():
            shutil.copy2(requirements, dest / requirements.name)

    if not (dest / "src" / "altair" / "main.py").is_file():
        raise RuntimeError("Payload incompleto: src/altair/main.py nao foi instalado.")
    for name in ("configs", "json", "data"):
        (dest / name).mkdir(parents=True, exist_ok=True)
    if not (dest / "requirements.txt").is_file():
        raise RuntimeError("requirements.txt nao foi incluido no payload.")


def _possible_python_paths() -> list[Path]:
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    return [
        local / "Programs/Python/Python312/python.exe",
        local / "Programs/Python/Python311/python.exe",
        local / "Programs/Python/Python310/python.exe",
    ]


def _find_python() -> Path | None:
    for cmd in ("py", "python"):
        try:
            code, out = _run([cmd, "--version"])
            if code == 0 and "Python" in out:
                result = shutil.which(cmd)
                if result:
                    return Path(result)
        except Exception:
            pass

    for p in _possible_python_paths():
        if p.exists():
            return p

    return None

def _install_python(dest: Path) -> None:
    installer = dest / "python_installer.exe"

    url = "https://www.python.org/ftp/python/3.12.3/python-3.12.3-amd64.exe"

    urllib.request.urlretrieve(url, installer)

    code, out = _run([
        str(installer),
        "/quiet",
        "InstallAllUsers=0",
        "PrependPath=1",
        "Include_pip=1",
    ])

    if code != 0:
        raise RuntimeError(out or "Falha ao instalar Python")



def _find_local_python_bundle() -> Path | None:
    if OFFLINE_PYTHON_INSTALLER.is_file():
        return OFFLINE_PYTHON_INSTALLER
    return None


def _embedded_python(dest: Path) -> Path:
    py = _find_python()

    if py:
        return Path(py)

    offline_py = _find_local_python_bundle()
    if offline_py:
        local_installer = dest / "python_installer.exe"
        shutil.copy2(offline_py, local_installer)
        code, out = _run([
            str(local_installer),
            "/quiet",
            "InstallAllUsers=0",
            "PrependPath=0",
            "Include_pip=1",
            "TargetDir=C:\\Python310",
        ])
        if code == 0:
            py = Path(r"C:\Python310\python.exe")
            if py.exists():
                return py
        raise RuntimeError(out or "Python offline nao foi instalado corretamente.")

    _install_python(dest)

    py = _find_python()

    if not py:
        raise RuntimeError("Python nao foi instalado corretamente.")

    return Path(py)



def _ensure_pip(py: Path, dest: Path) -> None:
    code, _out = _run([str(py), "-m", "pip", "--version"])
    if code == 0:
        return
    get_pip = dest / "python" / "get-pip.py"
    if not get_pip.exists():
        raise RuntimeError("pip nao encontrado e get-pip.py nao esta no payload. Rebuild o payload.")
    code2, out2 = _run([str(py), str(get_pip)])
    if code2 != 0:
        raise RuntimeError(out2 or "Falha ao instalar pip no Python embutido")


def _write_launcher(dest: Path) -> None:
    launcher = dest / "Altair.vbs"
    root = str(dest.resolve()).replace('"', '""')
    launcher.write_text(
        'Set shell = CreateObject("WScript.Shell")\n'
        'Set fso = CreateObject("Scripting.FileSystemObject")\n'
        f'root = "{root}"\n'
        'shell.CurrentDirectory = root\n'
        'python = root & "\\.venv\\Scripts\\pythonw.exe"\n'
        'If Not fso.FileExists(python) Then python = root & "\\.venv\\Scripts\\python.exe"\n'
        'node = root & "\\tools\\node"\n'
        'If fso.FileExists(node & "\\node.exe") Then\n'
        '  Set env = shell.Environment("Process")\n'
        '  env("PATH") = node & ";" & env("PATH")\n'
        'End If\n'
        'script = root & "\\run_altair.py"\n'
        'shell.Run Chr(34) & python & Chr(34) & " " & Chr(34) & script & Chr(34), 0, False\n',
        encoding="utf-8",
    )


def _create_shortcuts(dest: Path, log=None) -> None:
    root = str(dest.resolve()).replace('"', '""')
    shortcut_script = dest / "_CreateAltairShortcut.vbs"
    icon_path = str((dest / "assets" / "altair_icon.ico").resolve()).replace('"', '""')
    shortcut_script.write_text(
        'Set shell = CreateObject("WScript.Shell")\n'
        'root = "' + root + '"\n'
        'iconPath = "' + icon_path + '"\n'
        'For Each folder In Array(shell.SpecialFolders("Programs"), shell.SpecialFolders("Desktop"))\n'
        '  Set shortcut = shell.CreateShortcut(folder & "\\Altair.lnk")\n'
        '  shortcut.TargetPath = shell.ExpandEnvironmentStrings("%SystemRoot%") & "\\System32\\wscript.exe"\n'
        '  shortcut.Arguments = Chr(34) & root & "\\Altair.vbs" & Chr(34)\n'
        '  shortcut.WorkingDirectory = root\n'
        '  shortcut.Description = "Altair Assistant"\n'
        '  If Len(iconPath) > 0 Then\n'
        '    shortcut.IconLocation = iconPath & ",0"\n'
        '  End If\n'
        '  shortcut.Save\n'
        'Next\n',
        encoding="utf-8",
    )
    wscript = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "wscript.exe"
    try:
        code, output = _run([str(wscript), str(shortcut_script)])
        if code != 0 and log:
            log(f"Aviso: nao foi possivel criar atalho no menu Iniciar: {output}")
    finally:
        shortcut_script.unlink(missing_ok=True)


def _create_venv(dest: Path) -> Path:
    venv_dir = dest / ".venv"
    if venv_dir.exists():
        return venv_dir
    py = _embedded_python(dest)
    _ensure_pip(py, dest)
    code, out = _run([str(py), "-m", "venv", str(venv_dir)])
    if code != 0:
        _run([str(py), "-m", "pip", "install", "--upgrade", "virtualenv"])
        code2, out2 = _run([str(py), "-m", "virtualenv", str(venv_dir)])
        if code2 != 0:
            raise RuntimeError(out2 or out or "Falha ao criar venv")
    return venv_dir


def _venv_python(venv_dir: Path) -> Path:
    return venv_dir / "Scripts" / "python.exe"




def _find_local_wheelhouse(dest: Path | None = None) -> Path | None:
    # In the standalone installer the bundle is extracted from payload.zip into
    # the installation directory, rather than sitting beside this module.
    if dest:
        installed_bundle = dest / "offline_bundle" / "wheels"
        if installed_bundle.is_dir():
            return installed_bundle
    if OFFLINE_WHEELS_DIR.is_dir():
        return OFFLINE_WHEELS_DIR
    for candidate in (
        Path(__file__).resolve().parent / "offline_bundle" / "wheels",
        Path(__file__).resolve().parent.parent / "installer" / "offline_bundle" / "wheels",
    ):
        if candidate.is_dir():
            return candidate
    return None


def _pip_install_requirements(
    venv_dir: Path,
    requirements_file: Path,
    log=None,
    progress: Callable[[int, str], None] | None = None,
) -> None:
    py = _venv_python(venv_dir)

    wheelhouse = _find_local_wheelhouse(venv_dir.parent)
    # The packaged installer is designed to work without network access. Avoid
    # contacting PyPI just to upgrade pip when its bundled wheels are available.
    if not wheelhouse:
        code, out = _run([
            str(py),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "pip"
        ])

        if code != 0:
            raise RuntimeError(out or "Falha ao atualizar pip")

    if log:
        log("Baixando e instalando todos os componentes do Altair...")

    command = [
        str(py),
        "-m",
        "pip",
        "install",
        "--progress-bar",
        "off",
        "-v",
    ]
    if wheelhouse and wheelhouse.exists():
        command += ["--no-index", "--find-links", str(wheelhouse)]
        if log:
            log(f"Usando cache offline em: {wheelhouse}")
    command += ["-r", str(requirements_file)]

    requirements = [
        line.strip()
        for line in requirements_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    total = max(1, len(requirements))
    process = subprocess.Popen(
        command,
        cwd=str(venv_dir.parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    output_tail: list[str] = []
    resolved = 0
    if process.stdout:
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            output_tail.append(line)
            if len(output_tail) > 30:
                output_tail.pop(0)
            if line.startswith(("Collecting ", "Using cached ", "Downloading ")):
                resolved += 1
                percent = min(74, 30 + int(44 * min(resolved, total) / total))
                if progress:
                    progress(percent, f"Baixando componentes Python ({min(resolved, total)}/{total})")
                if log and line.startswith("Collecting "):
                    log(line)

    code = process.wait()
    if code != 0:
        raise RuntimeError("Falha ao instalar dependencias Python:\n" + "\n".join(output_tail))
    if progress:
        progress(76, "Componentes Python instalados")




def _install_node_dependencies(
    dest: Path,
    log=None,
    progress: Callable[[int, str], None] | None = None,
) -> None:
    if not (dest / "package.json").is_file():
        if progress:
            progress(94, "Componentes Node não necessários")
        return

    node_dir = dest / "tools" / "node"
    node_exe = node_dir / "node.exe"
    npm_cli = node_dir / "node_modules" / "npm" / "bin" / "npm-cli.js"
    if not node_exe.is_file() or not npm_cli.is_file():
        if progress:
            progress(78, "Baixando Node.js portátil")
        if log:
            log("Baixando Node.js LTS para instalar a integracao WhatsApp...")
        with urllib.request.urlopen("https://nodejs.org/dist/index.json", timeout=30) as response:
            releases = json.load(response)
        release = next(
            (
                item
                for item in releases
                if item.get("lts") and "win-x64-zip" in item.get("files", [])
            ),
            None,
        )
        if not release:
            raise RuntimeError("Nao foi possivel encontrar uma versao LTS do Node.js para Windows x64.")

        version = release["version"]
        archive = dest / "tools" / f"node-{version}-win-x64.zip"
        node_dir.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(
            f"https://nodejs.org/dist/{version}/node-{version}-win-x64.zip",
            archive,
        )
        with zipfile.ZipFile(archive, "r") as node_zip:
            roots = {entry.filename.split("/", 1)[0] for entry in node_zip.infolist() if entry.filename}
            node_zip.extractall(node_dir.parent)
        archive.unlink(missing_ok=True)
        extracted = node_dir.parent / next(iter(roots))
        if node_dir.exists():
            shutil.rmtree(node_dir)
        extracted.rename(node_dir)

    if not node_exe.is_file() or not npm_cli.is_file():
        raise RuntimeError("A distribuicao portatil do Node.js ficou incompleta.")

    if log:
        log("Instalando dependencias Node.js do WhatsApp...")
    if progress:
        progress(84, "Instalando componentes do WhatsApp")
    env = os.environ.copy()
    env["PATH"] = str(node_dir) + os.pathsep + env.get("PATH", "")
    code, out = _run(
        [str(node_exe), str(npm_cli), "install", "--prefix", str(dest), "--omit=dev"],
        cwd=dest,
        env=env,
    )
    if code != 0:
        raise RuntimeError(out or "Falha ao instalar dependencias Node.js")
    if progress:
        progress(94, "Integração WhatsApp pronta")


class InstallerUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Altair | Instalador")
        self.geometry("700x620")
        self.resizable(False, False)
        self.configure(bg="#0b1410")
        self.install_dir = tk.StringVar(value=str(_default_install_dir()))
        self.install_button: ttk.Button | None = None
        self.exit_button: ttk.Button | None = None
        self.done_button: ttk.Button | None = None
        self.status = tk.StringVar(value="Pronto para instalar")
        self.percent = tk.StringVar(value="0%")
        self._configure_styles()
        self._build()

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("App.TFrame", background="#0b1410")
        style.configure("Panel.TFrame", background="#14231c")
        style.configure("Title.TLabel", background="#0b1410", foreground="#e8f3ec", font=("Segoe UI Semibold", 23))
        style.configure("Subtitle.TLabel", background="#0b1410", foreground="#9cb5a5", font=("Segoe UI", 10))
        style.configure("Section.TLabel", background="#0b1410", foreground="#b8cdbf", font=("Segoe UI Semibold", 9))
        style.configure("Panel.TLabel", background="#14231c", foreground="#e1eee5", font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background="#14231c", foreground="#9cb5a5", font=("Segoe UI", 9))
        style.configure("Status.TLabel", background="#0b1410", foreground="#9ddbb7", font=("Segoe UI Semibold", 9))
        style.configure("TEntry", fieldbackground="#101b15", foreground="#e8f3ec", bordercolor="#385844", insertcolor="#e8f3ec", padding=9)
        style.configure("TButton", background="#263a2d", foreground="#e8f3ec", bordercolor="#45654e", padding=(13, 9), font=("Segoe UI Semibold", 9))
        style.map("TButton", background=[("active", "#314d3a"), ("disabled", "#1a281f")], foreground=[("disabled", "#738579")])
        style.configure("Accent.TButton", background="#9bd7af", foreground="#102017", bordercolor="#b5e9c5", padding=(20, 10), font=("Segoe UI Semibold", 10))
        style.map("Accent.TButton", background=[("active", "#b3e8c2"), ("disabled", "#34473a")], foreground=[("disabled", "#91a397")])
        style.configure("Altair.Horizontal.TProgressbar", troughcolor="#18261e", background="#9bd7af", bordercolor="#263b2d", lightcolor="#9bd7af", darkcolor="#79b98d")

    def _build(self) -> None:
        root = ttk.Frame(self, style="App.TFrame", padding=(28, 24))
        root.pack(fill="both", expand=True)

        ttk.Label(root, text="ALTAIR", style="Title.TLabel").pack(anchor="w")
        ttk.Label(root, text="Instalador do assistente", style="Subtitle.TLabel").pack(anchor="w", pady=(2, 20))

        ttk.Label(root, text="LOCAL DE INSTALAÇÃO", style="Section.TLabel").pack(anchor="w", pady=(0, 7))
        path_panel = ttk.Frame(root, style="Panel.TFrame", padding=12)
        path_panel.pack(fill="x")
        path_row = ttk.Frame(path_panel, style="Panel.TFrame")
        path_row.pack(fill="x")
        ttk.Entry(path_row, textvariable=self.install_dir).pack(side="left", fill="x", expand=True)
        ttk.Button(path_row, text="Procurar", command=self._pick_dir).pack(side="left", padx=(9, 0))

        ttk.Label(root, text="INCLUÍDO", style="Section.TLabel").pack(anchor="w", pady=(19, 7))
        included = ttk.Frame(root, style="Panel.TFrame", padding=(14, 12))
        included.pack(fill="x")
        ttk.Label(included, text=INSTALL_SUMMARY, style="Panel.TLabel", wraplength=600).pack(anchor="w")
        ttk.Label(included, text="Todos os componentes serão instalados automaticamente.", style="Muted.TLabel").pack(anchor="w", pady=(5, 0))

        progress_row = ttk.Frame(root, style="App.TFrame")
        progress_row.pack(fill="x", pady=(19, 7))
        self.status_label = ttk.Label(progress_row, textvariable=self.status, style="Status.TLabel")
        self.status_label.pack(side="left", anchor="w")
        ttk.Label(progress_row, textvariable=self.percent, style="Status.TLabel").pack(side="right")
        self.progress = ttk.Progressbar(
            root,
            mode="determinate",
            maximum=100,
            value=0,
            style="Altair.Horizontal.TProgressbar",
        )
        self.progress.pack(fill="x")

        self.log = tk.Text(
            root,
            height=9,
            bg="#0f1913",
            fg="#c5d6ca",
            insertbackground="#e8f3ec",
            selectbackground="#41644b",
            relief="flat",
            borderwidth=0,
            font=("Consolas", 9),
            padx=12,
            pady=10,
            state="disabled",
        )
        self.log.pack(fill="both", expand=True, pady=(10, 18))
        self._log("Pronto. Clique em Instalar para configurar o Altair.")

        actions = ttk.Frame(root, style="App.TFrame")
        actions.pack(fill="x")
        self.exit_button = ttk.Button(actions, text="Sair", command=self.destroy)
        self.exit_button.pack(side="right", padx=(8, 0))
        self.done_button = ttk.Button(actions, text="Concluído", style="Accent.TButton", command=self.destroy)
        self.done_button.pack(side="right")
        self.done_button.pack_forget()
        self.install_button = ttk.Button(actions, text="Instalar Altair", style="Accent.TButton", command=self._start_install)
        self.install_button.pack(side="right")

    def _log(self, msg: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", msg.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")
        self.update_idletasks()

    def _queue_log(self, msg: str) -> None:
        self.after(0, self._log, msg)

    def _queue_status(self, msg: str) -> None:
        self.after(0, self.status.set, msg)

    def _set_progress(self, value: int, status: str | None = None) -> None:
        value = max(0, min(100, int(value)))
        self.progress.configure(value=value)
        self.percent.set(f"{value}%")
        if status:
            self.status.set(status)

    def _queue_progress(self, value: int, status: str | None = None) -> None:
        self.after(0, self._set_progress, value, status)

    def _pick_dir(self) -> None:
        d = filedialog.askdirectory(initialdir=self.install_dir.get(), title="Escolha o diretorio de instalacao")
        if d:
            self.install_dir.set(d)

    def _start_install(self) -> None:
        dest = Path(self.install_dir.get()).expanduser()
        if not str(dest).strip():
            messagebox.showerror("Altair", "Escolha uma pasta para instalar o Altair.")
            return

        self._queue_progress(1, "Preparando instalação…")
        if self.install_button:
            self.install_button.configure(state="disabled")
        threading.Thread(
            target=self._install_worker,
            args=(dest,),
            daemon=True,
        ).start()

    def _install_worker(self, dest: Path) -> None:
        error = None
        try:
            self._queue_log(f"Instalando em: {dest}")
            self._queue_log("Copiando arquivos...")
            self._queue_progress(5, "Copiando arquivos do Altair…")
            _copy_payload(dest)

            self._queue_progress(16, "Preparando ambiente Python…")
            self._queue_log("Criando ambiente Python...")
            venv_dir = _create_venv(dest)

            self._queue_progress(28, "Instalando componentes Python…")
            self._queue_log("Instalando componentes Python de requirements.txt...")
            _pip_install_requirements(
                venv_dir,
                dest / "requirements.txt",
                self._queue_log,
                self._queue_progress,
            )

            _install_node_dependencies(dest, self._queue_log, self._queue_progress)

            self._queue_progress(96, "Finalizando instalação…")
            self._queue_log("Criando inicializador sem console...")
            _write_launcher(dest)
            _create_shortcuts(dest, self._queue_log)

            self._queue_log("Instalação concluída.")
            self._queue_progress(100, "Instalação concluída.")
        except Exception as exc:
            error = str(exc)
            self._queue_log("Falha: " + error)
        self.after(0, self._finish_install, error)

    def _finish_install(self, error: str | None) -> None:
        if error:
            self._set_progress(int(self.progress["value"]), "A instalação não foi concluída")
            if self.install_button:
                self.install_button.configure(state="normal")
            self.status.set("A instalação não foi concluída")
            messagebox.showerror("Altair", error)
        else:
            self._set_progress(100, "Instalação concluída.")
            self.status.set("Altair está instalado")
            if self.install_button:
                self.install_button.pack_forget()
            if self.exit_button:
                self.exit_button.pack_forget()
            if self.done_button:
                self.done_button.pack(side="right")


def main() -> int:
    app = InstallerUI()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

