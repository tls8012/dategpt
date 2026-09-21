from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping


_LEVELS = {"low", "medium", "high"}


def _as_bool(value: Any, name: str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().casefold()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    raise ValueError("{} must be boolean".format(name))


@dataclass
class ControlState:
    """Small engine-owned controls repeated in every LLM turn context."""

    language: str = "한국어"
    initiative: str = "medium"
    world_consistency: str = "medium"
    dev_commands: bool = False
    paused: bool = False
    extra: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "ControlState":
        state = cls()
        for name, value in values.items():
            state.set(name, value)
        return state

    def set(self, name: str, value: Any) -> None:
        if name == "language":
            text = str(value).strip()
            if not text:
                raise ValueError("language must not be empty")
            self.language = text
            return

        if name in {"initiative", "world_consistency"}:
            level = str(value).strip().casefold()
            if level not in _LEVELS:
                raise ValueError("{} must be low, medium, or high".format(name))
            setattr(self, name, level)
            return

        if name in {"paused", "dev_commands"}:
            setattr(self, name, _as_bool(value, name))
            return

        self.extra[name] = str(value).strip()

    def snapshot(self) -> Dict[str, Any]:
        values = {
            "language": self.language,
            "initiative": self.initiative,
            "world_consistency": self.world_consistency,
            "dev_commands": self.dev_commands,
            "paused": self.paused,
        }
        values.update(self.extra)
        return values
