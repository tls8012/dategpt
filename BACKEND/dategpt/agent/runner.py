from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional

from ..host import RuntimeHost, TurnContext
from .filesystem import AgentFilesystem
from .tools import build_langchain_tools


@dataclass(frozen=True)
class AgentRunResult:
    text: str
    prompt_fingerprint: str
    raw_result: Any


class AgentRunner:
    """Run one stateless DateGPT player turn through a LangChain agent loop."""

    def __init__(
        self,
        *,
        host: RuntimeHost,
        model: Any = None,
        model_factory: Optional[Callable[[], Any]] = None,
        agent_factory: Optional[Callable[..., Any]] = None,
        tool_factory: Optional[Callable[[AgentFilesystem], List[object]]] = None,
    ) -> None:
        if model is None and model_factory is None:
            raise ValueError("model or model_factory is required")
        if model is not None and model_factory is not None:
            raise ValueError("provide model or model_factory, not both")

        self.host = host
        self.model = model
        self.model_factory = model_factory
        self.agent_factory = agent_factory or _default_agent_factory
        self.tool_factory = tool_factory or build_langchain_tools

    def run_turn(
        self,
        user_input: str,
        *,
        history_limit: int = 20,
    ) -> AgentRunResult:
        turn = self.host.begin_turn(
            user_input,
            history_limit=history_limit,
        )
        return self.run_context(
            turn,
            record_history=True,
        )

    def run_maintenance(
        self,
        instruction: str,
        *,
        history_limit: int = 20,
    ) -> AgentRunResult:
        """Run an explicit engine/user maintenance command without chat history append."""

        turn = self.host.begin_turn(
            instruction,
            history_limit=history_limit,
        )
        return self.run_context(
            turn,
            record_history=False,
        )

    def run_context(
        self,
        turn: TurnContext,
        *,
        record_history: bool = True,
    ) -> AgentRunResult:
        if self.host.scenario is None:
            raise RuntimeError("scenario pack is not mounted")
        if self.host.workspace is None:
            raise RuntimeError("session workspace is not mounted")

        filesystem = AgentFilesystem(
            scenario=self.host.scenario,
            workspace=self.host.workspace,
        )
        tools = self.tool_factory(filesystem)
        model = (
            self.model_factory()
            if self.model_factory is not None
            else self.model
        )

        agent = self.agent_factory(
            model=model,
            tools=tools,
            system_prompt=turn.system_prompt,
        )

        messages = _build_messages(turn)
        raw_result = agent.invoke({"messages": messages})
        text = _extract_final_text(raw_result)

        if record_history:
            self.host.workspace.history.append(
                {
                    "role": "user",
                    "text": turn.user_input,
                    "prompt_fingerprint": turn.prompt_fingerprint,
                }
            )
            self.host.workspace.history.append(
                {
                    "role": "assistant",
                    "text": text,
                    "prompt_fingerprint": turn.prompt_fingerprint,
                }
            )

        return AgentRunResult(
            text=text,
            prompt_fingerprint=turn.prompt_fingerprint,
            raw_result=raw_result,
        )


def _default_agent_factory(**kwargs):
    try:
        from langchain.agents import create_agent
    except ImportError as exc:
        raise RuntimeError(
            "LangChain is required to run the agent. "
            "Install BACKEND/requirements.txt."
        ) from exc
    return create_agent(**kwargs)


def _build_messages(turn: TurnContext) -> List[Dict[str, Any]]:
    messages: List[Dict[str, Any]] = []

    scratchpad_text = _serialize_scratchpad(turn.scratchpad)
    if scratchpad_text:
        messages.append(
            {
                "role": "system",
                "content": (
                    "# DATEGPT SESSION SCRATCHPAD\n"
                    "This is revisable working memory, not canonical world truth.\n\n"
                    + scratchpad_text
                ),
            }
        )

    for record in turn.recent_history:
        role = str(record.get("role", "")).strip()
        if role not in {"user", "assistant"}:
            continue
        content = record.get("text", record.get("content", ""))
        if not isinstance(content, str) or not content:
            continue
        messages.append(
            {
                "role": role,
                "content": content,
            }
        )

    messages.append(
        {
            "role": "user",
            "content": turn.user_input,
        }
    )
    return messages


def _serialize_scratchpad(scratchpad: Dict[str, str]) -> str:
    if not scratchpad:
        return ""

    chunks = []
    for path in sorted(scratchpad):
        chunks.append(
            "## {}\n{}".format(
                path,
                scratchpad[path],
            )
        )
    return "\n\n".join(chunks)


def _extract_final_text(result: Any) -> str:
    if isinstance(result, dict):
        messages = result.get("messages")
        if isinstance(messages, Iterable) and not isinstance(messages, (str, bytes)):
            for message in reversed(list(messages)):
                text = _message_text(message)
                if text:
                    return text

        structured = result.get("structured_response")
        if structured is not None:
            return str(structured)

    text = _message_text(result)
    if text:
        return text

    raise RuntimeError("agent returned no textual final response")


def _message_text(message: Any) -> str:
    if message is None:
        return ""

    if isinstance(message, dict):
        role = message.get("role")
        if role not in {None, "assistant"}:
            return ""
        return _content_text(message.get("content"))

    message_type = getattr(message, "type", None)
    if message_type not in {None, "ai", "assistant"}:
        return ""

    text_property = getattr(message, "text", None)
    if isinstance(text_property, str) and text_property:
        return text_property

    return _content_text(getattr(message, "content", None))


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        pieces = []
        for block in content:
            if isinstance(block, str):
                pieces.append(block)
                continue
            if not isinstance(block, dict):
                continue
            if block.get("type") in {"text", "output_text"}:
                value = block.get("text", block.get("content", ""))
                if isinstance(value, str):
                    pieces.append(value)
        return "\n".join(piece for piece in pieces if piece).strip()

    return ""
