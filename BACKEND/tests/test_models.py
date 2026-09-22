import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dategpt.models import (
    ModelFactory,
    ModelNotConfigured,
    ModelSettingsRouter,
    ModelSettingsStore,
)


class ModelSettingsTests(unittest.TestCase):
    def test_commands_persist_model_and_never_echo_full_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ModelSettingsStore(
                Path(tmp) / "model_settings.json"
            )
            router = ModelSettingsRouter(store)

            model = router.try_handle_text(
                "!모델 anthropic claude-test"
            )
            self.assertTrue(model.handled)
            self.assertEqual(
                store.load().provider,
                "anthropic",
            )
            self.assertEqual(
                store.load().model,
                "claude-test",
            )

            secret = "sk-ant-this-is-a-test-secret"
            key = router.try_handle_text(
                "!api_key anthropic {}".format(secret)
            )
            self.assertTrue(key.handled)
            self.assertNotIn(secret, key.message)
            self.assertNotIn(
                secret,
                str(key.settings),
            )
            self.assertEqual(
                store.load().api_keys["anthropic"],
                secret,
            )

            status = router.try_handle_text("!모델")
            self.assertIn("anthropic / claude-test", status.message)
            self.assertNotIn(secret, status.message)

    def test_provider_aliases_and_environment_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ModelSettingsStore(
                Path(tmp) / "model_settings.json"
            )

            settings = store.set_model(
                "gemini",
                "gemini-test",
            )
            self.assertEqual(
                settings.provider,
                "google_genai",
            )

            settings = store.set_model(
                "grok",
                "grok-test",
            )
            self.assertEqual(
                settings.provider,
                "xai",
            )

            with patch.dict(
                os.environ,
                {
                    "GOOGLE_API_KEY": "google-key",
                    "GEMINI_API_KEY": "gemini-fallback",
                    "XAI_API_KEY": "xai-key",
                },
                clear=False,
            ):
                self.assertEqual(
                    store.effective_api_key("gemini"),
                    ("google-key", "environment"),
                )
                self.assertEqual(
                    store.effective_api_key("grok"),
                    ("xai-key", "environment"),
                )

            with patch.dict(
                os.environ,
                {
                    "GOOGLE_API_KEY": "",
                    "GEMINI_API_KEY": "gemini-fallback",
                },
                clear=False,
            ):
                self.assertEqual(
                    store.effective_api_key("google_genai"),
                    ("gemini-fallback", "environment"),
                )

    def test_clear_saved_key_falls_back_to_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ModelSettingsStore(
                Path(tmp) / "model_settings.json"
            )
            router = ModelSettingsRouter(store)
            router.try_handle_text("!api_key openai saved-key")

            with patch.dict(
                os.environ,
                {"OPENAI_API_KEY": "environment-key"},
                clear=False,
            ):
                response = router.try_handle_text(
                    "!api_key openai 삭제"
                )
                public = store.public_snapshot()
                self.assertEqual(
                    public["api_keys"]["openai"]["source"],
                    "environment",
                )
                self.assertIn(
                    "환경변수",
                    response.message,
                )

    def test_model_factory_dispatches_through_init_chat_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ModelSettingsStore(
                Path(tmp) / "model_settings.json"
            )
            calls = []

            def fake_initializer(**kwargs):
                calls.append(dict(kwargs))
                return dict(kwargs)

            factory = ModelFactory(
                store,
                initializer=fake_initializer,
            )

            store.set_model("openai", "gpt-test")
            store.set_api_key("openai", "openai-key")
            model = factory.create()

            self.assertEqual(
                model["model"],
                "gpt-test",
            )
            self.assertEqual(
                model["model_provider"],
                "openai",
            )
            self.assertEqual(
                model["api_key"],
                "openai-key",
            )
            self.assertTrue(
                model["use_responses_api"]
            )
            self.assertEqual(
                model["output_version"],
                "responses/v1",
            )
            self.assertNotIn(
                "anthropic_api_key",
                model,
            )

            store.set_model(
                "anthropic",
                "claude-test",
            )
            store.set_api_key(
                "anthropic",
                "anthropic-key",
            )
            model = factory.create()

            self.assertEqual(
                model["model"],
                "claude-test",
            )
            self.assertEqual(
                model["model_provider"],
                "anthropic",
            )
            self.assertEqual(
                model["anthropic_api_key"],
                "anthropic-key",
            )
            self.assertNotIn(
                "api_key",
                model,
            )
            self.assertNotIn(
                "use_responses_api",
                model,
            )

            store.set_model(
                "gemini",
                "gemini-test",
            )
            store.set_api_key(
                "gemini",
                "google-key",
            )
            model = factory.create()

            self.assertEqual(
                model["model"],
                "gemini-test",
            )
            self.assertEqual(
                model["model_provider"],
                "google_genai",
            )
            self.assertEqual(
                model["api_key"],
                "google-key",
            )

            store.set_model(
                "grok",
                "grok-test",
            )
            store.set_api_key(
                "grok",
                "xai-key",
            )
            model = factory.create()

            self.assertEqual(
                model["model"],
                "grok-test",
            )
            self.assertEqual(
                model["model_provider"],
                "xai",
            )
            self.assertEqual(
                model["api_key"],
                "xai-key",
            )

            self.assertEqual(
                len(calls),
                4,
            )

    def test_model_factory_requires_model_and_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ModelSettingsStore(
                Path(tmp) / "model_settings.json"
            )
            factory = ModelFactory(
                store,
                initializer=lambda **kwargs: kwargs,
            )

            with self.assertRaises(ModelNotConfigured):
                factory.create()

            store.set_model("openai", "gpt-test")
            with patch.dict(
                os.environ,
                {
                    "OPENAI_API_KEY": "",
                    "ANTHROPIC_API_KEY": "",
                    "GOOGLE_API_KEY": "",
                    "GEMINI_API_KEY": "",
                    "XAI_API_KEY": "",
                },
                clear=False,
            ):
                with self.assertRaises(ModelNotConfigured):
                    factory.create()


if __name__ == "__main__":
    unittest.main()
