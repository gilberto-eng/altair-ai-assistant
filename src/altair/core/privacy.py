"""Persist and query the user's opt-in for sending content to external services."""

from __future__ import annotations

import json
import os
from pathlib import Path

from altair.paths import APP_DATA_ROOT

_PREFERENCES_FILE = APP_DATA_ROOT / "privacy_preferences.json"


def external_services_allowed() -> bool:
    override = os.environ.get("ALTAIR_EXTERNAL_SERVICES_ALLOWED")
    if override is not None:
        return override.strip().lower() in {"1", "true", "yes"}
    try:
        preferences = json.loads(_PREFERENCES_FILE.read_text(encoding="utf-8"))
        return preferences.get("external_services_allowed") is True
    except Exception:
        return False


def set_external_services_allowed(allowed: bool) -> None:
    _PREFERENCES_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PREFERENCES_FILE.write_text(
        json.dumps({"external_services_allowed": bool(allowed)}, indent=2),
        encoding="utf-8",
    )
    os.environ["ALTAIR_EXTERNAL_SERVICES_ALLOWED"] = "1" if allowed else "0"


def require_external_services_allowed(service: str) -> None:
    if not external_services_allowed():
        raise PermissionError(
            f"Envio para {service} esta desativado. Autorize em Menu > Privacidade e dados."
        )
