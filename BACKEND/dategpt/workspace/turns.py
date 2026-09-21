from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class FilePreimage:
    store: str
    path: str
    existed: bool
    content: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "store": self.store,
            "path": self.path,
            "existed": self.existed,
            "content": self.content,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FilePreimage":
        return cls(
            store=str(data["store"]),
            path=str(data["path"]),
            existed=bool(data["existed"]),
            content=str(data.get("content", "")),
        )


class TurnTransaction:
    """Collect only files actually mutated during one gameplay turn."""

    def __init__(
        self,
        manager: "TurnJournal",
        *,
        turn_id: str,
        history_before: int,
    ) -> None:
        self.manager = manager
        self.turn_id = turn_id
        self.history_before = history_before
        self._preimages: Dict[Tuple[str, str], FilePreimage] = {}
        self._order: List[Tuple[str, str]] = []
        self._committed = False

    def capture(self, store_name: str, store, path: str) -> None:
        key = (store_name, str(path))
        if key in self._preimages:
            return

        existed = store.exists(path)
        content = store.read_text(path) if existed else ""
        self._preimages[key] = FilePreimage(
            store=store_name,
            path=str(path),
            existed=existed,
            content=content,
        )
        self._order.append(key)

    def commit(
        self,
        *,
        user_text: str,
        assistant_text: str,
        prompt_fingerprint: str,
    ) -> None:
        if self._committed:
            raise RuntimeError("turn transaction already committed")

        self.manager._commit(
            turn_id=self.turn_id,
            history_before=self.history_before,
            user_text=user_text,
            assistant_text=assistant_text,
            prompt_fingerprint=prompt_fingerprint,
            preimages=[
                self._preimages[key]
                for key in self._order
            ],
        )
        self._committed = True

    def rollback_uncommitted(self) -> None:
        if self._committed:
            return
        self.manager._restore_preimages(
            [
                self._preimages[key]
                for key in reversed(self._order)
            ]
        )
        self.manager.history.truncate(self.history_before)


class TurnJournal:
    """Sparse reversible journal for committed gameplay turns.

    The semantic Save remains the one current Save. A turn journal stores only
    preimages of files that the agent actually changed during that turn plus
    the history boundary. This is intentionally not a full save snapshot.
    """

    def __init__(
        self,
        *,
        root: Path,
        save_store,
        scratchpad_store,
        history,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.save_store = save_store
        self.scratchpad_store = scratchpad_store
        self.history = history
        self.index_path = self.root / "index.json"

    def begin(self) -> TurnTransaction:
        return TurnTransaction(
            self,
            turn_id=uuid.uuid4().hex,
            history_before=self.history.count(),
        )

    def latest_turn_id(self) -> Optional[str]:
        ids = self._load_index()
        return ids[-1] if ids else None

    def amend_latest(
        self,
        preimages: List[FilePreimage],
    ) -> None:
        turn_id = self.latest_turn_id()
        if turn_id is None or not preimages:
            return

        data = self._load_journal(turn_id)
        if data is None:
            return

        existing = [
            FilePreimage.from_dict(item)
            for item in data.get("preimages", [])
            if isinstance(item, dict)
        ]
        seen = {
            (item.store, item.path)
            for item in existing
        }
        for item in preimages:
            key = (item.store, item.path)
            if key not in seen:
                existing.append(item)
                seen.add(key)

        data["preimages"] = [
            item.to_dict() for item in existing
        ]
        self._write_json(
            self._journal_path(turn_id),
            data,
        )

    def list_turns(self, limit: int = 50) -> List[Dict[str, Any]]:
        ids = self._load_index()
        if limit > 0:
            ids = ids[-limit:]

        turns = []
        for turn_id in ids:
            data = self._load_journal(turn_id)
            if data is None:
                continue
            turns.append(
                {
                    "turn_id": turn_id,
                    "user_text": str(
                        data.get("user_text", "")
                    ),
                    "assistant_text": str(
                        data.get("assistant_text", "")
                    ),
                    "prompt_fingerprint": str(
                        data.get("prompt_fingerprint", "")
                    ),
                    "changed_files": len(
                        data.get("preimages", [])
                    ),
                }
            )
        return turns

    def rollback(
        self,
        turn_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        ids = self._load_index()
        if not ids:
            raise ValueError("되돌릴 게임플레이 턴이 없습니다.")

        target = turn_id or ids[-1]
        try:
            target_index = ids.index(target)
        except ValueError as exc:
            raise ValueError(
                "요청한 turn_id를 찾을 수 없습니다."
            ) from exc

        target_data = self._load_journal(target)
        if target_data is None:
            raise ValueError(
                "턴 journal 파일이 없습니다: {}".format(target)
            )

        removed = ids[target_index:]
        for current_id in reversed(removed):
            data = self._load_journal(current_id)
            if data is None:
                continue
            preimages = [
                FilePreimage.from_dict(item)
                for item in data.get("preimages", [])
                if isinstance(item, dict)
            ]
            self._restore_preimages(
                list(reversed(preimages))
            )

        self.history.truncate(
            int(target_data.get("history_before", 0))
        )

        for current_id in removed:
            path = self._journal_path(current_id)
            if path.exists():
                path.unlink()

        self._save_index(ids[:target_index])

        return {
            "turn_id": target,
            "user_text": str(
                target_data.get("user_text", "")
            ),
            "assistant_text": str(
                target_data.get("assistant_text", "")
            ),
            "rolled_back_turn_ids": removed,
        }

    def _commit(
        self,
        *,
        turn_id: str,
        history_before: int,
        user_text: str,
        assistant_text: str,
        prompt_fingerprint: str,
        preimages: List[FilePreimage],
    ) -> None:
        payload = {
            "turn_id": turn_id,
            "history_before": int(history_before),
            "user_text": user_text,
            "assistant_text": assistant_text,
            "prompt_fingerprint": prompt_fingerprint,
            "preimages": [
                item.to_dict() for item in preimages
            ],
        }
        self._write_json(
            self._journal_path(turn_id),
            payload,
        )

        ids = self._load_index()
        ids.append(turn_id)
        self._save_index(ids)

    def _restore_preimages(
        self,
        preimages: List[FilePreimage],
    ) -> None:
        for item in preimages:
            store = self._store(item.store)
            if item.existed:
                store.write_text(
                    item.path,
                    item.content,
                )
            else:
                store.delete(item.path)

    def _store(self, name: str):
        if name == "save":
            return self.save_store
        if name == "scratchpad":
            return self.scratchpad_store
        raise ValueError(
            "unknown turn journal store: {}".format(name)
        )

    def _journal_path(self, turn_id: str) -> Path:
        return self.root / "{}.json".format(turn_id)

    def _load_journal(
        self,
        turn_id: str,
    ) -> Optional[Dict[str, Any]]:
        path = self._journal_path(turn_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(
                "turn journal must contain an object"
            )
        return data

    def _load_index(self) -> List[str]:
        if not self.index_path.exists():
            return []
        data = json.loads(
            self.index_path.read_text(encoding="utf-8")
        )
        if not isinstance(data, list):
            raise ValueError(
                "turn journal index must contain a list"
            )
        return [
            str(value)
            for value in data
            if isinstance(value, str) and value
        ]

    def _save_index(self, ids: List[str]) -> None:
        self._write_json(self.index_path, ids)

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + ".tmp")
        temp.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        os.replace(temp, path)
