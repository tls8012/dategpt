from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from .settings import ModelSettingsStore


class ModelNotConfigured(RuntimeError):
    pass


class ModelFactory:
    """Build the selected LangChain chat model from DateGPT settings.

    DateGPT owns validation and the small amount of provider-specific policy we
    actually need. LangChain owns provider dispatch through init_chat_model().
    """

    def __init__(
        self,
        settings_store: ModelSettingsStore,
        *,
        initializer: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.settings_store = settings_store
        self._initializer = initializer

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

        initializer = (
            self._initializer
            or _load_chat_model_initializer()
        )

        return initializer(
            model=settings.model,
            model_provider=settings.provider,
            **_provider_kwargs(
                settings.provider,
                api_key,
            ),
        )


def _provider_kwargs(
    provider: str,
    api_key: str,
) -> Dict[str, Any]:
    if provider == "openai":
        return {
            "api_key": api_key,
            "use_responses_api": True,
            "output_version": "responses/v1",
        }

    if provider == "anthropic":
        return {
            "anthropic_api_key": api_key,
        }

    raise ModelNotConfigured(
        "지원하지 않는 provider: {}".format(
            provider
        )
    )


def _load_chat_model_initializer():
    try:
        from langchain.chat_models import init_chat_model
    except ImportError as exc:
        raise RuntimeError(
            "LangChain chat model support requires langchain."
        ) from exc

    return init_chat_model
