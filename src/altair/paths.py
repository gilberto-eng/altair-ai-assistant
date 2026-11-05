from pathlib import Path

import os
import sys


def _resource_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)).resolve()
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = _resource_root()
SRC_DIR = PROJECT_ROOT / "src"
CORE_DIR = SRC_DIR / "altair" / "core"
_windows_user_data = Path(
    os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")
) / "Altair"
_default_user_data = _windows_user_data if getattr(sys, "frozen", False) else PROJECT_ROOT
APP_DATA_ROOT = Path(os.environ.get("ALTAIR_USER_DATA_DIR", _default_user_data))
DATA_DIR = Path(os.environ.get("ALTAIR_DATA_DIR", APP_DATA_ROOT / "data"))
CONFIG_DIR = Path(os.environ.get("ALTAIR_CONFIG_DIR", APP_DATA_ROOT / "configs"))
CONFIG_JSON_DIR = DATA_DIR / "json"
ASSETS_DIR = PROJECT_ROOT / "assets"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
WHATSAPP_DIR = SCRIPTS_DIR / "whatsapp"

for _directory in (DATA_DIR, CONFIG_DIR, CONFIG_JSON_DIR):
    _directory.mkdir(parents=True, exist_ok=True)
