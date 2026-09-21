from __future__ import annotations

from pathlib import Path
from typing import List

from ..fs import RootedTextStore


class ScenarioPack:
    """Read-only cartridge mounted by the DateGPT runtime.

    The engine deliberately does not model entities/story/flags/hidden here.
    Their meaning and lookup policy stay in the scenario manifest and prompt
    bundle, preserving compatibility when those documents evolve.
    """

    def __init__(self, root: Path) -> None:
        self.store = RootedTextStore(root, writable=False)

    @property
    def root(self) -> Path:
        return self.store.root

    def exists(self, path: str) -> bool:
        return self.store.exists(path)

    def read_text(self, path: str) -> str:
        return self.store.read_text(path)

    def list_files(self, relative_dir: str = ".") -> List[str]:
        return self.store.list_files(relative_dir)

    def search(self, query: str, *, scope: str = ".", limit: int = 20) -> List[dict]:
        return self.store.search_text(query, relative_dir=scope, limit=limit)
