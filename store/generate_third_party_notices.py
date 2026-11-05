from __future__ import annotations

import argparse
import os
from importlib import metadata
from pathlib import Path


LICENSE_NAMES = ("license", "licence", "copying", "notice", "copyright")


def _license_files(folder: Path) -> list[Path]:
    try:
        return sorted(
            path for path in folder.iterdir()
            if path.is_file() and path.name.lower().startswith(LICENSE_NAMES)
        )
    except OSError:
        return []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--node-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    sections: list[str] = [
        "Altair third-party notices",
        "This file contains license notices found in the Python build environment and bundled npm packages.",
    ]
    seen: set[tuple[str, str]] = set()

    for distribution in sorted(metadata.distributions(), key=lambda item: item.metadata.get("Name", "").lower()):
        name = distribution.metadata.get("Name", "unknown package")
        version = distribution.version
        license_name = distribution.metadata.get("License-Expression") or distribution.metadata.get("License") or "License not declared in package metadata"
        sections.append(f"\n\n===== Python: {name} {version} ({license_name}) =====")
        for item in distribution.files or ():
            filename = Path(str(item)).name.lower()
            if filename.startswith(LICENSE_NAMES):
                path = Path(distribution.locate_file(item))
                identity = (name.lower(), str(path))
                if identity in seen:
                    continue
                seen.add(identity)
                try:
                    sections.append(path.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    pass

    node_root = args.node_root
    for current, dirs, files in os.walk(node_root, followlinks=False):
        dirs[:] = [folder for folder in dirs if folder != ".bin"]
        folder = Path(current)
        if "package.json" not in files:
            continue
        try:
            import json
            info = json.loads((folder / "package.json").read_text(encoding="utf-8"))
            name = info.get("name", folder.name)
            version = info.get("version", "unknown")
            license_name = info.get("license", "License not declared in package metadata")
        except Exception:
            name, version, license_name = folder.name, "unknown", "License metadata unavailable"
        sections.append(f"\n\n===== npm: {name} {version} ({license_name}) =====")
        for path in _license_files(folder):
            identity = (str(name).lower(), str(path))
            if identity in seen:
                continue
            seen.add(identity)
            try:
                sections.append(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                pass

    args.output.write_text("\n".join(sections), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
