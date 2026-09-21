from __future__ import annotations

import unicodedata
from typing import Dict


def _normalize_field_key(value: str) -> str:
    key = unicodedata.normalize("NFC", str(value))
    key = key.replace("\ufeff", "")
    key = key.replace("\u200b", "")
    key = key.replace("\u200c", "")
    key = key.replace("\u200d", "")
    key = key.replace("\u2060", "")
    key = key.strip()

    for token in (
        "_", "-", ".", ":", "*", "`",
        "[", "]", "(", ")", "#", "+",
    ):
        key = key.replace("\\" + token, token)

    # Backslashes have no valid meaning in manifest/save field names.
    # Removing any leftovers recovers keys damaged by Windows/editor
    # copy-save round trips, e.g. game\\_id or game_\\id.
    key = key.replace("\\", "")

    return key


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
        key = _normalize_field_key(key)
        if (
            len(key) >= 4
            and key.startswith("**")
            and key.endswith("**")
        ):
            key = key[2:-2].strip()
        elif (
            len(key) >= 2
            and key.startswith("*")
            and key.endswith("*")
        ):
            key = key[1:-1].strip()
        elif (
            len(key) >= 2
            and key.startswith("_")
            and key.endswith("_")
        ):
            key = key[1:-1].strip()

        if key:
            values[key] = value.strip()

    return values
