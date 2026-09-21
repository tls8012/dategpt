from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from ..bootstrap import InitializationResult, SessionInitializer
from ..host import RuntimeHost
from ..pointers import game_path, game_pointer
from ..scenarios import ScenarioPack


DRAFT_PATH = "onboarding/main_character.md"


class CharacterDraftMissing(RuntimeError):
    pass


@dataclass
class OnboardingState:
    phase: str = "not_started"
    player_character_mode: Optional[str] = None
    main_character: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "OnboardingState":
        return cls(
            phase=str(
                data.get("phase", "not_started")
            ),
            player_character_mode=data.get(
                "player_character_mode"
            ),
            main_character=data.get("main_character"),
        )


class OnboardingController:
    """Persistent deterministic state around LLM-assisted onboarding."""

    def __init__(
        self,
        *,
        initializer: SessionInitializer,
        initialization: InitializationResult,
        host: RuntimeHost,
        scenario: ScenarioPack,
    ) -> None:
        self.initializer = initializer
        self.initialization = initialization
        self.host = host
        self.scenario = scenario
        self.state_path = (
            initialization.workspace.runtime_root
            / "onboarding.json"
        )

        if not initialization.needs_setup:
            self.state = OnboardingState(
                phase="complete",
                player_character_mode=(
                    initialization.init_complete.player_character_mode
                    if initialization.init_complete
                    else None
                ),
                main_character=(
                    initialization.init_complete.main_character
                    if initialization.init_complete
                    else None
                ),
            )
        else:
            self.state = self._load()

    def start(self) -> OnboardingState:
        if self.state.phase == "not_started":
            self.state.phase = "mode_selection"
            self._save()
        return self.state

    def select_mode(
        self,
        mode: str,
        *,
        main_character: Optional[str] = None,
    ) -> OnboardingState:
        normalized = str(mode).strip().casefold()

        if normalized == "original":
            self.state = OnboardingState(
                phase="character_creation",
                player_character_mode="original",
                main_character="game:entities/main_character.md",
            )
            self._save()
            return self.state

        if normalized == "observer":
            self.state = OnboardingState(
                phase="ready_to_finalize",
                player_character_mode="none",
                main_character="none",
            )
            self._save()
            return self.state

        if normalized == "existing":
            path = game_path(main_character)
            if path is None or not path.startswith("entities/"):
                raise ValueError(
                    "existing mode requires an entities/... path"
                )
            if _is_hidden(path):
                raise ValueError(
                    "hidden content cannot be selected as player character"
                )
            if not self.scenario.exists(path):
                raise FileNotFoundError(path)

            self.state = OnboardingState(
                phase="ready_to_finalize",
                player_character_mode="existing",
                main_character=game_pointer(path),
            )
            self._save()
            return self.state

        raise ValueError(
            "onboarding mode must be original, existing, or observer"
        )

    def finalize(self):
        mode = self.state.player_character_mode
        if mode is None:
            raise ValueError(
                "select an onboarding mode before finalizing"
            )

        if mode == "original":
            if not self.initialization.workspace.scratchpad.exists(
                DRAFT_PATH
            ):
                raise CharacterDraftMissing(
                    "캐릭터 초안이 없습니다. "
                    "온보딩 대화에서 캐릭터를 먼저 확정해 주세요."
                )
            draft = (
                self.initialization.workspace.scratchpad.read_text(
                    DRAFT_PATH
                )
            )
            self.initialization.workspace.save.write_text(
                "entities/main_character.md",
                draft,
            )
            play_mode = "player"
            main_character = "game:entities/main_character.md"

        elif mode == "existing":
            play_mode = "player"
            main_character = str(
                self.state.main_character
            )

        elif mode == "none":
            play_mode = "observer"
            main_character = "none"

        else:
            raise ValueError(
                "invalid onboarding state"
            )

        init_complete = self.initializer.finalize_new_game(
            self.initialization,
            play_mode=play_mode,
            player_character_mode=mode,
            main_character=main_character,
            controls=self.host.controls,
        )
        self.host.set_init_complete(init_complete)

        self.mark_complete(init_complete)
        return init_complete

    def mark_complete(self, init_complete) -> None:
        self.state = OnboardingState(
            phase="complete",
            player_character_mode=(
                init_complete.player_character_mode
            ),
            main_character=init_complete.main_character,
        )
        self._save()

    def public_state(self) -> dict:
        data = asdict(self.state)
        data["has_character_draft"] = (
            self.initialization.workspace.scratchpad.exists(
                DRAFT_PATH
            )
        )
        return data

    def _load(self) -> OnboardingState:
        if not self.state_path.exists():
            return OnboardingState()

        data = json.loads(
            self.state_path.read_text(encoding="utf-8")
        )
        if not isinstance(data, dict):
            return OnboardingState()
        return OnboardingState.from_dict(data)

    def _save(self) -> None:
        self.state_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        temp = self.state_path.with_name(
            self.state_path.name + ".tmp"
        )
        temp.write_text(
            json.dumps(
                asdict(self.state),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        os.replace(temp, self.state_path)


def _is_hidden(path: str) -> bool:
    normalized = str(path).replace("\\", "/").lstrip("./")
    return (
        normalized == "hidden"
        or normalized.startswith("hidden/")
    )
