from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple

from ..controls import ControlState
from ..fs import RootedTextStore, safe_path_segment
from ..scenarios import ScenarioPack
from ..workspace import SessionWorkspace
from .markdown import parse_markdown_fields
from .models import InitComplete, ScenarioManifest


_SAVE_DIRS: Tuple[str, ...] = (
    "entities",
    "story",
    "flags",
    "hidden",
    "assets",
)


class GameInstanceSelectionRequired(RuntimeError):
    def __init__(self, game_ids: Sequence[str]) -> None:
        self.game_ids = tuple(game_ids)
        super().__init__(
            "multiple game instances exist; choose one: {}".format(
                ", ".join(self.game_ids)
            )
        )


class UnknownGameInstance(FileNotFoundError):
    pass


@dataclass
class InitializationResult:
    """Deterministic result of the original init.md bootstrap contract."""

    is_new: bool
    manifest: ScenarioManifest
    workspace: SessionWorkspace
    controls: ControlState
    init_complete: Optional[InitComplete]
    welcome_text: Optional[str]
    distribution_character_manifest: Optional[str]
    save_character_manifest: str

    @property
    def game_name(self) -> str:
        return self.manifest.game_name

    @property
    def game_id(self) -> str:
        return self.workspace.game_id

    @property
    def needs_setup(self) -> bool:
        return self.init_complete is None


