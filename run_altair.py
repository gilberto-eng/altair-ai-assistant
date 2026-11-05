import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", ROOT)).resolve()
ALT_DIR = RESOURCE_ROOT / "src" / "altair"
CORE_DIR = ALT_DIR / "core"
APP_DIR = ALT_DIR / "app"

for p in (str(ALT_DIR), str(CORE_DIR), str(APP_DIR), str(RESOURCE_ROOT / "src")):
    if p not in sys.path:
        sys.path.insert(0, p)

USER_ROOT = (
    Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Altair"
    if getattr(sys, "frozen", False)
    else ROOT
)
USER_ROOT = Path(os.environ.get("ALTAIR_USER_DATA_DIR", USER_ROOT))
DATA_ROOT = Path(os.environ.get("ALTAIR_DATA_DIR", USER_ROOT / "data"))
CONFIG_ROOT = Path(os.environ.get("ALTAIR_CONFIG_DIR", USER_ROOT / "configs"))
for directory in (DATA_ROOT, CONFIG_ROOT, DATA_ROOT / "json"):
    directory.mkdir(parents=True, exist_ok=True)

os.environ.setdefault("ALTAIR_USER_DATA_DIR", str(USER_ROOT))
os.environ.setdefault("ALTAIR_CONFIG_DIR", str(CONFIG_ROOT))
os.environ.setdefault("ALTAIR_WWEBJS_DIR", str(RESOURCE_ROOT / "scripts" / "whatsapp"))
os.environ.setdefault("ALTAIR_CHROME_PROFILE_DIR", str(DATA_ROOT / "chrome_profile"))
os.environ.setdefault("ALTAIR_DATA_DIR", str(DATA_ROOT))
node = RESOURCE_ROOT / "tools" / "node" / "node.exe"
if node.is_file():
    os.environ.setdefault("ALTAIR_NODE_PATH", str(node))
os.environ.setdefault("PUPPETEER_CACHE_DIR", str(RESOURCE_ROOT / "browser"))
if (RESOURCE_ROOT / "support.json").is_file():
    os.environ.setdefault("ALTAIR_STORE_PACKAGE", "1")

from altair.core.privacy import external_services_allowed

os.environ.setdefault(
    "ALTAIR_EXTERNAL_SERVICES_ALLOWED",
    "1" if external_services_allowed() else "0",
)

from altair import main  # noqa: E402, F401

