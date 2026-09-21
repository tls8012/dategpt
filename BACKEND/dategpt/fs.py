from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List, Optional


_TEXT_SUFFIXES = {
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".csv",
}


class PathOutsideRoot(ValueError):
    """Raised when a relative path escapes its configured root."""


class ReadOnlyStore(PermissionError):
    """Raised when a write is attempted against a read-only store."""


class RootedTextStore:
    """Small, dependency-free text file store confined to one directory.

    The class intentionally knows nothing about entities, stories, flags, or
    save semantics. Those meanings belong to the prompt/scenario layer.
    """

    def __init__(self, root: Path, *, writable: bool = False) -> None:
        self.root = Path(root).expanduser().resolve()
        self.writable = writable

    def ensure_root(self) -> None:
        if self.writable:
            self.root.mkdir(parents=True, exist_ok=True)

    def resolve(self, relative_path: str) -> Path:
        if not isinstance(relative_path, str) or not relative_path.strip():
            raise ValueError("relative_path must be a non-empty string")

        candidate = (self.root / relative_path).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise PathOutsideRoot(relative_path) from exc
        return candidate

    def exists(self, relative_path: str) -> bool:
        return self.resolve(relative_path).exists()

    def read_text(self, relative_path: str) -> str:
        path = self.resolve(relative_path)
        return path.read_text(encoding="utf-8")

    def list_files(self, relative_dir: str = ".") -> List[str]:
        base = self.resolve(relative_dir)
        if not base.exists():
            return []
        if not base.is_dir():
            raise NotADirectoryError(relative_dir)

        return sorted(
            str(path.relative_to(self.root)).replace(os.sep, "/")
            for path in base.rglob("*")
            if path.is_file()
        )

    def write_text(self, relative_path: str, content: str) -> None:
        self._require_writable()
        path = self.resolve(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Replace atomically so an interrupted semantic save does not leave a
        # half-written Markdown file behind.
        temp_path = path.with_name(path.name + ".tmp")
        temp_path.write_text(content, encoding="utf-8")
        os.replace(temp_path, path)

    def delete(self, relative_path: str) -> None:
        self._require_writable()
        path = self.resolve(relative_path)
        if path.exists():
            path.unlink()

    def search_text(
        self,
        query: str,
        *,
        relative_dir: str = ".",
        suffixes: Optional[Iterable[str]] = None,
        limit: int = 20,
        max_file_bytes: int = 1_000_000,
    ) -> List[dict]:
        """Simple lexical search intended as the first retrieval backend.

        No vector database is assumed. The interface can later be backed by
        SQLite FTS/BM25 without changing the agent-facing capability.
        """

        terms = [term.casefold() for term in query.split() if term.strip()]
        if not terms:
            return []

        allowed = set(suffixes or _TEXT_SUFFIXES)
        base = self.resolve(relative_dir)
        if not base.exists():
            return []

        results = []
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.casefold() not in allowed:
                continue
            try:
                if path.stat().st_size > max_file_bytes:
                    continue
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            folded = text.casefold()
            score = sum(folded.count(term) for term in terms)
            filename = path.name.casefold()
            score += 3 * sum(filename.count(term) for term in terms)
            if score <= 0:
                continue

            first_line = ""
            for line in text.splitlines():
                if any(term in line.casefold() for term in terms):
                    first_line = line.strip()
                    break

            results.append(
                {
                    "path": str(path.relative_to(self.root)).replace(os.sep, "/"),
                    "score": score,
                    "preview": first_line[:300],
                }
            )

        results.sort(key=lambda item: (-item["score"], item["path"]))
        return results[: max(1, limit)]

    def _require_writable(self) -> None:
        if not self.writable:
            raise ReadOnlyStore(str(self.root))
