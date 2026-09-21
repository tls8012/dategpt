from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple

from ..fs import RootedTextStore


@dataclass(frozen=True)
class PromptSnapshot:
    """Immutable prompt material for one agent invocation.

    Read the long runtime prompt once at the start of a player turn. The same
    snapshot is then reused throughout that LangChain agent loop rather than
    reloading/re-appending the prompt for each tool step.
    """

    system_prompt: str
    controls: Dict[str, Any]
    source_files: Tuple[str, ...]
    fingerprint: str


class PromptBundle:
    """Loads prompt policy from an independently managed directory.

    Expected conventional names are init.md and runtime.md, matching the
    original ChatGPT-project prompts. No prompt text is embedded in the engine,
    so the prompt bundle may carry its own license and update cadence.
    """

    def __init__(
        self,
        root: Path,
        *,
        init_name: str = "init.md",
        runtime_name: str = "runtime.md",
        controls_name: str = "controls.json",
    ) -> None:
        self.store = RootedTextStore(root, writable=False)
        self.init_name = init_name
        self.runtime_name = runtime_name
        self.controls_name = controls_name

    @property
    def root(self) -> Path:
        return self.store.root

    def read_init(self) -> str:
        return self.store.read_text(self.init_name)

    def read_runtime(self) -> str:
        return self.store.read_text(self.runtime_name)

    def control_manifest(self) -> Dict[str, Any]:
        """Optional UI/control metadata owned by the prompt bundle.

        The Markdown prompts remain authoritative game policy. This optional
        sidecar exists so button labels/aliases can evolve without teaching the
        Python engine the prose structure of runtime.md.
        """

        if not self.store.exists(self.controls_name):
            return {}
        data = json.loads(self.store.read_text(self.controls_name))
        if not isinstance(data, dict):
            raise ValueError("controls.json must contain a JSON object")
        return data

    def snapshot(
        self,
        *,
        controls: Mapping[str, Any],
        include_init: bool = False,
    ) -> PromptSnapshot:
        parts = []
        source_files = []

        if include_init:
            parts.append(self.read_init())
            source_files.append(self.init_name)

        parts.append(self.read_runtime())
        source_files.append(self.runtime_name)

        # Controls are deliberately repeated every player turn. They are tiny,
        # mutable runtime state and must not depend on model memory.
        control_block = json.dumps(
            dict(controls),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        parts.append(
            "# CURRENT ENGINE CONTROLS\n"
            "These values are the current runtime settings for this turn.\n"
            + control_block
        )

        system_prompt = "\n\n".join(part.rstrip() for part in parts if part)
        digest = hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()

        return PromptSnapshot(
            system_prompt=system_prompt,
            controls=dict(controls),
            source_files=tuple(source_files),
            fingerprint=digest,
        )
