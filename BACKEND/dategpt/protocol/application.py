from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional

from ..agent import AgentRunner
from ..bootstrap import (
    GameInstanceSelectionRequired,
    InitializationResult,
    ScenarioSourceConflict,
    SessionInitializer,
    UnknownGameInstance,
)
from ..controls import ControlRouter, ControlState
from ..host import RuntimeHost
from ..models import (
    ModelFactory,
    ModelNotConfigured,
    ModelSettingsRouter,
    ModelSettingsStore,
)
from ..prompts import PromptBundle
from ..scenarios import ScenarioPack
from .errors import ProtocolError


@dataclass
class ActiveSession:
    """The one and only mounted runtime session in a backend process."""

    scenario: ScenarioPack
    initialization: InitializationResult
    host: RuntimeHost
    runner: Any

    @property
    def workspace(self):
        return self.initialization.workspace

    @property
    def needs_setup(self) -> bool:
        return self.initialization.needs_setup


class BackendApplication:
    """Single-active-session application protocol for the Ren'Py frontend."""

    def __init__(
        self,
        *,
        backend_dir: Path,
        model_settings_store: Optional[ModelSettingsStore] = None,
        runner_factory: Optional[Callable[[RuntimeHost, Callable[[], Any]], Any]] = None,
    ) -> None:
        self.backend_dir = Path(backend_dir).expanduser().resolve()

        self.config_dir = _env_path(
            "DATEGPT_CONFIG_DIR",
            self.backend_dir / "user_data" / "config",
        )
        self.save_base = _env_path(
            "DATEGPT_SAVE_DIR",
            self.backend_dir / "user_data" / "games",
        )
        self.runtime_base = _env_path(
            "DATEGPT_RUNTIME_DIR",
            self.backend_dir / "user_data" / "runtime",
        )

        self.model_settings_store = (
            model_settings_store
            or ModelSettingsStore(
                self.config_dir / "model_settings.json"
            )
        )
        self.model_router = ModelSettingsRouter(
            self.model_settings_store
        )
        self.model_factory = ModelFactory(
            self.model_settings_store
        )

        # Commands entered before a game is opened still have deterministic
        # defaults. Once a session is active, its own ControlRouter takes over.
        self.default_controls = ControlState()
        self.default_control_router = ControlRouter(
            self.default_controls
        )

        self.initializer = SessionInitializer(
            save_base=self.save_base,
            runtime_base=self.runtime_base,
        )
        self.runner_factory = runner_factory or _default_runner_factory
        self.active_session: Optional[ActiveSession] = None

    def handle(
        self,
        message: Mapping[str, Any],
        *,
        emit: Optional[Callable[[dict], None]] = None,
    ) -> List[dict]:
        request_id = message.get("request_id")
        message_type = str(message.get("type", "")).strip()

        try:
            if message_type == "ping":
                return [
                    _event(
                        "reply",
                        request_id,
                        text="pong — 백엔드 살아있음",
                    )
                ]

            if message_type == "open_session":
                return self._open_session(
                    message,
                    request_id=request_id,
                )

            if message_type == "setup_session":
                return self._setup_session(
                    message,
                    request_id=request_id,
                )

            if message_type == "close_session":
                self.active_session = None
                return [
                    _event(
                        "session_closed",
                        request_id,
                    )
                ]

            if message_type == "get_session_state":
                return [
                    self._session_state_event(
                        request_id=request_id,
                    )
                ]

            model_response = self.model_router.try_handle_message(
                message
            )
            if model_response.handled:
                events = []
                if model_response.settings is not None:
                    events.append(
                        _event(
                            "model_settings",
                            request_id,
                            settings=model_response.settings,
                        )
                    )
                events.append(
                    _event(
                        "reply",
                        request_id,
                        text=model_response.message,
                    )
                )
                return events

            control_router = self._current_control_router()
            control_response = control_router.try_handle_message(
                message
            )
            if control_response.handled:
                events = []
                if control_response.controls is not None:
                    events.append(
                        _event(
                            "control_state",
                            request_id,
                            controls=control_response.controls,
                        )
                    )
                events.append(
                    _event(
                        "reply",
                        request_id,
                        text=control_response.message,
                    )
                )
                return events

            # Current Ren'Py text input can continue to send "say"; it is a
            # compatibility alias for "play". New protocol callers should use
            # "play" explicitly.
            if message_type in {"play", "say"}:
                return self._play(
                    message,
                    request_id=request_id,
                    emit=emit,
                )

            if message_type == "checkpoint":
                return self._checkpoint(
                    request_id=request_id,
                    emit=emit,
                )

            raise ProtocolError(
                "PROTOCOL_ERROR",
                "알 수 없는 message type: {}".format(
                    message_type or "(empty)"
                ),
            )

        except ProtocolError as exc:
            return [exc.event(request_id)]
        except GameInstanceSelectionRequired as exc:
            return [
                _event(
                    "instance_selection_required",
                    request_id,
                    game_ids=list(exc.game_ids),
                )
            ]
        except UnknownGameInstance:
            return [
                ProtocolError(
                    "UNKNOWN_GAME_INSTANCE",
                    "요청한 GAME_ID를 찾을 수 없습니다.",
                ).event(request_id)
            ]
        except ScenarioSourceConflict as exc:
            return [
                ProtocolError(
                    "SCENARIO_SOURCE_CONFLICT",
                    str(exc),
                ).event(request_id)
            ]
        except ModelNotConfigured as exc:
            return [
                ProtocolError(
                    "MODEL_NOT_CONFIGURED",
                    str(exc),
                ).event(request_id)
            ]
        except FileNotFoundError as exc:
            return [
                ProtocolError(
                    "FILE_NOT_FOUND",
                    str(exc),
                ).event(request_id)
            ]
        except ValueError as exc:
            return [
                ProtocolError(
                    "INVALID_REQUEST",
                    str(exc),
                ).event(request_id)
            ]
        except Exception as exc:
            return [
                ProtocolError(
                    "BACKEND_ERROR",
                    "{}: {}".format(
                        type(exc).__name__,
                        exc,
                    ),
                ).event(request_id)
            ]

    def _open_session(
        self,
        message: Mapping[str, Any],
        *,
        request_id,
    ) -> List[dict]:
        scenario_path = _message_or_env_path(
            message,
            "scenario_path",
            "DATEGPT_SCENARIO_DIR",
        )
        prompt_path = _message_or_env_path(
            message,
            "prompt_path",
            "DATEGPT_PROMPT_DIR",
        )

        scenario = ScenarioPack(scenario_path)
        prompt_bundle = PromptBundle(prompt_path)

        result = self.initializer.prepare(
            scenario,
            distribution_url=str(
                message.get("distribution_url", "")
            ).strip(),
            manifest_url=str(
                message.get("manifest_url", "")
            ).strip(),
            requested_game_id=(
                str(message["game_id"]).strip()
                if message.get("game_id") is not None
                else None
            ),
            new_game=bool(message.get("new_game", False)),
        )

        host = RuntimeHost(
            prompt_bundle=prompt_bundle,
            scenario=scenario,
            workspace=result.workspace,
            controls=result.controls,
        )
        runner = self.runner_factory(
            host,
            self.model_factory.create,
        )

        # v1 intentionally hard-codes exactly one active session. A successful
        # open atomically replaces the previous mounted game.
        self.active_session = ActiveSession(
            scenario=scenario,
            initialization=result,
            host=host,
            runner=runner,
        )

        return [
            _event(
                "session_opened",
                request_id,
                game_name=result.game_name,
                game_id=result.game_id,
                is_new=result.is_new,
                needs_setup=result.needs_setup,
                controls=result.controls.snapshot(),
                has_welcome=result.welcome_text is not None,
            )
        ]

    def _setup_session(
        self,
        message: Mapping[str, Any],
        *,
        request_id,
    ) -> List[dict]:
        session = self._require_session()

        if not session.needs_setup:
            raise ProtocolError(
                "SESSION_ALREADY_SETUP",
                "현재 세션은 이미 초기 설정이 완료되어 있습니다.",
            )

        self._apply_controls(
            session.host,
            message.get("controls"),
        )

        init_complete = self.initializer.finalize_new_game(
            session.initialization,
            play_mode=str(
                message.get("play_mode", "")
            ).strip(),
            player_character_mode=str(
                message.get("player_character_mode", "")
            ).strip(),
            main_character=str(
                message.get("main_character", "")
            ).strip(),
            current=_string_mapping(
                message.get("current", {})
            ),
            controls=session.host.controls,
        )

        return [
            _event(
                "session_setup_complete",
                request_id,
                game_name=init_complete.game_name,
                game_id=init_complete.game_id,
                controls=session.host.controls.snapshot(),
            )
        ]

    def _play(
        self,
        message: Mapping[str, Any],
        *,
        request_id,
        emit: Optional[Callable[[dict], None]],
    ) -> List[dict]:
        session = self._require_session()
        if session.needs_setup:
            raise ProtocolError(
                "SESSION_NEEDS_SETUP",
                "새 플레이의 모드 설정이 먼저 필요합니다.",
            )

        self._apply_controls(
            session.host,
            message.get("controls"),
        )

        text = str(message.get("text", ""))
        if not text.strip():
            raise ProtocolError(
                "INVALID_REQUEST",
                "play.text가 비어 있습니다.",
            )

        if emit is not None:
            emit(
                _event(
                    "status",
                    request_id,
                    message="메세지 처리중...",
                )
            )

        result = session.runner.run_turn(text)

        return [
            _event(
                "reply",
                request_id,
                text=result.text,
            )
        ]

    def _checkpoint(
        self,
        *,
        request_id,
        emit: Optional[Callable[[dict], None]],
    ) -> List[dict]:
        session = self._require_session()
        if session.needs_setup:
            raise ProtocolError(
                "SESSION_NEEDS_SETUP",
                "초기 설정이 끝나기 전에는 저장할 수 없습니다.",
            )

        if emit is not None:
            emit(
                _event(
                    "status",
                    request_id,
                    message="저장 정리 중...",
                )
            )

        result = session.runner.run_maintenance("!저장")
        return [
            _event(
                "checkpoint_complete",
                request_id,
                text=result.text,
            )
        ]

    def _session_state_event(self, *, request_id) -> dict:
        if self.active_session is None:
            return _event(
                "session_state",
                request_id,
                active=False,
            )

        session = self.active_session
        return _event(
            "session_state",
            request_id,
            active=True,
            game_name=session.initialization.game_name,
            game_id=session.initialization.game_id,
            needs_setup=session.needs_setup,
            controls=session.host.controls.snapshot(),
        )

    def _current_control_router(self) -> ControlRouter:
        if self.active_session is not None:
            return self.active_session.host.control_router
        return self.default_control_router

    def _apply_controls(
        self,
        host: RuntimeHost,
        raw_controls,
    ) -> None:
        if raw_controls is None:
            return
        if not isinstance(raw_controls, Mapping):
            raise ProtocolError(
                "INVALID_CONTROL",
                "controls는 JSON object여야 합니다.",
            )

        for name, value in raw_controls.items():
            try:
                host.controls.set(str(name), value)
            except ValueError as exc:
                raise ProtocolError(
                    "INVALID_CONTROL",
                    str(exc),
                ) from exc

        host.workspace.save_controls(
            host.controls.snapshot()
        )

    def _require_session(self) -> ActiveSession:
        if self.active_session is None:
            raise ProtocolError(
                "NO_ACTIVE_SESSION",
                "먼저 open_session을 호출해 주세요.",
            )
        return self.active_session


def _default_runner_factory(
    host: RuntimeHost,
    model_factory: Callable[[], Any],
):
    return AgentRunner(
        host=host,
        model_factory=model_factory,
    )


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name, "").strip()
    return Path(value or default).expanduser().resolve()


def _message_or_env_path(
    message: Mapping[str, Any],
    message_key: str,
    env_key: str,
) -> Path:
    value = str(message.get(message_key, "")).strip()
    if not value:
        value = os.environ.get(env_key, "").strip()
    if not value:
        raise ProtocolError(
            "PATH_NOT_CONFIGURED",
            "{} 또는 {} 설정이 필요합니다.".format(
                message_key,
                env_key,
            ),
        )
    return Path(value).expanduser().resolve()


def _event(event_type: str, request_id=None, **payload) -> dict:
    event = {"type": event_type}
    if request_id is not None:
        event["request_id"] = request_id
    event.update(payload)
    return event


def _string_mapping(value) -> Dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ProtocolError(
            "INVALID_REQUEST",
            "current는 JSON object여야 합니다.",
        )
    return {
        str(key): str(item)
        for key, item in value.items()
    }
