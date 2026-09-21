from __future__ import annotations

import json
from typing import List

from .filesystem import AgentFilesystem


def build_langchain_tools(filesystem: AgentFilesystem) -> List[object]:
    """Wrap DateGPT capabilities as LangChain tools.

    LangChain is imported lazily so bootstrap, save compatibility, and tests
    that do not invoke an agent can run without importing the framework.
    """

    try:
        from langchain.tools import tool
    except ImportError as exc:
        raise RuntimeError(
            "LangChain is required to build agent tools. "
            "Install BACKEND/requirements.txt."
        ) from exc

    @tool("content_read")
    def content_read(path: str) -> str:
        """Read one exact file from the mounted read-only scenario pack.

        Use manifest/index pointers when available. Do not read hidden content
        unless the runtime rules and current game state authorize that exact
        hidden file.
        """

        return filesystem.content_read(path)

    @tool("content_list")
    def content_list(path: str = ".") -> str:
        """List files below a scenario-pack directory without modifying it.

        Prefer precise directories and manifests over scanning the whole pack.
        """

        return _json(filesystem.content_list(path))

    @tool("content_search")
    def content_search(
        query: str,
        scope: str = ".",
        limit: int = 20,
    ) -> str:
        """Lexically search scenario text files.

        Ordinary searches exclude hidden/. Set scope to an exact hidden/
        directory only when runtime rules already authorize that lookup.
        """

        return _json(
            filesystem.content_search(
                query,
                scope=scope,
                limit=limit,
            )
        )

    @tool("save_read")
    def save_read(path: str) -> str:
        """Read an exact file from the current compatible game Save overlay."""

        return filesystem.save_read(path)

    @tool("save_list")
    def save_list(path: str = ".") -> str:
        """List files below a directory in the current compatible Save."""

        return _json(filesystem.save_list(path))

    @tool("save_search")
    def save_search(
        query: str,
        scope: str = ".",
        limit: int = 20,
    ) -> str:
        """Lexically search the current compatible Save overlay."""

        return _json(
            filesystem.save_search(
                query,
                scope=scope,
                limit=limit,
            )
        )

    @tool("save_write")
    def save_write(path: str, content: str) -> str:
        """Create or replace one text file in the current compatible Save.

        Preserve the runtime save contract. Store semantic long-term state here,
        not raw conversation transcripts or temporary reasoning.
        """

        return filesystem.save_write(path, content)

    @tool("save_delete")
    def save_delete(path: str) -> str:
        """Delete one file from the current compatible Save.

        Use only when runtime save semantics require removing stale overlay
        state. Directories cannot be deleted with this tool.
        """

        return filesystem.save_delete(path)

    @tool("scratchpad_read")
    def scratchpad_read(path: str) -> str:
        """Read one DateGPT working-memory file.

        Scratchpad content is mutable working state, not canonical world truth.
        """

        return filesystem.scratchpad_read(path)

    @tool("scratchpad_list")
    def scratchpad_list(path: str = ".") -> str:
        """List DateGPT working-memory files for the current session."""

        return _json(filesystem.scratchpad_list(path))

    @tool("scratchpad_search")
    def scratchpad_search(
        query: str,
        scope: str = ".",
        limit: int = 20,
    ) -> str:
        """Lexically search DateGPT working-memory files."""

        return _json(
            filesystem.scratchpad_search(
                query,
                scope=scope,
                limit=limit,
            )
        )

    @tool("scratchpad_write")
    def scratchpad_write(path: str, content: str) -> str:
        """Create or replace a DateGPT working-memory file.

        Use this for plans, threads, retrieval notes, continuity reminders, and
        other revisable state that should survive across player turns but is not
        canonical Save state.
        """

        return filesystem.scratchpad_write(path, content)

    @tool("scratchpad_delete")
    def scratchpad_delete(path: str) -> str:
        """Delete one obsolete DateGPT working-memory file."""

        return filesystem.scratchpad_delete(path)

    return [
        content_read,
        content_list,
        content_search,
        save_read,
        save_list,
        save_search,
        save_write,
        save_delete,
        scratchpad_read,
        scratchpad_list,
        scratchpad_search,
        scratchpad_write,
        scratchpad_delete,
    ]


def _json(value) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
    )
