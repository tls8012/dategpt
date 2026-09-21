from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from ..fs import RootedTextStore


class SaveStore(RootedTextStore):
    """Writable overlay compatible with the original prompt save layout."""

    def __init__(self, root: Path) -> None:
        super().__init__(root, writable=True)
        self.ensure_root()


class ScratchpadStore(RootedTextStore):
    """Agent working memory. This is not canonical world state."""

    def __init__(self, root: Path) -> None:
        super().__init__(root, writable=True)
        self.ensure_root()

    def snapshot(self, *, limit_files: int = 50, max_chars: int = 100_000) -> Dict[str, str]:
        """Return a bounded text snapshot for turn-context construction."""

        output: Dict[str, str] = {}
        used = 0
        for path in self.list_files()[:limit_files]:
            try:
                text = self.read_text(path)
            except (OSError, UnicodeDecodeError):
                continue
            remaining = max_chars - used
            if remaining <= 0:
                break
            output[path] = text[:remaining]
            used += len(output[path])
        return output


class HistoryStore:
    """Append-only conversation/audit history outside the compatible Save tree."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: Dict[str, Any]) -> None:
        payload = dict(record)
        payload.setdefault(
            "timestamp",
            datetime.now(timezone.utc).isoformat(),
        )
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def records(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        records = []
        for line in self.path.read_text(
            encoding="utf-8"
        ).splitlines():
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                records.append(value)
        return records

    def count(self) -> int:
        return len(self.records())

    def tail(self, limit: int = 20) -> List[Dict[str, Any]]:
        if limit <= 0:
            return []
        return self.records()[-limit:]

    def truncate(self, count: int) -> None:
        records = self.records()[:max(0, int(count))]
        temp = self.path.with_name(
            self.path.name + ".tmp"
        )
        with temp.open("w", encoding="utf-8") as stream:
            for record in records:
                stream.write(
                    json.dumps(
                        record,
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        temp.replace(self.path)
