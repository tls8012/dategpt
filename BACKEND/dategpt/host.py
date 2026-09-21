from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple

from .bootstrap.models import InitComplete
from .context import ContextBuilder
from .controls import ControlResponse, ControlRouter, ControlState
from .prompts import PromptBundle, PromptSnapshot
from .scenarios import ScenarioPack
from .workspace import SessionWorkspace


@dataclass(frozen=True)
class TurnContext:
    user_input: str
    system_prompt: str
    controls: Dict[str, Any]
    prompt_fingerprint: str
    prompt_files: Tuple[str, ...]
    context_messages: Tuple[Dict[str, Any], ...]
    recent_history: Tuple[Dict[str, Any], ...]


class RuntimeHost:
    """Composition root and per-turn context assembler."""

    def __init__(
        self,
        *,
        prompt_bundle: Optional[PromptBundle] = None,
        scenario: Optional[ScenarioPack] = None,
        workspace: Optional[SessionWorkspace] = None,
        controls: Optional[ControlState] = None,
        init_complete: Optional[InitComplete] = None,
    ) -> None:
        self.prompt_bundle = prompt_bundle
        self.scenario = scenario
        self.workspace = workspace
        self.init_complete = init_complete

        if controls is None and workspace is not None:
            controls = ControlState.from_mapping(
                workspace.load_controls()
            )
        self.controls = controls or ControlState()

        self.context_builder = None
        if scenario is not None and workspace is not None:
            self.context_builder = ContextBuilder(
                scenario=scenario,
                workspace=workspace,
                init_complete=init_complete,
            )

        aliases = None
        help_text = None
        if prompt_bundle is not None:
            manifest = prompt_bundle.control_manifest()
            aliases = (
                manifest.get("aliases")
                if isinstance(
                    manifest.get("aliases"),
                    dict,
                )
                else None
            )
            help_value = manifest.get("help")
            help_text = (
                help_value
                if isinstance(help_value, str)
                else None
            )

        self.control_router = ControlRouter(
            self.controls,
            aliases=aliases,
            help_text=help_text,
            on_change=self._persist_controls,
        )

    def set_init_complete(
        self,
        init_complete: InitComplete,
    ) -> None:
        self.init_complete = init_complete
        if self.context_builder is not None:
            self.context_builder.set_init_complete(
                init_complete
            )

    def route_control(
        self,
        message: Dict[str, Any],
    ) -> ControlResponse:
        return self.control_router.try_handle_message(
            message
        )

    def begin_turn(
        self,
        user_input: str,
        *,
        history_limit: int = 20,
    ) -> TurnContext:
        self._require_prompt_and_context()

        material = self.context_builder.build_gameplay()
        snapshot: PromptSnapshot = (
            self.prompt_bundle.snapshot(
                controls=self.controls.snapshot(),
                stable_context=material.stable_context,
            )
        )

        return self._turn_context(
            user_input,
            snapshot=snapshot,
            context_messages=material.dynamic_messages,
            history_limit=history_limit,
        )

    def begin_onboarding_turn(
        self,
        user_input: str,
        *,
        welcome_text: Optional[str],
        onboarding_state: Mapping[str, object],
        history_limit: int = 20,
    ) -> TurnContext:
        self._require_prompt_and_context()

        material = self.context_builder.build_onboarding(
            welcome_text=welcome_text,
            onboarding_state=onboarding_state,
        )
        onboarding_prompt = (
            self.prompt_bundle.read_onboarding()
        )
        snapshot = self.prompt_bundle.snapshot(
            controls=self.controls.snapshot(),
            stable_context=material.stable_context,
            mode_prompt=onboarding_prompt,
            mode_prompt_name=(
                self.prompt_bundle.onboarding_name
            ),
        )

        return self._turn_context(
            user_input,
            snapshot=snapshot,
            context_messages=material.dynamic_messages,
            history_limit=history_limit,
        )

    def _turn_context(
        self,
        user_input: str,
        *,
        snapshot: PromptSnapshot,
        context_messages,
        history_limit: int,
    ) -> TurnContext:
        recent_history = ()
        if self.workspace is not None:
            recent_history = tuple(
                self.workspace.history.tail(
                    history_limit
                )
            )

        return TurnContext(
            user_input=user_input,
            system_prompt=snapshot.system_prompt,
            controls=snapshot.controls,
            prompt_fingerprint=(
                snapshot.fingerprint
            ),
            prompt_files=snapshot.source_files,
            context_messages=tuple(
                context_messages
            ),
            recent_history=recent_history,
        )

    def _require_prompt_and_context(self) -> None:
        if self.prompt_bundle is None:
            raise RuntimeError(
                "prompt bundle is not mounted"
            )
        if self.context_builder is None:
            raise RuntimeError(
                "scenario/workspace context is not mounted"
            )

    def _persist_controls(
        self,
        values: Dict[str, Any],
    ) -> None:
        if self.workspace is None:
            return

        self.workspace.save_controls(values)

        if self.init_complete is not None:
            self.init_complete.apply_control_values(
                values
            )
            self.workspace.save.write_text(
                "init완료.md",
                self.init_complete.render(),
            )
