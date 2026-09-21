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
        self.onboarding_turns = []
        self.recorded_assistant = []

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

    def run_onboarding_turn(
        self,
        text,
        *,
        welcome_text,
        onboarding_state,
        record_history=True,
    ):
        self.onboarding_turns.append(
            {
                "text": text,
                "welcome_text": welcome_text,
                "state": dict(onboarding_state),
                "record_history": record_history,
            }
        )
        return AgentRunResult(
            text="ONBOARDING: " + text,
            prompt_fingerprint="onboarding-test",
            raw_result={},
        )

    def record_assistant_message(
        self,
        text,
        *,
        prompt_fingerprint,
        phase,
    ):
        self.recorded_assistant.append(
            {
                "text": text,
                "prompt_fingerprint": prompt_fingerprint,
                "phase": phase,
            }
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
    (root / "entities").mkdir()
    (root / "entities" / "existing.md").write_text(
        "# Existing Character",
        encoding="utf-8",
    )


def write_prompts(root: Path):
    root.mkdir(parents=True)
    (root / "runtime.md").write_text(
        "RUNTIME",
        encoding="utf-8",
    )
    (root / "onboarding.md").write_text(
        "ONBOARDING POLICY",
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

    def make_open_app(self, base: Path):
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
        return app, scenario, prompts, opened

    def test_direct_setup_play_and_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            app, _, _, opened = self.make_open_app(base)

            self.assertEqual(opened[0]["type"], "session_opened")
            self.assertTrue(opened[0]["needs_setup"])

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
            self.assertEqual(
                app.active_session.onboarding.state.phase,
                "complete",
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

    def test_new_game_text_input_routes_into_onboarding(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            app, _, _, _ = self.make_open_app(base)

            statuses = []
            reply = app.handle(
                {
                    "type": "say",
                    "request_id": "2",
                    "text": "어떤 캐릭터를 만들 수 있어?",
                },
                emit=statuses.append,
            )

            self.assertEqual(statuses[0]["type"], "status")
            self.assertEqual(reply[0]["type"], "reply")
            self.assertEqual(reply[0]["phase"], "onboarding")
            self.assertEqual(
                app.active_session.onboarding.state.phase,
                "mode_selection",
            )

    def test_original_character_draft_finalizes_to_compatible_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            app, _, _, _ = self.make_open_app(base)

            selected = app.handle({
                "type": "say",
                "request_id": "2",
                "text": "!새캐릭터",
            })
            self.assertEqual(
                selected[0]["type"],
                "onboarding_state",
            )

            missing = app.handle({
                "type": "say",
                "request_id": "3",
                "text": "!캐릭터확정",
            })
            self.assertEqual(
                missing[0]["code"],
                "CHARACTER_DRAFT_MISSING",
            )

            app.active_session.workspace.scratchpad.write_text(
                "onboarding/main_character.md",
                "# PLAYER\n- name: 유키\n",
            )

            completed = app.handle({
                "type": "say",
                "request_id": "4",
                "text": "!캐릭터확정",
            })
            self.assertEqual(
                completed[0]["type"],
                "session_setup_complete",
            )
            self.assertFalse(
                app.active_session.needs_setup
            )
            self.assertEqual(
                app.active_session.workspace.save.read_text(
                    "entities/main_character.md"
                ),
                "# PLAYER\n- name: 유키\n",
            )

    def test_existing_mode_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            app, _, _, _ = self.make_open_app(base)

            existing = app.handle({
                "type": "onboarding_select_mode",
                "mode": "existing",
                "main_character": "entities/existing.md",
            })
            self.assertEqual(
                existing[0]["type"],
                "onboarding_state",
            )

            completed = app.handle({
                "type": "onboarding_finalize",
            })
            self.assertEqual(
                completed[0]["type"],
                "session_setup_complete",
            )
            self.assertEqual(
                app.active_session.initialization.init_complete.main_character,
                "entities/existing.md",
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
