import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dategpt.agent import AgentRunResult
from dategpt.models import ModelSettingsStore
from dategpt.protocol import BackendApplication


class FakeRunner:
    def __init__(self, host, model_factory):
        self.host = host
        self.model_factory = model_factory
        self.turns = []
        self.maintenance = []

    def run_turn(self, text):
        self.turns.append(text)
        return AgentRunResult(
            text="AI: " + text,
            prompt_fingerprint="test",
            raw_result={},
        )

    def run_maintenance(self, instruction):
        self.maintenance.append(instruction)
        return AgentRunResult(
            text="저장 완료",
            prompt_fingerprint="test",
            raw_result={},
        )


def write_scenario(root: Path):
    root.mkdir(parents=True)
    (root / "file-manifest.md").write_text(
        "# FILE MANIFEST\n\n"
        "- `GAME_NAME: protocol-test`\n"
        "- `CONTENT_ROOT: .`\n",
        encoding="utf-8",
    )
    (root / "story").mkdir()
    (root / "story" / "welcome.md").write_text(
        "welcome",
        encoding="utf-8",
    )


def write_prompts(root: Path):
    root.mkdir(parents=True)
    (root / "runtime.md").write_text(
        "RUNTIME",
        encoding="utf-8",
    )


class ProtocolTests(unittest.TestCase):
    def make_app(self, base: Path):
        model_store = ModelSettingsStore(
            base / "config" / "model_settings.json"
        )
        return BackendApplication(
            backend_dir=base / "backend",
            model_settings_store=model_store,
            runner_factory=lambda host, model_factory: FakeRunner(
                host,
                model_factory,
            ),
        )

    def test_single_active_session_setup_play_and_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            scenario = base / "scenario"
            prompts = base / "prompts"
            write_scenario(scenario)
            write_prompts(prompts)

            with patch.dict(
                "os.environ",
                {
                    "DATEGPT_SAVE_DIR": str(base / "games"),
                    "DATEGPT_RUNTIME_DIR": str(base / "runtime"),
                },
                clear=False,
            ):
                app = self.make_app(base)

            opened = app.handle({
                "type": "open_session",
                "request_id": "1",
                "scenario_path": str(scenario),
                "prompt_path": str(prompts),
            })
            self.assertEqual(opened[0]["type"], "session_opened")
            self.assertTrue(opened[0]["needs_setup"])

            needs_setup = app.handle({
                "type": "play",
                "request_id": "2",
                "text": "hello",
            })
            self.assertEqual(needs_setup[0]["code"], "SESSION_NEEDS_SETUP")

            setup = app.handle({
                "type": "setup_session",
                "request_id": "3",
                "play_mode": "observer",
                "player_character_mode": "none",
                "main_character": "none",
            })
            self.assertEqual(
                setup[0]["type"],
                "session_setup_complete",
            )

            statuses = []
            played = app.handle(
                {
                    "type": "play",
                    "request_id": "4",
                    "text": "hello",
                    "controls": {
                        "initiative": "high",
                        "world_consistency": "low",
                        "language": "한국어",
                    },
                },
                emit=statuses.append,
            )
            self.assertEqual(statuses[0]["type"], "status")
            self.assertEqual(played[0]["text"], "AI: hello")
            self.assertEqual(
                app.active_session.host.controls.initiative,
                "high",
            )

            checkpoint = app.handle({
                "type": "checkpoint",
                "request_id": "5",
            })
            self.assertEqual(
                checkpoint[0]["type"],
                "checkpoint_complete",
            )
            self.assertEqual(
                app.active_session.runner.maintenance,
                ["!저장"],
            )

    def test_open_session_replaces_previous_active_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            scenario = base / "scenario"
            prompts = base / "prompts"
            write_scenario(scenario)
            write_prompts(prompts)

            with patch.dict(
                "os.environ",
                {
                    "DATEGPT_SAVE_DIR": str(base / "games"),
                    "DATEGPT_RUNTIME_DIR": str(base / "runtime"),
                },
                clear=False,
            ):
                app = self.make_app(base)

            first = app.handle({
                "type": "open_session",
                "scenario_path": str(scenario),
                "prompt_path": str(prompts),
                "new_game": True,
            })
            first_id = first[0]["game_id"]

            second = app.handle({
                "type": "open_session",
                "scenario_path": str(scenario),
                "prompt_path": str(prompts),
                "new_game": True,
            })
            second_id = second[0]["game_id"]

            self.assertNotEqual(first_id, second_id)
            self.assertEqual(
                app.active_session.initialization.game_id,
                second_id,
            )

    def test_model_commands_work_without_active_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            app = self.make_app(base)

            result = app.handle({
                "type": "say",
                "request_id": "m1",
                "text": "!모델 anthropic claude-test",
            })
            self.assertEqual(
                result[-1]["type"],
                "reply",
            )
            self.assertIn(
                "anthropic / claude-test",
                result[-1]["text"],
            )

    def test_play_without_session_is_structured_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self.make_app(Path(tmp))
            result = app.handle({
                "type": "play",
                "request_id": "x",
                "text": "hello",
            })
            self.assertEqual(
                result[0]["code"],
                "NO_ACTIVE_SESSION",
            )
            self.assertEqual(
                result[0]["request_id"],
                "x",
            )


if __name__ == "__main__":
    unittest.main()
