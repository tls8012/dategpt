from __future__ import annotations

import json
from typing import List

from .filesystem import AgentFilesystem


def build_langchain_tools(
    filesystem: AgentFilesystem,
) -> List[object]:
    tool = _tool_decorator()

    @tool("content_read")
    def content_read(path: str) -> str:
        """Read one exact file from the mounted read-only scenario pack."""

        return filesystem.content_read(path)

    @tool("content_list")
    def content_list(path: str = ".") -> str:
        """List files below a precise scenario-pack directory."""

        return _json(
            filesystem.content_list(path)
        )

    @tool("content_search")
    def content_search(
        query: str,
        scope: str = ".",
        limit: int = 20,
    ) -> str:
        """Lexically search public scenario text files."""

        return _json(
            filesystem.content_search(
                query,
                scope=scope,
                limit=limit,
            )
        )

    @tool("save_read")
    def save_read(path: str) -> str:
        """Read one effective path as Distribution baseline plus newer Save overlay."""

        return filesystem.save_read(path)

    @tool("save_list")
    def save_list(path: str = ".") -> str:
        """List files below a directory in the compatible Save."""

        return _json(
            filesystem.save_list(path)
        )

    @tool("save_search")
    def save_search(
        query: str,
        scope: str = ".",
        limit: int = 20,
    ) -> str:
        """Lexically search the compatible Save overlay."""

        return _json(
            filesystem.save_search(
                query,
                scope=scope,
                limit=limit,
            )
        )

    @tool("save_write")
    def save_write(path: str, content: str) -> str:
        """Create or replace one semantic Save text file."""

        return filesystem.save_write(path, content)

    @tool("save_delete")
    def save_delete(path: str) -> str:
        """Delete one stale file from the compatible Save."""

        return filesystem.save_delete(path)

    scratchpad_tools = _scratchpad_tools(
        tool,
        filesystem,
    )

    return [
        content_read,
        content_list,
        content_search,
        save_read,
        save_list,
        save_search,
        save_write,
        save_delete,
        *scratchpad_tools,
    ]


def build_onboarding_tools(
    filesystem: AgentFilesystem,
) -> List[object]:
    """Restricted onboarding tools: scenario read + scratchpad only."""

    tool = _tool_decorator()

    @tool("content_read")
    def content_read(path: str) -> str:
        """Read one exact public scenario file needed for onboarding."""

        return filesystem.content_read(path)

    @tool("content_list")
    def content_list(path: str = ".") -> str:
        """List a precise public scenario directory."""

        return _json(
            filesystem.content_list(path)
        )

    @tool("content_search")
    def content_search(
        query: str,
        scope: str = ".",
        limit: int = 20,
    ) -> str:
        """Search public scenario material during character creation."""

        return _json(
            filesystem.content_search(
                query,
                scope=scope,
                limit=limit,
            )
        )

    return [
        content_read,
        content_list,
        content_search,
        *_scratchpad_tools(
            tool,
            filesystem,
        ),
    ]


def _scratchpad_tools(tool, filesystem):
    @tool("scratchpad_read")
    def scratchpad_read(path: str) -> str:
        """Read one DateGPT working-memory file."""

        return filesystem.scratchpad_read(path)

    @tool("scratchpad_list")
    def scratchpad_list(path: str = ".") -> str:
        """List DateGPT working-memory files."""

        return _json(
            filesystem.scratchpad_list(path)
        )

    @tool("scratchpad_search")
    def scratchpad_search(
        query: str,
        scope: str = ".",
        limit: int = 20,
    ) -> str:
        """Search DateGPT working-memory files."""

        return _json(
            filesystem.scratchpad_search(
                query,
                scope=scope,
                limit=limit,
            )
        )

    @tool("scratchpad_write")
    def scratchpad_write(
        path: str,
        content: str,
    ) -> str:
        """Create or replace working memory.

        During original-character onboarding, keep the current character draft
        at onboarding/main_character.md. This is not canonical Save state until
        the user explicitly finalizes onboarding.
        """

        return filesystem.scratchpad_write(
            path,
            content,
        )

    @tool("scratchpad_delete")
    def scratchpad_delete(path: str) -> str:
        """Delete one obsolete working-memory file."""

        return filesystem.scratchpad_delete(path)

    return [
        scratchpad_read,
        scratchpad_list,
        scratchpad_search,
        scratchpad_write,
        scratchpad_delete,
    ]


def _tool_decorator():
    try:
        from langchain.tools import tool
    except ImportError as exc:
        raise RuntimeError(
            "LangChain is required to build agent tools. "
            "Install BACKEND/requirements.txt."
        ) from exc
    return tool


def _json(value) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
    )
