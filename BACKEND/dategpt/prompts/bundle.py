from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple

from ..fs import RootedTextStore


DATEGPT_RUNTIME_ADAPTER = """# DATEGPT HOST ADAPTER
DateGPT already mounts the selected Distribution as a local read-only ScenarioPack.
Do not look for or recreate games/GAME_NAME/game_source.md.
Do not use .scaffolding paths through gameplay file tools; runtime/onboarding policy is already injected.
Scenario/content tool paths are relative to the mounted Distribution root, and Save tool paths are relative to the current GAME_ID Save root.
When a REGISTERED VISUAL ASSETS block is present, use it as incremental visual state. Choose a background at scene start or when the background should change, and choose SCGs when the visible character set or a visible character's registered pose should change. Do not repeat unchanged background/SCG IDs on every segment; omitted visuals stay on screen. If every visible character leaves, set clear_characters=true. If multiple authored staging choices are equally valid, prefer one that has an exact registered visual match instead of an equivalent unrepresented staging. Respect current engine controls such as gender/head_mode. Put only registered asset IDs in structured response assets; never put file paths there.
"""


@dataclass(frozen=True)
class PromptSnapshot:
    """Immutable prompt material for one agent invocation."""

    system_prompt: str
    controls: Dict[str, Any]
    source_files: Tuple[str, ...]
    fingerprint: str


class PromptBundle:
    """Loads independently licensed LLM policy files."""

    def __init__(
        self,
        root: Path,
        *,
        runtime_name: str = "runtime.md",
        onboarding_name: str = "onboarding.md",
        controls_name: str = "controls.json",
    ) -> None:
        self.store = RootedTextStore(root, writable=False)
        self.runtime_name = runtime_name
        self.onboarding_name = onboarding_name
        self.controls_name = controls_name

    @property
    def root(self) -> Path:
        return self.store.root

    def read_runtime(self) -> str:
        return self.store.read_text(self.runtime_name)

    def has_onboarding(self) -> bool:
        return self.store.exists(self.onboarding_name)

    def read_onboarding(self) -> str:
        if not self.has_onboarding():
            raise FileNotFoundError(self.onboarding_name)
        return self.store.read_text(self.onboarding_name)

    def control_manifest(self) -> Dict[str, Any]:
        if not self.store.exists(self.controls_name):
            return {}
        data = json.loads(
            self.store.read_text(self.controls_name)
        )
        if not isinstance(data, dict):
            raise ValueError(
                "controls.json must contain a JSON object"
            )
        return data

    def snapshot(
        self,
        *,
        controls: Mapping[str, Any],
        stable_context: str = "",
        mode_prompt: str = "",
        mode_prompt_name: str = "",
    ) -> PromptSnapshot:
        parts = [
            self.read_runtime().rstrip(),
            DATEGPT_RUNTIME_ADAPTER.rstrip(),
        ]
        source_files = [self.runtime_name]

        if stable_context:
            parts.append(stable_context.rstrip())

        if mode_prompt:
            parts.append(mode_prompt.rstrip())
            if mode_prompt_name:
                source_files.append(mode_prompt_name)

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

        system_prompt = "\n\n".join(parts)
        digest = hashlib.sha256(
            system_prompt.encode("utf-8")
        ).hexdigest()

        return PromptSnapshot(
            system_prompt=system_prompt,
            controls=dict(controls),
            source_files=tuple(source_files),
            fingerprint=digest,
        )
