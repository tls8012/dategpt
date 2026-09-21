from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

from .settings import ModelSettingsStore, normalize_provider


@dataclass(frozen=True)
class ModelSettingsResponse:
    handled: bool
    message: str = ""
    settings: Optional[Dict[str, Any]] = None


class ModelSettingsRouter:
    """Deterministic model/API-key commands handled before any LLM call."""

    def __init__(self, store: ModelSettingsStore) -> None:
        self.store = store

    def try_handle_message(
        self,
        message: Mapping[str, Any],
    ) -> ModelSettingsResponse:
        message_type = message.get("type")

        if message_type == "get_model_settings":
            return self._status()

        if message_type == "set_model":
            provider = str(message.get("provider", "")).strip()
            model = str(message.get("model", "")).strip()
            return self._set_model(provider, model)

        if message_type == "set_api_key":
            provider = str(message.get("provider", "")).strip()
            api_key = str(message.get("api_key", ""))
            return self._set_api_key(provider, api_key)

        if message_type == "clear_api_key":
            provider = str(message.get("provider", "")).strip()
            return self._clear_api_key(provider)

        if message_type == "say":
            return self.try_handle_text(
                str(message.get("text", ""))
            )

        return ModelSettingsResponse(False)

    def try_handle_text(self, text: str) -> ModelSettingsResponse:
        stripped = text.strip()
        if not stripped:
            return ModelSettingsResponse(False)

        if stripped == "!모델":
            return self._status()

        if stripped.startswith("!모델 "):
            payload = stripped[len("!모델 "):].strip()
            parts = payload.split(None, 1)
            if len(parts) != 2:
                return self._usage_model()
            return self._set_model(parts[0], parts[1])

        key_command = None
        for command in ("!api_key", "!api키", "!apikey"):
            if stripped == command or stripped.startswith(command + " "):
                key_command = command
                break

        if key_command is None:
            return ModelSettingsResponse(False)

        payload = stripped[len(key_command):].strip()
        if not payload:
            return self._status()

        parts = payload.split(None, 1)
        if len(parts) != 2:
            return self._usage_key()

        provider, value = parts
        if value.strip().casefold() in {
            "삭제",
            "지우기",
            "delete",
            "clear",
            "none",
        }:
            return self._clear_api_key(provider)

        return self._set_api_key(provider, value)

    def _set_model(
        self,
        provider: str,
        model: str,
    ) -> ModelSettingsResponse:
        try:
            settings = self.store.set_model(provider, model)
        except ValueError as exc:
            return ModelSettingsResponse(
                True,
                str(exc),
                self.store.public_snapshot(),
            )

        return ModelSettingsResponse(
            True,
            "모델을 {} / {} 로 설정했습니다.".format(
                settings.provider,
                settings.model,
            ),
            self.store.public_snapshot(settings),
        )

    def _set_api_key(
        self,
        provider: str,
        api_key: str,
    ) -> ModelSettingsResponse:
        try:
            name = normalize_provider(provider)
            settings = self.store.set_api_key(name, api_key)
        except ValueError as exc:
            return ModelSettingsResponse(
                True,
                str(exc),
                self.store.public_snapshot(),
            )

        public = self.store.public_snapshot(settings)
        masked = public["api_keys"][name]["masked"]
        return ModelSettingsResponse(
            True,
            "{} API key를 저장했습니다: {}".format(
                name,
                masked,
            ),
            public,
        )

    def _clear_api_key(
        self,
        provider: str,
    ) -> ModelSettingsResponse:
        try:
            name = normalize_provider(provider)
            settings = self.store.clear_api_key(name)
        except ValueError as exc:
            return ModelSettingsResponse(
                True,
                str(exc),
                self.store.public_snapshot(),
            )

        public = self.store.public_snapshot(settings)
        source = public["api_keys"][name]["source"]
        if source == "environment":
            message = (
                "{}에 저장된 키는 삭제했습니다. "
                "현재는 환경변수 키가 계속 적용됩니다."
            ).format(name)
        else:
            message = "{} API key를 삭제했습니다.".format(name)

        return ModelSettingsResponse(
            True,
            message,
            public,
        )

    def _status(self) -> ModelSettingsResponse:
        public = self.store.public_snapshot()
        lines = [
            "현재 모델: {} / {}".format(
                public["provider"],
                public["model"] or "(미설정)",
            ),
            "API key:",
        ]
        for provider in public["supported_providers"]:
            info = public["api_keys"][provider]
            if info["configured"]:
                lines.append(
                    "- {}: {} ({})".format(
                        provider,
                        info["masked"],
                        info["source"],
                    )
                )
            else:
                lines.append("- {}: 미설정".format(provider))

        return ModelSettingsResponse(
            True,
            "\n".join(lines),
            public,
        )

    def _usage_model(self) -> ModelSettingsResponse:
        return ModelSettingsResponse(
            True,
            "사용법: !모델 <openai|anthropic> <모델명>",
            self.store.public_snapshot(),
        )

    def _usage_key(self) -> ModelSettingsResponse:
        return ModelSettingsResponse(
            True,
            "사용법: !api_key <openai|anthropic> <키|삭제>",
            self.store.public_snapshot(),
        )
