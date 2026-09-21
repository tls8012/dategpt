from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple

from ..fs import RootedTextStore


@dataclass(frozen=True)
class PromptSnapshot:
    """Immutable runtime prompt material for one agent invocation."""

    system_prompt: str
    controls: Dict[str, Any]
    source_files: Tuple[str, ...]
    fingerprint: str


class PromptBundle:
    """Loads LLM runtime policy from an independently managed directory.

    DateGPT does not send init.md to the model. Deterministic initialization
    from the original init.md contract lives in dategpt.bootstrap instead.
    This keeps the long-lived gameplay prompt limited to runtime.md.
    """

    def __init__(
        self,
        root: Path,
        *,
        runtime_name: str = "runtime.md",
        controls_name: str = "controls.json",
    ) -> None:
        self.store = RootedTextStore(root, writable=False)
        self.runtime_name = runtime_name
        self.controls_name = controls_name

    @property
    def root(self) -> Path:
        return self.store.root

    def read_runtime(self) -> str:
        return self.store.read_text(self.runtime_name)

    def control_manifest(self) -> Dict[str, Any]:
        if not self.store.exists(self.controls_name):
            return {}
        data = json.loads(self.store.read_text(self.controls_name))
        if not isinstance(data, dict):
            raise ValueError("controls.json must contain a JSON object")
        return data

    def snapshot(self, *, controls: Mapping[str, Any]) -> PromptSnapshot:
        runtime = self.read_runtime()

        # Small, mutable settings are repeated every player turn and must not
        # depend on model memory.
        control_block = json.dumps(
            dict(controls),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        system_prompt = (
            runtime.rstrip()
            + "\n\n# CURRENT ENGINE CONTROLS\n"
            + "These values are the current runtime settings for this turn.\n"
            + control_block
        )
        digest = hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()

        return PromptSnapshot(
            system_prompt=system_prompt,
            controls=dict(controls),
            source_files=(self.runtime_name,),
            fingerprint=digest,
        )
