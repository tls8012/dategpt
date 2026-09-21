from __future__ import annotations

from typing import List, Optional

from ..scenarios import ScenarioPack
from ..workspace import SessionWorkspace, TurnTransaction


class AgentFilesystem:
    """Raw filesystem capabilities exposed to the story agent.

    Scenario content is read-only. Save and scratchpad are writable, rooted
    stores. History is deliberately absent: successful user/assistant turns are
    appended by AgentRunner, not by the model.
    """

    def __init__(
        self,
        *,
        scenario: ScenarioPack,
        workspace: SessionWorkspace,
        transaction: Optional[TurnTransaction] = None,
    ) -> None:
        self.scenario = scenario
        self.workspace = workspace
        self.transaction = transaction

    # ------------------------------------------------------------------
    # Scenario / distribution: read only
    # ------------------------------------------------------------------

    def content_read(self, path: str) -> str:
        return self.scenario.read_text(path)

    def content_list(self, path: str = ".") -> List[str]:
        return self.scenario.list_files(path)

    def content_search(
        self,
        query: str,
        *,
        scope: str = ".",
        limit: int = 20,
    ) -> List[dict]:
        """Lexical content search.

        hidden/ is intentionally excluded from ordinary whole-pack searches.
        The agent may explicitly search a hidden/ scope only when runtime rules
        already authorize access to that hidden area.
        """

        requested_limit = max(1, min(int(limit), 100))
        if _is_hidden_path(scope):
            return self.scenario.search(
                query,
                scope=scope,
                limit=requested_limit,
            )

        candidates = self.scenario.search(
            query,
            scope=scope,
            limit=max(requested_limit * 4, 40),
        )
        visible = [
            item
            for item in candidates
            if not _is_hidden_path(item.get("path", ""))
        ]
        return visible[:requested_limit]

    # ------------------------------------------------------------------
    # Semantic Save: read/write
    # ------------------------------------------------------------------

    def save_read(self, path: str) -> str:
        return self.workspace.save.read_text(path)

    def save_list(self, path: str = ".") -> List[str]:
        return self.workspace.save.list_files(path)

    def save_search(
        self,
        query: str,
        *,
        scope: str = ".",
        limit: int = 20,
    ) -> List[dict]:
        return self.workspace.save.search_text(
            query,
            relative_dir=scope,
            limit=max(1, min(int(limit), 100)),
        )

    def save_write(self, path: str, content: str) -> str:
        self._capture("save", self.workspace.save, path)
        self.workspace.save.write_text(path, content)
        return "saved: {}".format(path)

    def save_delete(self, path: str) -> str:
        self._capture("save", self.workspace.save, path)
        self.workspace.save.delete(path)
        return "deleted: {}".format(path)

    # ------------------------------------------------------------------
    # DateGPT working memory: read/write
    # ------------------------------------------------------------------

    def scratchpad_read(self, path: str) -> str:
        return self.workspace.scratchpad.read_text(path)

    def scratchpad_list(self, path: str = ".") -> List[str]:
        return self.workspace.scratchpad.list_files(path)

    def scratchpad_search(
        self,
        query: str,
        *,
        scope: str = ".",
        limit: int = 20,
    ) -> List[dict]:
        return self.workspace.scratchpad.search_text(
            query,
            relative_dir=scope,
            limit=max(1, min(int(limit), 100)),
        )

    def scratchpad_write(self, path: str, content: str) -> str:
        self._capture(
            "scratchpad",
            self.workspace.scratchpad,
            path,
        )
        self.workspace.scratchpad.write_text(path, content)
        return "scratchpad saved: {}".format(path)

    def scratchpad_delete(self, path: str) -> str:
        self._capture(
            "scratchpad",
            self.workspace.scratchpad,
            path,
        )
        self.workspace.scratchpad.delete(path)
        return "scratchpad deleted: {}".format(path)

    def _capture(self, store_name: str, store, path: str) -> None:
        if self.transaction is not None:
            self.transaction.capture(
                store_name,
                store,
                path,
            )


def _is_hidden_path(path: str) -> bool:
    normalized = str(path).replace("\\", "/").lstrip("./")
    return normalized == "hidden" or normalized.startswith("hidden/")
