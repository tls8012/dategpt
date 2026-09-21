from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from .controls import ControlResponse, ControlRouter, ControlState
from .prompts import PromptBundle, PromptSnapshot
from .scenarios import ScenarioPack
from .workspace import SessionWorkspace


@dataclass(frozen=True)
class TurnContext:
    """One immutable player-turn context handed to the future agent runner."""

    user_input: str
    system_prompt: str
    controls: Dict[str, Any]
    prompt_fingerprint: str
    prompt_files: Tuple[str, ...]
    scratchpad: Dict[str, str]
    recent_history: Tuple[Dict[str, Any], ...]


class RuntimeHost:
    """Composition root for one mounted scenario/session.

    LangChain is intentionally not imported here. A future AgentRunner can take
    TurnContext plus the mounted scenario/workspace tools. This keeps state and
    file compatibility independent from the chosen agent framework.
    """

    def __init__(
        self,
        *,
        prompt_bundle: Optional[PromptBundle] = None,
        scenario: Optional[ScenarioPack] = None,
        workspace: Optional[SessionWorkspace] = None,
        controls: Optional[ControlState] = None,
    ) -> None:
        self.prompt_bundle = prompt_bundle
        self.scenario = scenario
        self.workspace = workspace

        if controls is None and workspace is not None:
            controls = ControlState.from_mapping(workspace.load_controls())
        self.controls = controls or ControlState()

        aliases = None
        help_text = None
        if prompt_bundle is not None:
            manifest = prompt_bundle.control_manifest()
            aliases = manifest.get("aliases") if isinstance(manifest.get("aliases"), dict) else None
            help_value = manifest.get("help")
            help_text = help_value if isinstance(help_value, str) else None

        self.control_router = ControlRouter(
            self.controls,
            aliases=aliases,
            help_text=help_text,
            on_change=self._persist_controls,
        )

    def route_control(self, message: Dict[str, Any]) -> ControlResponse:
        return self.control_router.try_handle_message(message)

    def begin_turn(
        self,
        user_input: str,
        *,
        include_init: bool = False,
        history_limit: int = 20,
    ) -> TurnContext:
        if self.prompt_bundle is None:
            raise RuntimeError("prompt bundle is not mounted")

        snapshot: PromptSnapshot = self.prompt_bundle.snapshot(
            controls=self.controls.snapshot(),
            include_init=include_init,
        )

        scratchpad = {}
        recent_history = ()
        if self.workspace is not None:
            scratchpad = self.workspace.scratchpad.snapshot()
            recent_history = tuple(self.workspace.history.tail(history_limit))

        return TurnContext(
            user_input=user_input,
            system_prompt=snapshot.system_prompt,
            controls=snapshot.controls,
            prompt_fingerprint=snapshot.fingerprint,
            prompt_files=snapshot.source_files,
            scratchpad=scratchpad,
            recent_history=recent_history,
        )

    def _persist_controls(self, values: Dict[str, Any]) -> None:
        if self.workspace is not None:
            self.workspace.save_controls(values)
