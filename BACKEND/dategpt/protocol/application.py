from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional

from ..agent import AgentRunner
from ..bootstrap import (
    GameInstanceSelectionRequired,
    InitializationResult,
    SessionInitializer,
    UnknownGameInstance,
)
from ..cartridges import CartridgeLibrary
from ..controls import ControlRouter, ControlState
from ..host import RuntimeHost
from ..models import (
    ModelFactory,
    ModelNotConfigured,
    ModelSettingsRouter,
    ModelSettingsStore,
)
from ..onboarding import (
    CharacterDraftMissing,
    OnboardingController,
)
from ..prompts import PromptBundle
from ..scenarios import ScenarioPack
from ..sources import GitHubSourceResolver
from .errors import ProtocolError


@dataclass
class ActiveSession:
    """The one and only mounted runtime session in a backend process."""

    scenario: ScenarioPack
    initialization: InitializationResult
    host: RuntimeHost
    runner: Any
    onboarding: OnboardingController

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
        runner_factory: Optional[
            Callable[[RuntimeHost, Callable[[], Any]], Any]
        ] = None,
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
        self.cartridge_base = _env_path(
            "DATEGPT_CARTRIDGE_DIR",
            self.backend_dir / "user_data" / "cartridges",
        )
        self.cartridges = CartridgeLibrary(
            self.cartridge_base
        )
        self.source_cache_base = _env_path(
            "DATEGPT_SOURCE_CACHE_DIR",
            self.backend_dir / "user_data" / "sources",
        )
        self.sources = GitHubSourceResolver(
            self.source_cache_base
        )
        self.bundled_prompt_dir = (
            self.backend_dir.parent / ".scaffolding"
        ).resolve()

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

        self.default_controls = ControlState()
        self.default_control_router = ControlRouter(
            self.default_controls
        )

        self.initializer = SessionInitializer(
            save_base=self.save_base,
            runtime_base=self.runtime_base,
        )
        self.runner_factory = (
            runner_factory or _default_runner_factory
        )
        self.active_session: Optional[ActiveSession] = None

    def handle(
        self,
        message: Mapping[str, Any],
        *,
        emit: Optional[Callable[[dict], None]] = None,
    ) -> List[dict]:
        request_id = message.get("request_id")
        message_type = str(
            message.get("type", "")
        ).strip()

        try:
            if message_type == "ping":
                return [
                    _event(
                        "reply",
                        request_id,
                        text="pong — 백엔드 살아있음",
                    )
                ]

            if message_type == "install_cartridge":
                return self._install_cartridge(
                    message,
                    request_id=request_id,
                    emit=emit,
                )

            if message_type == "list_cartridges":
                return [
                    _event(
                        "cartridge_list",
                        request_id,
                        cartridges=[
                            item.public_dict()
                            for item in self.cartridges.list_installed()
                        ],
                    )
                ]

            if message_type == "list_game_instances":
                game_name = str(
                    message.get("game_name", "")
                ).strip()
                if not game_name:
                    raise ProtocolError(
                        "INVALID_REQUEST",
                        "list_game_instances.game_name이 필요합니다.",
                    )
                return [
                    _event(
                        "game_instance_list",
                        request_id,
                        game_name=game_name,
                        game_ids=list(
                            self.initializer.list_instance_ids(
                                game_name
                            )
                        ),
                    )
                ]

            if message_type == "open_session":
                return self._open_session(
                    message,
                    request_id=request_id,
                    emit=emit,
                )

            if message_type == "setup_session":
                return self._setup_session(
                    message,
                    request_id=request_id,
                )

            if message_type == "onboarding_start":
                return self._onboarding_start(
                    request_id=request_id,
                    emit=emit,
                )

            if message_type == "onboarding_select_mode":
                return self._onboarding_select_mode(
                    message,
                    request_id=request_id,
                )

            if message_type == "onboarding_turn":
                return self._onboarding_turn(
                    message,
                    request_id=request_id,
                    emit=emit,
                )

            if message_type == "onboarding_finalize":
                return self._onboarding_finalize(
                    request_id=request_id,
                )

            if message_type == "get_onboarding_state":
                session = self._require_session()
                return [
                    _event(
                        "onboarding_state",
                        request_id,
                        state=session.onboarding.public_state(),
                    )
                ]

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

            model_response = (
                self.model_router.try_handle_message(
                    message
                )
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
            control_response = (
                control_router.try_handle_message(
                    message
                )
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
        except CharacterDraftMissing as exc:
            return [
                ProtocolError(
                    "CHARACTER_DRAFT_MISSING",
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

    def _install_cartridge(
        self,
        message: Mapping[str, Any],
        *,
        request_id,
        emit: Optional[Callable[[dict], None]],
    ) -> List[dict]:
        source_value = str(
            message.get(
                "source",
                message.get("source_path", ""),
            )
        ).strip()
        if not source_value:
            raise ProtocolError(
                "INVALID_REQUEST",
                "install_cartridge.source가 필요합니다.",
            )

        if _is_github_url(source_value):
            if emit is not None:
                emit(
                    _event(
                        "status",
                        request_id,
                        message="GitHub 카트리지 소스 동기화 중...",
                    )
                )
            source_path = self.sources.materialize(
                source_value,
                refresh=True,
            )
        else:
            source_path = Path(
                source_value
            ).expanduser().resolve()

        installed = self.cartridges.install_directory(
            source_path,
            replace=bool(
                message.get("replace", False)
            ),
        )
        return [
            _event(
                "cartridge_installed",
                request_id,
                cartridge=installed.public_dict(),
            )
        ]

    def _open_session(
        self,
        message: Mapping[str, Any],
        *,
        request_id,
        emit: Optional[Callable[[dict], None]],
    ) -> List[dict]:
        scenario_path = self._resolve_scenario_path(
            message
        )
        prompt_path = self._resolve_prompt_path(
            message,
            request_id=request_id,
            emit=emit,
        )

        scenario = ScenarioPack(scenario_path)
        prompt_bundle = PromptBundle(prompt_path)

        result = self.initializer.prepare(
            scenario,
            requested_game_id=(
                str(message["game_id"]).strip()
                if message.get("game_id") is not None
                else None
            ),
            new_game=bool(
                message.get("new_game", False)
            ),
        )

        host = RuntimeHost(
            prompt_bundle=prompt_bundle,
            scenario=scenario,
            workspace=result.workspace,
            controls=result.controls,
            init_complete=result.init_complete,
        )
        runner = self.runner_factory(
            host,
            self.model_factory.create,
        )
        onboarding = OnboardingController(
            initializer=self.initializer,
            initialization=result,
            host=host,
            scenario=scenario,
        )

        self.active_session = ActiveSession(
            scenario=scenario,
            initialization=result,
            host=host,
            runner=runner,
            onboarding=onboarding,
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
                has_welcome=(
                    result.welcome_text is not None
                ),
                onboarding=(
                    onboarding.public_state()
                ),
                build_version=(
                    result.manifest.build_version
                ),
                format_version=(
                    result.manifest.format_version
                ),
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

        init_complete = (
            self.initializer.finalize_new_game(
                session.initialization,
                play_mode=str(
                    message.get("play_mode", "")
                ).strip(),
                player_character_mode=str(
                    message.get(
                        "player_character_mode",
                        "",
                    )
                ).strip(),
                main_character=str(
                    message.get(
                        "main_character",
                        "",
                    )
                ).strip(),
                current=_string_mapping(
                    message.get("current", {})
                ),
                controls=session.host.controls,
            )
        )
        session.host.set_init_complete(
            init_complete
        )
        session.onboarding.mark_complete(
            init_complete
        )

        return [
            _event(
                "session_setup_complete",
                request_id,
                game_name=init_complete.game_name,
                game_id=init_complete.game_id,
                controls=(
                    session.host.controls.snapshot()
                ),
            )
        ]

    def _onboarding_start(
        self,
        *,
        request_id,
        emit: Optional[Callable[[dict], None]],
    ) -> List[dict]:
        session = self._require_setup_session()
        self._require_onboarding_prompt(session)

        session.onboarding.start()

        if emit is not None:
            emit(
                _event(
                    "status",
                    request_id,
                    message="새 플레이를 준비 중...",
                )
            )

        result = session.runner.run_onboarding_turn(
            "BEGIN_ONBOARDING",
            welcome_text=(
                session.initialization.welcome_text
            ),
            onboarding_state=(
                session.onboarding.public_state()
            ),
            record_history=False,
        )
        session.runner.record_assistant_message(
            result.text,
            prompt_fingerprint=(
                result.prompt_fingerprint
            ),
            phase="onboarding",
        )

        return [
            _event(
                "reply",
                request_id,
                text=result.text,
                phase="onboarding",
                onboarding=(
                    session.onboarding.public_state()
                ),
            )
        ]

    def _onboarding_select_mode(
        self,
        message: Mapping[str, Any],
        *,
        request_id,
    ) -> List[dict]:
        session = self._require_setup_session()
        state = session.onboarding.select_mode(
            str(message.get("mode", "")),
            main_character=message.get(
                "main_character"
            ),
        )

        return [
            _event(
                "onboarding_state",
                request_id,
                state=session.onboarding.public_state(),
            ),
            _event(
                "reply",
                request_id,
                text=_mode_selected_message(
                    state.player_character_mode
                ),
                phase="onboarding",
            ),
        ]

    def _onboarding_turn(
        self,
        message: Mapping[str, Any],
        *,
        request_id,
        emit: Optional[Callable[[dict], None]],
    ) -> List[dict]:
        session = self._require_setup_session()
        self._require_onboarding_prompt(session)

        text = str(
            message.get("text", "")
        ).strip()
        if not text:
            raise ProtocolError(
                "INVALID_REQUEST",
                "onboarding_turn.text가 비어 있습니다.",
            )

        session.onboarding.start()

        if emit is not None:
            emit(
                _event(
                    "status",
                    request_id,
                    message="캐릭터 생성 중...",
                )
            )

        result = session.runner.run_onboarding_turn(
            text,
            welcome_text=(
                session.initialization.welcome_text
            ),
            onboarding_state=(
                session.onboarding.public_state()
            ),
        )

        return [
            _event(
                "reply",
                request_id,
                text=result.text,
                phase="onboarding",
                onboarding=(
                    session.onboarding.public_state()
                ),
            )
        ]

    def _onboarding_finalize(
        self,
        *,
        request_id,
    ) -> List[dict]:
        session = self._require_setup_session()
        init_complete = session.onboarding.finalize()

        return [
            _event(
                "session_setup_complete",
                request_id,
                game_name=init_complete.game_name,
                game_id=init_complete.game_id,
                controls=(
                    session.host.controls.snapshot()
                ),
                onboarding=(
                    session.onboarding.public_state()
                ),
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

        self._apply_controls(
            session.host,
            message.get("controls"),
        )

        text = str(
            message.get("text", "")
        )
        if not text.strip():
            raise ProtocolError(
                "INVALID_REQUEST",
                "play.text가 비어 있습니다.",
            )

        if session.needs_setup:
            return self._route_onboarding_text(
                text,
                request_id=request_id,
                emit=emit,
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

    def _route_onboarding_text(
        self,
        text: str,
        *,
        request_id,
        emit,
    ) -> List[dict]:
        stripped = text.strip()

        if stripped in {
            "!온보딩",
            "!시작",
        }:
            return self._onboarding_start(
                request_id=request_id,
                emit=emit,
            )

        if stripped == "!새캐릭터":
            return self._onboarding_select_mode(
                {"mode": "original"},
                request_id=request_id,
            )

        if stripped == "!관찰자":
            return self._onboarding_select_mode(
                {"mode": "observer"},
                request_id=request_id,
            )

        if stripped.startswith(
            "!기존캐릭터"
        ):
            _, _, path = stripped.partition(" ")
            path = path.strip()
            if not path:
                return [
                    _event(
                        "reply",
                        request_id,
                        text=(
                            "사용법: !기존캐릭터 "
                            "<Distribution entity 경로>"
                        ),
                        phase="onboarding",
                    )
                ]
            return self._onboarding_select_mode(
                {
                    "mode": "existing",
                    "main_character": path,
                },
                request_id=request_id,
            )

        if stripped == "!캐릭터확정":
            return self._onboarding_finalize(
                request_id=request_id,
            )

        return self._onboarding_turn(
            {"text": text},
            request_id=request_id,
            emit=emit,
        )

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
                "온보딩이 끝나기 전에는 저장할 수 없습니다.",
            )

        if emit is not None:
            emit(
                _event(
                    "status",
                    request_id,
                    message="저장 정리 중...",
                )
            )

        result = session.runner.run_maintenance(
            "!저장"
        )
        return [
            _event(
                "checkpoint_complete",
                request_id,
                text=result.text,
            )
        ]

    def _session_state_event(
        self,
        *,
        request_id,
    ) -> dict:
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
            game_name=(
                session.initialization.game_name
            ),
            game_id=(
                session.initialization.game_id
            ),
            needs_setup=session.needs_setup,
            controls=(
                session.host.controls.snapshot()
            ),
            onboarding=(
                session.onboarding.public_state()
            ),
        )

    def _resolve_prompt_path(
        self,
        message: Mapping[str, Any],
        *,
        request_id,
        emit: Optional[Callable[[dict], None]],
    ) -> Path:
        direct = str(
            message.get("prompt_path", "")
        ).strip()
        if direct:
            return Path(
                direct
            ).expanduser().resolve()

        env_path = os.environ.get(
            "DATEGPT_PROMPT_DIR",
            "",
        ).strip()
        if env_path:
            return Path(
                env_path
            ).expanduser().resolve()

        if self.bundled_prompt_dir.is_dir():
            return self.bundled_prompt_dir

        raise ProtocolError(
            "PATH_NOT_CONFIGURED",
            (
                "prompt_path 또는 DATEGPT_PROMPT_DIR가 없고 "
                "동기화된 .scaffolding 디렉터리도 없습니다."
            ),
        )

    def _resolve_scenario_path(
        self,
        message: Mapping[str, Any],
    ) -> Path:
        direct = str(
            message.get("scenario_path", "")
        ).strip()
        if direct:
            return Path(
                direct
            ).expanduser().resolve()

        game_name = str(
            message.get("game_name", "")
        ).strip()
        if game_name:
            build_version = str(
                message.get("build_version", "")
            ).strip() or None
            return self.cartridges.resolve(
                game_name,
                build_version=build_version,
            ).path

        env_path = os.environ.get(
            "DATEGPT_SCENARIO_DIR",
            "",
        ).strip()
        if env_path:
            return Path(
                env_path
            ).expanduser().resolve()

        raise ProtocolError(
            "PATH_NOT_CONFIGURED",
            (
                "scenario_path, game_name 또는 "
                "DATEGPT_SCENARIO_DIR 설정이 필요합니다."
            ),
        )

    def _current_control_router(
        self,
    ) -> ControlRouter:
        if self.active_session is not None:
            return (
                self.active_session.host.control_router
            )
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
                host.controls.set(
                    str(name),
                    value,
                )
            except ValueError as exc:
                raise ProtocolError(
                    "INVALID_CONTROL",
                    str(exc),
                ) from exc

        host.workspace.save_controls(
            host.controls.snapshot()
        )

    def _require_session(
        self,
    ) -> ActiveSession:
        if self.active_session is None:
            raise ProtocolError(
                "NO_ACTIVE_SESSION",
                "먼저 open_session을 호출해 주세요.",
            )
        return self.active_session

    def _require_setup_session(
        self,
    ) -> ActiveSession:
        session = self._require_session()
        if not session.needs_setup:
            raise ProtocolError(
                "SESSION_ALREADY_SETUP",
                "현재 세션은 이미 온보딩이 완료되어 있습니다.",
            )
        return session

    @staticmethod
    def _require_onboarding_prompt(
        session: ActiveSession,
    ) -> None:
        if not session.host.prompt_bundle.has_onboarding():
            raise ProtocolError(
                "ONBOARDING_PROMPT_MISSING",
                "prompt bundle에 onboarding.md가 필요합니다.",
            )


def _default_runner_factory(
    host: RuntimeHost,
    model_factory: Callable[[], Any],
):
    return AgentRunner(
        host=host,
        model_factory=model_factory,
    )


def _env_path(
    name: str,
    default: Path,
) -> Path:
    value = os.environ.get(
        name,
        "",
    ).strip()
    return Path(
        value or default
    ).expanduser().resolve()


def _message_or_env_path(
    message: Mapping[str, Any],
    message_key: str,
    env_key: str,
) -> Path:
    value = str(
        message.get(message_key, "")
    ).strip()
    if not value:
        value = os.environ.get(
            env_key,
            "",
        ).strip()
    if not value:
        raise ProtocolError(
            "PATH_NOT_CONFIGURED",
            "{} 또는 {} 설정이 필요합니다.".format(
                message_key,
                env_key,
            ),
        )
    return Path(
        value
    ).expanduser().resolve()


def _event(
    event_type: str,
    request_id=None,
    **payload,
) -> dict:
    event = {
        "type": event_type,
    }
    if request_id is not None:
        event["request_id"] = request_id
    event.update(payload)
    return event


def _string_mapping(
    value,
) -> Dict[str, str]:
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


def _mode_selected_message(
    mode: Optional[str],
) -> str:
    if mode == "original":
        return (
            "새 캐릭터 모드입니다. "
            "대화로 캐릭터를 만든 뒤 !캐릭터확정을 입력하세요."
        )
    if mode == "existing":
        return (
            "기존 캐릭터 모드가 선택되었습니다. "
            "!캐릭터확정으로 시작할 수 있습니다."
        )
    if mode == "none":
        return (
            "관찰자 모드가 선택되었습니다. "
            "!캐릭터확정으로 시작할 수 있습니다."
        )
    return "온보딩 모드를 선택했습니다."


def _is_github_url(value: str) -> bool:
    text = str(value).strip().casefold()
    return text.startswith("https://github.com/")
