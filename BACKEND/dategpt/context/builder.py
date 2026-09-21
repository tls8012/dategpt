from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..bootstrap.models import InitComplete
from ..scenarios import CharacterManifestIndex, ScenarioPack
from ..workspace import SessionWorkspace


_POINTER_RE = re.compile(
    r"(?:(?:entities|story|flags|assets)/"
    r"[^\n,;|\]\)]+?\.(?:md|json|txt))",
    re.IGNORECASE,
)
_ENTITY_SPLIT_RE = re.compile(r"[,;|\n、]+")


@dataclass(frozen=True)
class ContextMaterial:
    """Material assembled before an agent turn.

    stable_context is appended directly after runtime.md so provider prompt
    caching can reuse authored core material. dynamic_messages contain mutable
    scene/save/scratchpad state and therefore come later.
    """

    stable_context: str
    dynamic_messages: Tuple[dict, ...]
    core_files: Tuple[str, ...]


class ContextBuilder:
    """Hybrid context assembly: exact indexes first, search only when needed."""

    def __init__(
        self,
        *,
        scenario: ScenarioPack,
        workspace: SessionWorkspace,
        init_complete: Optional[InitComplete] = None,
        context_manifest_name: str = "context_manifest.json",
    ) -> None:
        self.scenario = scenario
        self.workspace = workspace
        self.init_complete = init_complete
        self.context_manifest_name = context_manifest_name

    def set_init_complete(
        self,
        init_complete: Optional[InitComplete],
    ) -> None:
        self.init_complete = init_complete

    def build_gameplay(self) -> ContextMaterial:
        core_files = self._core_files()
        stable_context = self._stable_core_context(core_files)

        blocks: List[str] = []

        if self.init_complete is not None:
            blocks.append(
                self._current_state_block(self.init_complete)
            )

            player_paths = self._player_paths(
                self.init_complete
            )
            player_block = self._player_context_block(
                self.init_complete
            )
            if player_block:
                blocks.append(player_block)

            pointer_paths = self._current_pointer_paths(
                self.init_complete,
                exclude=set(core_files) | player_paths,
            )
            pointer_block = self._paths_context_block(
                pointer_paths,
                heading="EXACT CURRENT-SCENE MATERIAL",
                description=(
                    "Loaded because the current Save points to "
                    "these exact files."
                ),
            )
            if pointer_block:
                blocks.append(pointer_block)

            character_paths = (
                self._resolved_scene_character_paths(
                    self.init_complete,
                    exclude=(
                        set(core_files)
                        | player_paths
                        | set(pointer_paths)
                    ),
                )
            )
            character_block = self._paths_context_block(
                character_paths,
                heading=(
                    "RESOLVED CURRENT-SCENE CHARACTERS"
                ),
                description=(
                    "Loaded from unique exact matches in the "
                    "Distribution/Save public character index."
                ),
            )
            if character_block:
                blocks.append(character_block)

        overlay_block = self._core_overlay_block(core_files)
        if overlay_block:
            blocks.append(overlay_block)

        scratchpad_block = self._scratchpad_block(
            exclude_prefixes=("onboarding/",),
        )
        if scratchpad_block:
            blocks.append(scratchpad_block)

        return ContextMaterial(
            stable_context=stable_context,
            dynamic_messages=_as_system_messages(blocks),
            core_files=tuple(core_files),
        )

    def build_onboarding(
        self,
        *,
        welcome_text: Optional[str],
        onboarding_state: Mapping[str, object],
    ) -> ContextMaterial:
        core_files = self._core_files()
        stable_context = self._stable_core_context(core_files)

        blocks: List[str] = [
            "# ONBOARDING STATE\n"
            + json.dumps(
                dict(onboarding_state),
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        ]

        if welcome_text:
            blocks.append(
                "# DISTRIBUTION WELCOME\n" + welcome_text
            )

        if self.scenario.exists("character_manifest.md"):
            blocks.append(
                "# PUBLIC CHARACTER INDEX\n"
                + self.scenario.read_text(
                    "character_manifest.md"
                )
            )

        draft_path = "onboarding/main_character.md"
        if self.workspace.scratchpad.exists(draft_path):
            blocks.append(
                "# CURRENT CHARACTER DRAFT\n"
                + self.workspace.scratchpad.read_text(
                    draft_path
                )
            )

        scratchpad_block = self._scratchpad_block(
            exclude={draft_path},
        )
        if scratchpad_block:
            blocks.append(scratchpad_block)

        return ContextMaterial(
            stable_context=stable_context,
            dynamic_messages=_as_system_messages(blocks),
            core_files=tuple(core_files),
        )

    def _character_index(
        self,
    ) -> CharacterManifestIndex:
        distribution_text = ""
        save_text = ""

        if self.scenario.exists(
            "character_manifest.md"
        ):
            distribution_text = self.scenario.read_text(
                "character_manifest.md"
            )

        if self.workspace.save.exists(
            "character_manifest.md"
        ):
            save_text = self.workspace.save.read_text(
                "character_manifest.md"
            )

        return CharacterManifestIndex.from_texts(
            distribution_text=distribution_text,
            save_text=save_text,
        )

    def _resolved_scene_character_paths(
        self,
        init_complete: InitComplete,
        *,
        exclude: set,
    ) -> Tuple[str, ...]:
        value = init_complete.current.get(
            "present_entities",
            "",
        )
        if not value:
            return ()

        index = self._character_index()
        paths = []
        seen = set(exclude)

        for name in _extract_entity_names(value):
            record = index.resolve_unique(name)
            if record is None:
                continue
            if record.path in seen:
                continue
            if not (
                self.scenario.exists(record.path)
                or self.workspace.save.exists(record.path)
            ):
                continue

            seen.add(record.path)
            paths.append(record.path)

        return tuple(paths)

    def _core_files(self) -> List[str]:
        if not self.scenario.exists(self.context_manifest_name):
            return []

        data = json.loads(
            self.scenario.read_text(
                self.context_manifest_name
            )
        )
        if not isinstance(data, dict):
            raise ValueError(
                "context_manifest.json must contain an object"
            )

        values = data.get("core_files", [])
        if not isinstance(values, list):
            raise ValueError(
                "context_manifest.json core_files must be a list"
            )

        files: List[str] = []
        seen = set()
        for value in values:
            if not isinstance(value, str):
                continue
            path = value.strip()
            if not path or path in seen or _is_hidden(path):
                continue
            if not self.scenario.exists(path):
                raise FileNotFoundError(path)
            files.append(path)
            seen.add(path)

        return files

    def _stable_core_context(
        self,
        core_files: Sequence[str],
    ) -> str:
        if not core_files:
            return ""

        chunks = [
            "# SCENARIO CORE CONTEXT",
            (
                "Authored baseline material declared by "
                "context_manifest.json. Save/session changes "
                "override these baselines when they conflict."
            ),
        ]
        for path in core_files:
            chunks.append(
                "## SOURCE: {}\n{}".format(
                    path,
                    self.scenario.read_text(path),
                )
            )
        return "\n\n".join(chunks)

    def _core_overlay_block(
        self,
        core_files: Sequence[str],
    ) -> str:
        chunks = []
        for path in core_files:
            if self.workspace.save.exists(path):
                chunks.append(
                    "## SAVE OVERLAY: {}\n{}".format(
                        path,
                        self.workspace.save.read_text(path),
                    )
                )

        if not chunks:
            return ""
        return (
            "# CORE ENTITY SAVE OVERLAYS\n"
            "These mutable Save overlays are newer than authored baselines."
            "\n\n"
            + "\n\n".join(chunks)
        )

    def _current_state_block(
        self,
        init_complete: InitComplete,
    ) -> str:
        payload = {
            "game_name": init_complete.game_name,
            "game_id": init_complete.game_id,
            "play_mode": init_complete.play_mode,
            "player_character_mode": (
                init_complete.player_character_mode
            ),
            "main_character": init_complete.main_character,
            "current": dict(init_complete.current),
        }
        return (
            "# SAVED CURRENT STATE\n"
            "This is the latest semantic Save checkpoint. "
            "Newer scratchpad/recent conversation may supersede it.\n"
            + json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        )

    def _player_paths(
        self,
        init_complete: InitComplete,
    ) -> set:
        path = init_complete.main_character.strip()
        if not path or path == "none":
            return set()
        return {path}

    def _player_context_block(
        self,
        init_complete: InitComplete,
    ) -> str:
        path = init_complete.main_character.strip()
        if not path or path == "none":
            return ""

        chunks = ["# PLAYER CHARACTER"]

        if self.scenario.exists(path) and not _is_hidden(path):
            chunks.append(
                "## SOURCE: {}\n{}".format(
                    path,
                    self.scenario.read_text(path),
                )
            )

        if self.workspace.save.exists(path):
            chunks.append(
                "## SAVE OVERLAY: {}\n{}".format(
                    path,
                    self.workspace.save.read_text(path),
                )
            )

        if len(chunks) == 1:
            return ""

        return "\n\n".join(chunks)

    def _current_pointer_paths(
        self,
        init_complete: InitComplete,
        *,
        exclude: set,
    ) -> Tuple[str, ...]:
        paths = []
        seen = set(exclude)

        for value in init_complete.current.values():
            for path in _extract_pointers(value):
                if path in seen or _is_hidden(path):
                    continue
                if (
                    self.scenario.exists(path)
                    or self.workspace.save.exists(path)
                ):
                    paths.append(path)
                    seen.add(path)

        return tuple(paths)

    def _paths_context_block(
        self,
        paths: Sequence[str],
        *,
        heading: str,
        description: str,
    ) -> str:
        chunks = []

        for path in paths:
            if self.scenario.exists(path):
                chunks.append(
                    "## SOURCE: {}\n{}".format(
                        path,
                        self.scenario.read_text(path),
                    )
                )
            if self.workspace.save.exists(path):
                chunks.append(
                    "## SAVE OVERLAY: {}\n{}".format(
                        path,
                        self.workspace.save.read_text(path),
                    )
                )

        if not chunks:
            return ""

        return (
            "# {}\n{}\n\n{}".format(
                heading,
                description,
                "\n\n".join(chunks),
            )
        )

    def _scratchpad_block(
        self,
        *,
        exclude: Optional[set] = None,
        exclude_prefixes: Sequence[str] = (),
    ) -> str:
        excluded = exclude or set()
        snapshot = self.workspace.scratchpad.snapshot()
        chunks = []

        for path in sorted(snapshot):
            if path in excluded:
                continue
            if any(
                path.startswith(prefix)
                for prefix in exclude_prefixes
            ):
                continue
            chunks.append(
                "## {}\n{}".format(
                    path,
                    snapshot[path],
                )
            )

        if not chunks:
            return ""

        return (
            "# DATEGPT SESSION SCRATCHPAD\n"
            "Revisable working memory, not canonical world truth. "
            "Current confirmed conversation can supersede it."
            "\n\n"
            + "\n\n".join(chunks)
        )


def _extract_pointers(value: object) -> Iterable[str]:
    if not isinstance(value, str):
        return ()
    return tuple(
        match.group(0).rstrip(".:、。")
        for match in _POINTER_RE.finditer(value)
    )


def _extract_entity_names(
    value: object,
) -> Tuple[str, ...]:
    if not isinstance(value, str):
        return ()

    names = []
    seen = set()

    for raw in _ENTITY_SPLIT_RE.split(value):
        text = raw.strip().strip(
            "[](){}<>\"'"
        )
        if not text:
            continue
        if "/" in text or text.casefold() in {
            "none",
            "null",
        }:
            continue

        normalized = " ".join(
            text.casefold().split()
        )
        if normalized in seen:
            continue
        seen.add(normalized)
        names.append(text)

    return tuple(names)


def _is_hidden(path: str) -> bool:
    normalized = str(path).replace("\\", "/").lstrip("./")
    return (
        normalized == "hidden"
        or normalized.startswith("hidden/")
    )


def _as_system_messages(
    blocks: Sequence[str],
) -> Tuple[dict, ...]:
    content = "\n\n".join(
        block for block in blocks if block
    )
    if not content:
        return ()
    return (
        {
            "role": "system",
            "content": content,
        },
    )
