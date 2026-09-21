from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from .stores import HistoryStore, SaveStore, ScratchpadStore


def _safe_segment(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("{} must be a non-empty string".format(label))
    if value in {".", ".."} or "/" in value or "\\" in value or "\x00" in value:
        raise ValueError("{} contains an unsafe path segment".format(label))
    return value


@dataclass
class SessionWorkspace:
    """Separates compatible game Saves from DateGPT-only runtime state."""

    game_name: str
    game_id: str
    save: SaveStore
    scratchpad: ScratchpadStore
    history: HistoryStore
    runtime_root: Path

    @classmethod
    def open(
        cls,
        *,
        save_base: Path,
        runtime_base: Path,
        game_name: str,
        game_id: str,
    ) -> "SessionWorkspace":
        safe_game_name = _safe_segment(game_name, "game_name")
        safe_game_id = _safe_segment(game_id, "game_id")

        # Save path intentionally matches the original:
        # games/GAME_NAME/GAME_ID/<init완료.md, entities/, story/, ...>
        save_root = Path(save_base).expanduser().resolve() / safe_game_name / safe_game_id

        # DateGPT implementation details live elsewhere and may be discarded
        # without invalidating the semantic Save.
        runtime_root = (
            Path(runtime_base).expanduser().resolve()
            / safe_game_name
            / safe_game_id
        )
        runtime_root.mkdir(parents=True, exist_ok=True)

        return cls(
            game_name=safe_game_name,
            game_id=safe_game_id,
            save=SaveStore(save_root),
            scratchpad=ScratchpadStore(runtime_root / "scratchpad"),
            history=HistoryStore(runtime_root / "history.jsonl"),
            runtime_root=runtime_root,
        )

    @property
    def controls_path(self) -> Path:
        return self.runtime_root / "controls.json"

    def load_controls(self) -> Dict[str, Any]:
        if not self.controls_path.exists():
            return {}
        data = json.loads(self.controls_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("controls.json must contain an object")
        return data

    def save_controls(self, controls: Dict[str, Any]) -> None:
        temp = self.controls_path.with_name(self.controls_path.name + ".tmp")
        temp.write_text(
            json.dumps(controls, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temp.replace(self.controls_path)
