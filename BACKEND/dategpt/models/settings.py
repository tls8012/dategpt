from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple


SUPPORTED_PROVIDERS = (
    "openai",
    "anthropic",
    "google_genai",
    "xai",
)
_PROVIDER_ALIASES = {
    "gemini": "google_genai",
    "google": "google_genai",
    "grok": "xai",
}
_ENV_KEYS = {
    "openai": ("OPENAI_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "google_genai": (
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
    ),
    "xai": ("XAI_API_KEY",),
}


def normalize_provider(value: str) -> str:
    provider = str(value).strip().casefold()
    provider = _PROVIDER_ALIASES.get(
        provider,
        provider,
    )
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(
            "provider must be one of: {}".format(
                ", ".join(SUPPORTED_PROVIDERS)
            )
        )
    return provider


@dataclass
class ModelSettings:
    provider: str = "openai"
    model: str = ""
    api_keys: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "ModelSettings":
        provider = normalize_provider(data.get("provider", "openai"))
        model = str(data.get("model", "")).strip()

        raw_keys = data.get("api_keys", {})
        if not isinstance(raw_keys, dict):
            raw_keys = {}

        api_keys = {}
        for name in SUPPORTED_PROVIDERS:
            value = raw_keys.get(name)
            if isinstance(value, str) and value.strip():
                api_keys[name] = value.strip()

        return cls(
            provider=provider,
            model=model,
            api_keys=api_keys,
        )

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "api_keys": dict(self.api_keys),
        }


class ModelSettingsStore:
    """Local DateGPT model settings, separate from game Saves.

    API keys are stored only in this DateGPT-local settings file, never in
    compatible game Save data. On POSIX systems the file is best-effort chmod
    0600 after writing. Environment variables remain valid fallback sources.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> ModelSettings:
        if not self.path.exists():
            return self._environment_defaults()

        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("model settings file must contain a JSON object")

        settings = ModelSettings.from_dict(data)

        if not settings.model:
            env_model = os.environ.get("DATEGPT_MODEL", "").strip()
            if env_model:
                settings.model = env_model

        env_provider = os.environ.get("DATEGPT_PROVIDER", "").strip()
        if not data.get("provider") and env_provider:
            settings.provider = normalize_provider(env_provider)

        return settings

    def save(self, settings: ModelSettings) -> None:
        settings.provider = normalize_provider(settings.provider)
        settings.model = str(settings.model).strip()

        temp = self.path.with_name(self.path.name + ".tmp")
        temp.write_text(
            json.dumps(
                settings.to_dict(),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        os.replace(temp, self.path)
        self._restrict_permissions()

    def set_model(self, provider: str, model: str) -> ModelSettings:
        provider = normalize_provider(provider)
        model = str(model).strip()
        if not model:
            raise ValueError("model name must not be empty")

        settings = self.load()
        settings.provider = provider
        settings.model = model
        self.save(settings)
        return settings

    def set_api_key(self, provider: str, api_key: str) -> ModelSettings:
        provider = normalize_provider(provider)
        api_key = str(api_key).strip()
        if not api_key:
            raise ValueError("API key must not be empty")

        settings = self.load()
        settings.api_keys[provider] = api_key
        self.save(settings)
        return settings

    def clear_api_key(self, provider: str) -> ModelSettings:
        provider = normalize_provider(provider)
        settings = self.load()
        settings.api_keys.pop(provider, None)
        self.save(settings)
        return settings

    def effective_api_key(
        self,
        provider: Optional[str] = None,
        *,
        settings: Optional[ModelSettings] = None,
    ) -> Tuple[str, str]:
        current = settings or self.load()
        name = normalize_provider(provider or current.provider)

        saved = current.api_keys.get(name, "")
        if saved:
            return saved, "saved"

        for env_name in _ENV_KEYS[name]:
            env_value = os.environ.get(
                env_name,
                "",
            ).strip()
            if env_value:
                return env_value, "environment"

        return "", "missing"

    def public_snapshot(
        self,
        settings: Optional[ModelSettings] = None,
    ) -> dict:
        current = settings or self.load()
        keys = {}

        for provider in SUPPORTED_PROVIDERS:
            value, source = self.effective_api_key(
                provider,
                settings=current,
            )
            keys[provider] = {
                "configured": bool(value),
                "source": source,
                "masked": _mask_secret(value) if value else "",
            }

        return {
            "provider": current.provider,
            "model": current.model,
            "api_keys": keys,
            "supported_providers": list(SUPPORTED_PROVIDERS),
        }

    def _environment_defaults(self) -> ModelSettings:
        provider = os.environ.get("DATEGPT_PROVIDER", "openai").strip()
        if not provider:
            provider = "openai"

        return ModelSettings(
            provider=normalize_provider(provider),
            model=os.environ.get("DATEGPT_MODEL", "").strip(),
        )

    def _restrict_permissions(self) -> None:
        try:
            os.chmod(
                self.path,
                stat.S_IRUSR | stat.S_IWUSR,
            )
        except (OSError, AttributeError):
            # Windows and some filesystems do not implement POSIX mode bits in
            # the same way. The file still remains under ignored user_data/.
            pass


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return "{}...{}".format(value[:4], value[-4:])