class SessionInitializer:
    """Code implementation of the non-creative parts of init.md.

    This class intentionally hard-codes the stable save directory contract.
    It does not ask an LLM to discover folders, select a single unambiguous
    GAME_ID, restore controls, or load known indexes.
    """

    def __init__(self, *, save_base: Path, runtime_base: Path) -> None:
        self.save_base = Path(save_base).expanduser().resolve()
        self.runtime_base = Path(runtime_base).expanduser().resolve()
        self.save_base.mkdir(parents=True, exist_ok=True)
        self.runtime_base.mkdir(parents=True, exist_ok=True)
        self.registry = RootedTextStore(self.save_base, writable=True)

    def prepare(
        self,
        scenario: ScenarioPack,
        *,
        requested_game_id: Optional[str] = None,
        new_game: bool = False,
    ) -> InitializationResult:
        manifest = ScenarioManifest.parse(
            scenario.read_text("file-manifest.md")
        )
        game_name = safe_path_segment(manifest.game_name, "GAME_NAME")

        existing_ids = self._list_instance_ids(game_name)
        game_id, is_new = self._select_instance(
            existing_ids,
            requested_game_id=requested_game_id,
            new_game=new_game,
        )

        workspace = SessionWorkspace.open(
            save_base=self.save_base,
            runtime_base=self.runtime_base,
            game_name=game_name,
            game_id=game_id,
        )

        if is_new:
            self._create_save_skeleton(workspace)

        init_complete = None
        if workspace.save.exists("init완료.md"):
            init_path = workspace.save.resolve(
                "init완료.md"
            )
            init_text = workspace.save.read_text(
                "init완료.md"
            )
            try:
                init_complete = InitComplete.parse(
                    init_text
                )
            except ValueError as exc:
                parsed_keys = sorted(
                    parse_markdown_fields(
                        init_text
                    ).keys()
                )
                raise ValueError(
                    "{} [path={}, parsed_keys={}]".format(
                        exc,
                        init_path,
                        parsed_keys,
                    )
                ) from exc
            if init_complete.game_name != game_name:
                raise ValueError("init완료.md game_name does not match scenario")
            if init_complete.game_id != game_id:
                raise ValueError("init완료.md game_id does not match directory")

        controls = self._restore_controls(
            workspace,
            init_complete,
            manifest,
        )

        return InitializationResult(
            is_new=is_new,
            manifest=manifest,
            workspace=workspace,
            controls=controls,
            init_complete=init_complete,
            welcome_text=self._read_optional(scenario, "story/welcome.md"),
            distribution_character_manifest=self._read_optional(
                scenario,
                "character_manifest.md",
            ),
            save_character_manifest=(
                workspace.save.read_text("character_manifest.md")
                if workspace.save.exists("character_manifest.md")
                else ""
            ),
        )

    def finalize_new_game(
        self,
        result: InitializationResult,
        *,
        play_mode: str,
        player_character_mode: str,
        main_character: str,
        current: Optional[Dict[str, str]] = None,
        controls: Optional[ControlState] = None,
    ) -> InitComplete:
        """Write the original compatible init완료.md after mode setup."""

        self._validate_mode(
            play_mode,
            player_character_mode,
            main_character,
        )
        state = controls or result.controls
        for name, value in (
            result.manifest.control_defaults.items()
        ):
            state.extra.setdefault(name, value)

        extra_fields = dict(state.extra)

        current_state = dict(current or {})
        if (
            result.manifest.start_story
            and not current_state.get("active_story")
        ):
            current_state["active_story"] = (
                result.manifest.start_story
            )

        init_complete = InitComplete(
            game_name=result.game_name,
            game_id=result.game_id,
            play_mode=play_mode,
            player_character_mode=player_character_mode,
            main_character=main_character,
            world_consistency=state.world_consistency,
            initiative=state.initiative,
            language=state.language,
            dev_commands=state.dev_commands,
            paused=state.paused,
            current=current_state,
            extra_fields=extra_fields,
        )
        result.workspace.save.write_text(
            "init완료.md",
            init_complete.render(),
        )
        result.workspace.save_controls(state.snapshot())
        result.init_complete = init_complete
        result.controls = state
        return init_complete

    def list_instance_ids(self, game_name: str):
        """Return existing save instance ids without opening or creating one."""
        safe_game_name = safe_path_segment(game_name, "GAME_NAME")
        return tuple(self._list_instance_ids(safe_game_name))

    def _list_instance_ids(self, game_name: str):
        game_root = self.registry.resolve(game_name)
        if not game_root.exists():
            return []
        return sorted(
            path.name
            for path in game_root.iterdir()
            if path.is_dir() and not path.name.startswith(".")
        )

    def _select_instance(
        self,
        existing_ids,
        *,
        requested_game_id: Optional[str],
        new_game: bool,
    ):
        if new_game:
            return self._new_game_id(set(existing_ids)), True

        if requested_game_id is not None:
            requested = safe_path_segment(requested_game_id, "GAME_ID")
            if requested not in existing_ids:
                raise UnknownGameInstance(requested)
            return requested, False

        if len(existing_ids) == 1:
            return existing_ids[0], False
        if len(existing_ids) > 1:
            raise GameInstanceSelectionRequired(existing_ids)
        return self._new_game_id(set(existing_ids)), True

    def _new_game_id(self, existing) -> str:
        while True:
            game_id = uuid.uuid4().hex[:12]
            if game_id not in existing:
                return game_id

    def _create_save_skeleton(self, workspace: SessionWorkspace) -> None:
        for name in _SAVE_DIRS:
            workspace.save.resolve(name).mkdir(parents=True, exist_ok=True)
        if not workspace.save.exists("character_manifest.md"):
            workspace.save.write_text(
                "character_manifest.md",
                "# CHARACTER MANIFEST\n",
            )

    def _restore_controls(
        self,
        workspace: SessionWorkspace,
        init_complete: Optional[InitComplete],
        manifest: ScenarioManifest,
    ) -> ControlState:
        values = dict(manifest.control_defaults)

        if init_complete is not None:
            values.update(init_complete.control_values())

        if workspace.has_runtime_controls():
            values.update(workspace.load_controls())

        return ControlState.from_mapping(
            values,
            options=manifest.control_options,
        )

    @staticmethod
    def _read_optional(scenario: ScenarioPack, path: str) -> Optional[str]:
        if not scenario.exists(path):
            return None
        return scenario.read_text(path)

    @staticmethod
    def _validate_mode(
        play_mode: str,
        player_character_mode: str,
        main_character: str,
    ) -> None:
        valid = {
            ("player", "original"),
            ("player", "existing"),
            ("observer", "none"),
        }
        if (play_mode, player_character_mode) not in valid:
            raise ValueError("invalid play/player_character mode combination")

        if player_character_mode == "original":
            if main_character != "entities/main_character.md":
                raise ValueError(
                    "original player character must use entities/main_character.md"
                )
        elif player_character_mode == "existing":
            if not main_character or main_character == "none":
                raise ValueError("existing player character requires a source pointer")
        elif main_character != "none":
            raise ValueError("observer mode must use main_character: none")
