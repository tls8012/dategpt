from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Optional, Tuple


GAME_POINTER_PREFIX = "game:"
_GAME_ROOTS = {"entities", "story", "flags", "assets"}
_TEXT_POINTER_RE = re.compile(
    r"(?:(?:game:)?(?:entities|story|flags|assets)/"
    r"[^\\n,;|\\]\\)]+?\\.(?:md|json|txt))",
    re.IGNORECASE,
)


def game_path(value: object) -> Optional[str]:
    """Return an overlay-relative path from a runtime game pointer.

    Runtime pointers use the game: prefix so they are not mistaken for paths
    relative to init완료.md. Legacy bare paths remain readable.
    """

    text = str(value or "").strip().replace("\\\\", "/")
    if not text or text.casefold() in {"none", "null"}:
        return None

    if text.casefold().startswith(GAME_POINTER_PREFIX):
        text = text[len(GAME_POINTER_PREFIX):].strip()

    while text.startswith("./"):
        text = text[2:]

    if not text or text.startswith("/"):
        return None

    path = PurePosixPath(text)
    parts = path.parts
    if (
        not parts
        or parts[0].casefold() not in _GAME_ROOTS
        or any(part in {"", ".", ".."} for part in parts)
    ):
        return None

    return path.as_posix()


def game_pointer(value: object) -> str:
    path = game_path(value)
    if path is None:
        return str(value or "").strip()
    return GAME_POINTER_PREFIX + path


def canonicalize_game_pointers(value: object) -> str:
    text = str(value or "")
    if not text:
        return ""

    def replace(match) -> str:
        path = game_path(match.group(0))
        if path is None:
            return match.group(0)
        return GAME_POINTER_PREFIX + path

    return _TEXT_POINTER_RE.sub(replace, text)


def extract_game_paths(value: object) -> Tuple[str, ...]:
    if not isinstance(value, str) or not value:
        return ()

    paths = []
    seen = set()
    for match in _TEXT_POINTER_RE.finditer(value):
        path = game_path(match.group(0))
        if path is None or path in seen:
            continue
        seen.add(path)
        paths.append(path)
    return tuple(paths)
