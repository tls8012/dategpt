from __future__ import annotations

from typing import Any, Callable, Optional

from .settings import ModelSettingsStore


class ModelNotConfigured(RuntimeError):
    pass


class ModelFactory:
    """Create the currently selected LangChain chat model on demand."""

    def __init__(
        self,
        settings_store: ModelSettingsStore,
        *,
        openai_factory: Optional[Callable[..., Any]] = None,
        anthropic_factory: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.settings_store = settings_store
        self._openai_factory = openai_factory
        self._anthropic_factory = anthropic_factory

    def create(self) -> Any:
        settings = self.settings_store.load()

        if not settings.model:
            raise ModelNotConfigured(
                "모델이 설정되지 않았습니다. "
                "!모델 <openai|anthropic> <모델명> 으로 설정해 주세요."
            )

        api_key, _ = self.settings_store.effective_api_key(
            settings.provider,
            settings=settings,
        )
        if not api_key:
            raise ModelNotConfigured(
                "{} API key가 설정되지 않았습니다. "
                "!api_key {} <키> 로 설정해 주세요.".format(
                    settings.provider,
                    settings.provider,
                )
            )

        if settings.provider == "openai":
            factory = self._openai_factory or _load_openai_factory()
            return factory(
                model=settings.model,
                api_key=api_key,
                use_responses_api=True,
                output_version="responses/v1",
            )

        if settings.provider == "anthropic":
            factory = self._anthropic_factory or _load_anthropic_factory()
            return factory(
                model=settings.model,
                api_key=api_key,
            )

        raise ModelNotConfigured(
            "지원하지 않는 provider: {}".format(settings.provider)
        )


def _load_openai_factory():
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise RuntimeError(
            "OpenAI provider support requires langchain-openai."
        ) from exc
    return ChatOpenAI


def _load_anthropic_factory():
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError as exc:
        raise RuntimeError(
            "Anthropic provider support requires langchain-anthropic."
        ) from exc
    return ChatAnthropic
