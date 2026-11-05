from pathlib import Path
import tkinter as tk

import installer.altair_installer as installer
from installer.altair_installer import InstallerUI, _copy_payload, _write_launcher


def test_payload_inclui_requirements_para_instalacao_automatica(tmp_path):
    install_dir = tmp_path / "install"
    _copy_payload(install_dir)

    requirements = (install_dir / "requirements.txt").read_text(encoding="utf-8")
    assert "numpy" in requirements
    assert "faster-whisper" not in requirements
    assert all(package in requirements for package in ("sympy", "cadquery", "pynput"))
    assert not hasattr(installer, "FEATURES")


def test_copy_payload_instala_app_sem_sobrescrever_configuracoes(tmp_path):
    install_dir = tmp_path / "install"
    configs_dir = install_dir / "configs"
    json_dir = install_dir / "json"
    configs_dir.mkdir(parents=True)
    json_dir.mkdir(parents=True)
    (configs_dir / "user-token.txt").write_text("preservar", encoding="utf-8")
    (json_dir / "local.json").write_text("{}", encoding="utf-8")

    _copy_payload(install_dir)

    assert (install_dir / "src" / "altair" / "main.py").is_file()
    assert (configs_dir / "user-token.txt").read_text(encoding="utf-8") == "preservar"
    assert (json_dir / "local.json").read_text(encoding="utf-8") == "{}"
    assert (install_dir / "data").is_dir()


def test_launcher_usa_pythonw_e_nao_abre_console(tmp_path):
    _write_launcher(tmp_path)

    launcher = (tmp_path / "Altair.vbs").read_text(encoding="utf-8")
    assert "pythonw.exe" in launcher
    assert "shell.Run" in launcher
    assert not (tmp_path / "Altair.bat").exists()


def test_sucesso_mostra_apenas_botao_concluido_e_fecha():
    ui = InstallerUI()
    ui.withdraw()
    try:
        ui._set_progress(47, "Instalando componentes")
        assert ui.progress["value"] == 47
        assert ui.percent.get() == "47%"

        ui._finish_install(None)

        assert ui.percent.get() == "100%"
        assert not ui.install_button.winfo_manager()
        assert not ui.exit_button.winfo_manager()
        assert ui.done_button.winfo_manager() == "pack"
        ui.done_button.invoke()
        try:
            ui.winfo_exists()
        except tk.TclError:
            pass
        else:
            raise AssertionError("O botao Concluido nao fechou o instalador")
    finally:
        try:
            ui.destroy()
        except tk.TclError:
            pass


def test_cria_atalhos_no_desktop_e_menu_iniciar(tmp_path, monkeypatch):
    install_dir = tmp_path / "Altair"
    install_dir.mkdir()
    (tmp_path / "System32").mkdir()
    gerados = []

    def run_falso(cmd, cwd=None, env=None):
        gerados.append(Path(cmd[1]).read_text(encoding="utf-8"))
        return 0, ""

    monkeypatch.setenv("WINDIR", str(tmp_path))
    monkeypatch.setattr(installer, "_run", run_falso)

    installer._create_shortcuts(install_dir)

    assert len(gerados) == 1
    assert 'SpecialFolders("Desktop")' in gerados[0]
    assert 'SpecialFolders("Programs")' in gerados[0]
    assert "Altair.vbs" in gerados[0]