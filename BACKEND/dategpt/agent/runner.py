from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple

from ..workspace import TurnTransaction

from ..host import RuntimeHost, TurnContext
from ..presentation import VNResponse, coerce_vn_response
from .filesystem import AgentFilesystem
from .tools import (
    build_langchain_tools,
    build_onboarding_tools,
)


@dataclass(frozen=True)
class AgentRunResult:
    text: str
    prompt_fingerprint: str
    raw_result: Any
    segments: Tuple[Dict[str, str], ...] = ()


class AgentRunner:
    """One-turn LangChain harness with DateGPT-owned cross-turn memory."""

    def __init__(
        self,
        *,
        host: RuntimeHost,
        model: Any = None,
        model_factory: Optional[Callable[[], Any]] = None,
        agent_factory: Optional[Callable[..., Any]] = None,
        tool_factory: Optional[Callable[[AgentFilesystem], List[object]]] = None,
        onboarding_tool_factory: Optional[
            Callable[[AgentFilesystem], List[object]]
        ] = None,
    ) -> None:
        if model is None and model_factory is None:
            raise ValueError(
                "model or model_factory is required"
            )
        if model is not None and model_factory is not None:
            raise ValueError(
                "provide model or model_factory, not both"
            )

        self.host = host
        self.model = model
        self.model_factory = model_factory
        self.agent_factory = (
            agent_factory or _default_agent_factory
        )
        self.tool_factory = (
            tool_factory or build_langchain_tools
        )
        self.onboarding_tool_factory = (
            onboarding_tool_factory
            or build_onboarding_tools
        )

    def run_turn(
        self,
        user_input: str,
        *,
        history_limit: int = 20,
    ) -> AgentRunResult:
        if self.host.workspace is None:
            raise RuntimeError(
                "session workspace is not mounted"
            )
        transaction = (
            self.host.workspace.turns.begin()
        )
        try:
            turn = self.host.begin_turn(
                user_input,
                history_limit=history_limit,
            )
            return self.run_context(
                turn,
                record_history=True,
                tool_factory=self.tool_factory,
                transaction=transaction,
                transaction_mode="turn",
                structured_output=True,
            )
        except Exception:
            transaction.rollback_uncommitted()
            raise

    def run_onboarding_turn(
        self,
        user_input: str,
        *,
        welcome_text: Optional[str],
        onboarding_state: Mapping[str, object],
        history_limit: int = 20,
        record_history: bool = True,
    ) -> AgentRunResult:
        turn = self.host.begin_onboarding_turn(
            user_input,
            welcome_text=welcome_text,
            onboarding_state=onboarding_state,
            history_limit=history_limit,
        )
        return self.run_context(
            turn,
            record_history=record_history,
            tool_factory=(
                self.onboarding_tool_factory
            ),
            structured_output=True,
        )

    def run_maintenance(
        self,
        instruction: str,
        *,
        history_limit: int = 20,
    ) -> AgentRunResult:
        if self.host.workspace is None:
            raise RuntimeError(
                "session workspace is not mounted"
            )
        transaction = (
            self.host.workspace.turns.begin()
        )
        try:
            turn = self.host.begin_turn(
                instruction,
                history_limit=history_limit,
            )
            return self.run_context(
                turn,
                record_history=False,
                tool_factory=self.tool_factory,
                transaction=transaction,
                transaction_mode="amend",
                structured_output=False,
            )
        except Exception:
            transaction.rollback_uncommitted()
            raise

    def run_context(
        self,
        turn: TurnContext,
        *,
        record_history: bool,
        tool_factory,
        transaction: Optional[TurnTransaction] = None,
        transaction_mode: Optional[str] = None,
        structured_output: bool = False,
    ) -> AgentRunResult:
        if self.host.scenario is None:
            raise RuntimeError(
                "scenario pack is not mounted"
            )
        if self.host.workspace is None:
            raise RuntimeError(
                "session workspace is not mounted"
            )

        filesystem = AgentFilesystem(
            scenario=self.host.scenario,
            workspace=self.host.workspace,
            transaction=transaction,
        )
        tools = tool_factory(filesystem)
        model = (
            self.model_factory()
            if self.model_factory is not None
            else self.model
        )

        agent_kwargs = {
            "model": model,
            "tools": tools,
            "system_prompt": turn.system_prompt,
        }
        if structured_output:
            agent_kwargs["response_format"] = VNResponse

        agent = self.agent_factory(**agent_kwargs)

        messages = _build_messages(turn)
        raw_result = agent.invoke(
            {"messages": messages}
        )

        segments: Tuple[Dict[str, str], ...] = ()
        if structured_output:
            response = _extract_structured_response(
                raw_result
            )
            text = response.plain_text()
            segments = tuple(
                response.public_segments()
            )
        else:
            text = _extract_final_text(raw_result)

        if record_history:
            self._record_exchange(
                turn,
                text,
                segments=segments,
            )

        if transaction is not None:
            if transaction_mode == "turn":
                transaction.commit(
                    user_text=turn.user_input,
                    assistant_text=text,
                    prompt_fingerprint=(
                        turn.prompt_fingerprint
                    ),
                )
            elif transaction_mode == "amend":
                transaction.amend_latest()
            else:
                raise ValueError(
                    "invalid transaction_mode"
                )

        return AgentRunResult(
            text=text,
            prompt_fingerprint=(
                turn.prompt_fingerprint
            ),
            raw_result=raw_result,
            segments=segments,
        )

    def record_assistant_message(
        self,
        text: str,
        *,
        prompt_fingerprint: str,
        phase: str,
        segments: Tuple[Dict[str, str], ...] = (),
    ) -> None:
        record = {
            "role": "assistant",
            "text": text,
            "prompt_fingerprint": (
                prompt_fingerprint
            ),
            "phase": phase,
        }
        if segments:
            record["segments"] = [
                dict(item) for item in segments
            ]
        self.host.workspace.history.append(record)

    def _record_exchange(
        self,
        turn: TurnContext,
        text: str,
        *,
        segments: Tuple[Dict[str, str], ...] = (),
    ) -> None:
        self.host.workspace.history.append(
            {
                "role": "user",
                "text": turn.user_input,
                "prompt_fingerprint": (
                    turn.prompt_fingerprint
                ),
            }
        )
        assistant_record = {
            "role": "assistant",
            "text": text,
            "prompt_fingerprint": (
                turn.prompt_fingerprint
            ),
        }
        if segments:
            assistant_record["segments"] = [
                dict(item) for item in segments
            ]
        self.host.workspace.history.append(
            assistant_record
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


def _build_messages(
    turn: TurnContext,
) -> List[Dict[str, Any]]:
    messages: List[Dict[str, Any]] = list(
        turn.context_messages
    )

    for record in turn.recent_history:
        role = str(
            record.get("role", "")
        ).strip()
        if role not in {"user", "assistant"}:
            continue
        content = record.get(
            "text",
            record.get("content", ""),
        )
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


def _extract_structured_response(
    result: Any,
) -> VNResponse:
    if not isinstance(result, dict):
        raise RuntimeError(
            "agent structured output state must be a mapping"
        )

    structured = result.get(
        "structured_response"
    )
    if structured is None:
        raise RuntimeError(
            "agent returned no structured_response"
        )

    return coerce_vn_response(structured)


def _extract_final_text(result: Any) -> str:
    if isinstance(result, dict):
        messages = result.get("messages")
        if (
            isinstance(messages, Iterable)
            and not isinstance(
                messages,
                (str, bytes),
            )
        ):
            for message in reversed(
                list(messages)
            ):
                text = _message_text(message)
                if text:
                    return text

        structured = result.get(
            "structured_response"
        )
        if structured is not None:
            return str(structured)

    text = _message_text(result)
    if text:
        return text

    raise RuntimeError(
        "agent returned no textual final response"
    )


def _message_text(message: Any) -> str:
    if message is None:
        return ""

    if isinstance(message, dict):
        role = message.get("role")
        if role not in {None, "assistant"}:
            return ""
        return _content_text(
            message.get("content")
        )

    message_type = getattr(
        message,
        "type",
        None,
    )
    if message_type not in {
        None,
        "ai",
        "assistant",
    }:
        return ""

    text_property = getattr(
        message,
        "text",
        None,
    )
    if (
        isinstance(text_property, str)
        and text_property
    ):
        return text_property

    return _content_text(
        getattr(message, "content", None)
    )


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
            if block.get("type") in {
                "text",
                "output_text",
            }:
                value = block.get(
                    "text",
                    block.get("content", ""),
                )
                if isinstance(value, str):
                    pieces.append(value)

        return "\n".join(
            piece
            for piece in pieces
            if piece
        ).strip()

    return ""
