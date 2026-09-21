from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping


_LEVELS = {"low", "medium", "high"}


@dataclass
class ControlState:
    """Small engine-owned controls repeated in every LLM turn context."""

    language: str = "한국어"
    initiative: str = "medium"
    world_consistency: str = "medium"
    paused: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)

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

        if name == "paused":
            if isinstance(value, bool):
                self.paused = value
                return
            normalized = str(value).strip().casefold()
            if normalized in {"true", "1", "yes", "on"}:
                self.paused = True
                return
            if normalized in {"false", "0", "no", "off"}:
                self.paused = False
                return
            raise ValueError("paused must be boolean")

        # Future prompt bundles may introduce controls without forcing an
        # engine release. The structured control API can carry them immediately
        # and the snapshot will expose them to the LLM every turn.
        self.extra[name] = value

    def snapshot(self) -> Dict[str, Any]:
        values = {
            "language": self.language,
            "initiative": self.initiative,
            "world_consistency": self.world_consistency,
            "paused": self.paused,
        }
        values.update(self.extra)
        return values
