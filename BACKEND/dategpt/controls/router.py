from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

from .state import ControlState


@dataclass(frozen=True)
class ControlResponse:
    handled: bool
    message: str = ""
    controls: Optional[Dict[str, Any]] = None


class ControlRouter:
    """Handles deterministic engine controls before an LLM call.

    Text commands are only a compatibility adapter for the current Ren'Py UI.
    The canonical interface is structured set_control / get_controls messages,
    so later buttons can bypass command parsing entirely.
    """

    def __init__(
        self,
        state: ControlState,
        *,
        aliases: Optional[Mapping[str, str]] = None,
        help_text: Optional[str] = None,
        on_change=None,
    ) -> None:
        self.state = state
        self.aliases = {
            "!언어": "language",
            "!language": "language",
            "!initiative": "initiative",
            "!world_consistency": "world_consistency",
            "!중단": "paused:true",
            "!재개": "paused:false",
        }
        if aliases:
            self.aliases.update(dict(aliases))
        self.help_text = help_text
        self.on_change = on_change

    def try_handle_message(self, message: Mapping[str, Any]) -> ControlResponse:
        message_type = message.get("type")

        if message_type == "get_controls":
            return self._ok("현재 설정입니다.")

        if message_type == "set_control":
            name = str(message.get("name", "")).strip()
            if not name:
                return ControlResponse(True, "설정 이름이 비어 있습니다.", self.state.snapshot())
            try:
                self._set(name, message.get("value"))
            except ValueError as exc:
                return ControlResponse(True, str(exc), self.state.snapshot())
            return self._ok("{} 설정을 변경했습니다.".format(name))

        if message_type == "help":
            return self._ok(self.render_help())

        if message_type == "say":
            return self.try_handle_text(str(message.get("text", "")))

        return ControlResponse(False)

    def try_handle_text(self, text: str) -> ControlResponse:
        stripped = text.strip()
        if not stripped:
            return ControlResponse(False)

        if stripped == "!도움말":
            return self._ok(self.render_help())

        command, separator, argument = stripped.partition(" ")
        target = self.aliases.get(command)
        if target is None:
            return ControlResponse(False)

        if target.startswith("paused:"):
            self._set("paused", target.split(":", 1)[1])
            return self._ok("중단 상태를 변경했습니다.")

        argument = argument.strip()
        if not separator or not argument:
            current = self.state.snapshot().get(target)
            return self._ok("{}: {}".format(target, current))

        try:
            self._set(target, argument)
        except ValueError as exc:
            return ControlResponse(True, str(exc), self.state.snapshot())

        return self._ok("{}: {}".format(target, self.state.snapshot().get(target)))

    def render_help(self) -> str:
        if self.help_text:
            return self.help_text

        return (
            "엔진에서 즉시 처리되는 설정:\n"
            "- !언어 <언어>\n"
            "- !initiative <low|medium|high>\n"
            "- !world_consistency <low|medium|high>\n"
            "- !중단 / !재개\n"
            "- !도움말\n"
            "이 명령들은 LLM을 호출하지 않습니다."
        )

    def _set(self, name: str, value: Any) -> None:
        self.state.set(name, value)
        if self.on_change is not None:
            self.on_change(self.state.snapshot())

    def _ok(self, message: str) -> ControlResponse:
        return ControlResponse(True, message, self.state.snapshot())
