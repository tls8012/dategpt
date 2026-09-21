from __future__ import annotations

from typing import Dict


def parse_markdown_fields(text: str) -> Dict[str, str]:
    """Parse simple key/value fields used by manifests and compatible Saves.

    Accepted forms include both the legacy bulleted representation and the
    current cartridge build representation:

    - key: value
    - `GAME_NAME: example`
    GAME_NAME: example
    """

    values: Dict[str, str] = {}

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        payload = line
        if payload.startswith("- "):
            payload = payload[2:].strip()

        if (
            payload.startswith("`")
            and payload.endswith("`")
            and len(payload) >= 2
        ):
            payload = payload[1:-1].strip()

        if ":" not in payload:
            continue

        key, value = payload.split(":", 1)
        key = key.strip()
        if key:
            values[key] = value.strip()

    return values
