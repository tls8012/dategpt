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
        if text == "__fail__":
            raise RuntimeError("forced test failure")

        self.turns.append(text)
        transaction = self.host.workspace.turns.begin()
        transaction.capture(
            "save",
            self.host.workspace.save,
            "story/state.md",
        )
        self.host.workspace.save.write_text(
            "story/state.md",
            text,
        )
        self.host.workspace.history.append(
            {
                "role": "user",
                "text": text,
                "prompt_fingerprint": "test",
            }
        )
        reply = "AI: " + text
        segments = (
            {
                "kind": "narration",
                "speaker": "",
                "text": reply,
            },
        )
        self.host.workspace.history.append(
            {
                "role": "assistant",
                "text": reply,
                "segments": [
                    dict(item) for item in segments
                ],
                "prompt_fingerprint": "test",
            }
        )
        transaction.commit(
            user_text=text,
            assistant_text=reply,
            prompt_fingerprint="test",
        )
        return AgentRunResult(
            text=reply,
            prompt_fingerprint="test",
            raw_result={},
            segments=segments,
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
        reply = "ONBOARDING: " + text
        return AgentRunResult(
            text=reply,
            prompt_fingerprint="onboarding-test",
            raw_result={},
            segments=(
                {
                    "kind": "system",
                    "speaker": "",
                    "text": reply,
                },
            ),
        )

    def record_assistant_message(
        self,
        text,
        *,
        prompt_fingerprint,
        phase,
        segments=(),
    ):
        self.recorded_assistant.append(
            {
                "text": text,
                "prompt_fingerprint": prompt_fingerprint,
                "phase": phase,
                "segments": list(segments),
            }
        )


def write_datellm_style_distribution(root: Path):
    root.mkdir(parents=True)
    (root / "file-manifest.md").write_text(
        "# datellm Distribution\n\n"
        "GAME_NAME: datellm\n"
        "BUILD_VERSION: 1\n"
        "FORMAT_VERSION: 1\n"
        "CONTENT_ROOT: datellm/distribution\n",
        encoding="utf-8",
    )
    (root / "story").mkdir()
    (root / "story" / "welcome.md").write_text(
        "welcome",
        encoding="utf-8",
    )
    (root / "character_manifest.md").write_text(
        (
            "ChatGPT | roles: 같은 반 학생, 연애 대상, LLM | "
            "path: entities/characters/ChatGPT.md\n"
        ),
        encoding="utf-8",
    )
    (root / "entities" / "characters").mkdir(
        parents=True
    )
    (root / "entities" / "characters" / "ChatGPT.md").write_text(
        "# ChatGPT",
        encoding="utf-8",
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

    def test_install_and_mount_datellm_style_cartridge_without_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "datellm" / "distribution"
            prompts = base / "prompts"
            write_datellm_style_distribution(source)
            write_prompts(prompts)

            with patch.dict(
                "os.environ",
                {
                    "DATEGPT_SAVE_DIR": str(base / "games"),
                    "DATEGPT_RUNTIME_DIR": str(base / "runtime"),
                    "DATEGPT_CARTRIDGE_DIR": str(base / "cartridges"),
                },
                clear=False,
            ):
                app = self.make_app(base)

            installed = app.handle({
                "type": "install_cartridge",
                "request_id": "i1",
                "source_path": str(source.parent),
            })
            self.assertEqual(
                installed[0]["type"],
                "cartridge_installed",
            )
            self.assertEqual(
                installed[0]["cartridge"]["game_name"],
                "datellm",
            )
            self.assertEqual(
                installed[0]["cartridge"]["build_version"],
                "1",
            )

            opened = app.handle({
                "type": "open_session",
                "request_id": "i2",
                "game_name": "datellm",
                "build_version": "1",
                "prompt_path": str(prompts),
            })
            self.assertEqual(
                opened[0]["type"],
                "session_opened",
            )
            self.assertEqual(
                opened[0]["game_name"],
                "datellm",
            )
            self.assertEqual(
                opened[0]["build_version"],
                "1",
            )
            self.assertTrue(
                app.active_session.scenario.exists(
                    "entities/characters/ChatGPT.md"
                )
            )
            self.assertFalse(
                app.active_session.scenario.exists(
                    "assets/example.png"
                )
            )

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

    def test_list_game_instances_does_not_create_a_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            app = self.make_app(base)

            empty = app.handle({
                "type": "list_game_instances",
                "request_id": "list-1",
                "game_name": "protocol-test",
            })
            self.assertEqual(
                empty[0]["type"],
                "game_instance_list",
            )
            self.assertEqual(empty[0]["game_ids"], [])

            game_root = app.save_base / "protocol-test"
            game_root.mkdir(parents=True)
            (game_root / "save-a").mkdir()
            (game_root / "save-b").mkdir()

            listed = app.handle({
                "type": "list_game_instances",
                "request_id": "list-2",
                "game_name": "protocol-test",
            })
            self.assertEqual(
                listed[0]["game_ids"],
                ["save-a", "save-b"],
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

    def test_turn_rollback_restores_sparse_save_and_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            app, _, _, _ = self.make_open_app(base)

            app.handle({
                "type": "setup_session",
                "play_mode": "observer",
                "player_character_mode": "none",
                "main_character": "none",
            })

            first = app.handle({
                "type": "play",
                "text": "first",
            })
            second = app.handle({
                "type": "play",
                "text": "second",
            })
            self.assertEqual(first[0]["text"], "AI: first")
            self.assertEqual(second[0]["text"], "AI: second")

            turns = app.handle({
                "type": "list_turns",
            })[0]["turns"]
            self.assertEqual(len(turns), 2)
            self.assertEqual(
                app.active_session.workspace.save.read_text(
                    "story/state.md"
                ),
                "second",
            )

            rolled_back = app.handle({
                "type": "rollback_turn",
                "turn_id": turns[1]["turn_id"],
            })
            self.assertEqual(
                rolled_back[0]["type"],
                "turn_rolled_back",
            )
            self.assertEqual(
                app.active_session.workspace.save.read_text(
                    "story/state.md"
                ),
                "first",
            )
            self.assertEqual(
                len(
                    app.active_session.workspace.history.tail(
                        100
                    )
                ),
                2,
            )

    def test_edit_turn_discards_future_and_creates_new_head(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            app, _, _, _ = self.make_open_app(base)

            app.handle({
                "type": "setup_session",
                "play_mode": "observer",
                "player_character_mode": "none",
                "main_character": "none",
            })
            app.handle({"type": "play", "text": "first"})
            app.handle({"type": "play", "text": "second"})
            app.handle({"type": "play", "text": "third"})

            turns = app.handle({
                "type": "list_turns",
            })[0]["turns"]
            edited = app.handle({
                "type": "edit_turn",
                "turn_id": turns[1]["turn_id"],
                "text": "changed",
            })

            self.assertEqual(
                edited[0]["type"],
                "turn_edited",
            )
            self.assertEqual(
                edited[0]["text"],
                "AI: changed",
            )
            self.assertEqual(
                [
                    item["user_text"]
                    for item in edited[0]["turns"]
                ],
                ["first", "changed"],
            )
            self.assertEqual(
                app.active_session.workspace.save.read_text(
                    "story/state.md"
                ),
                "changed",
            )

    def test_failed_turn_edit_restores_original_head(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            app, _, _, _ = self.make_open_app(base)

            app.handle({
                "type": "setup_session",
                "play_mode": "observer",
                "player_character_mode": "none",
                "main_character": "none",
            })
            app.handle({"type": "play", "text": "first"})
            app.handle({"type": "play", "text": "second"})

            turns = app.handle({
                "type": "list_turns",
            })[0]["turns"]
            failed = app.handle({
                "type": "edit_turn",
                "turn_id": turns[0]["turn_id"],
                "text": "__fail__",
            })
            self.assertEqual(
                failed[0]["type"],
                "error",
            )

            restored = app.handle({
                "type": "list_turns",
            })[0]["turns"]
            self.assertEqual(
                [item["user_text"] for item in restored],
                ["first", "second"],
            )
            self.assertEqual(
                app.active_session.workspace.save.read_text(
                    "story/state.md"
                ),
                "second",
            )
            history = (
                app.active_session.workspace.history.tail(100)
            )
            self.assertEqual(
                [item["text"] for item in history[-4:]],
                [
                    "first",
                    "AI: first",
                    "second",
                    "AI: second",
                ],
            )

    def test_regenerate_turn_reuses_original_user_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            app, _, _, _ = self.make_open_app(base)

            app.handle({
                "type": "setup_session",
                "play_mode": "observer",
                "player_character_mode": "none",
                "main_character": "none",
            })
            app.handle({"type": "play", "text": "again"})
            turn_id = app.handle({
                "type": "list_turns",
            })[0]["turns"][0]["turn_id"]

            regenerated = app.handle({
                "type": "regenerate_turn",
                "turn_id": turn_id,
            })
            self.assertEqual(
                regenerated[0]["type"],
                "turn_regenerated",
            )
            self.assertEqual(
                regenerated[0]["user_text"],
                "again",
            )
            self.assertEqual(
                regenerated[0]["text"],
                "AI: again",
            )

    def test_play_emits_structured_presentation_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            app, _, _, _ = self.make_open_app(base)
            app.handle({
                "type": "setup_session",
                "play_mode": "observer",
                "player_character_mode": "none",
                "main_character": "none",
            })

            emitted = []
            reply = app.handle(
                {
                    "type": "play",
                    "request_id": "present-1",
                    "text": "hello",
                },
                emit=emitted.append,
            )

            self.assertEqual(
                [item["type"] for item in emitted],
                [
                    "status",
                    "presentation_start",
                    "presentation_segment",
                    "presentation_end",
                ],
            )
            self.assertEqual(
                emitted[2]["segment"]["text"],
                "AI: hello",
            )
            self.assertEqual(
                reply[0]["segments"][0]["kind"],
                "narration",
            )

    def test_resume_exposes_recent_structured_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            app, scenario, prompts, opened = self.make_open_app(base)
            game_id = opened[0]["game_id"]
            app.handle({
                "type": "setup_session",
                "play_mode": "observer",
                "player_character_mode": "none",
                "main_character": "none",
            })
            app.handle({
                "type": "play",
                "text": "remember me",
            })

            resumed = app.handle({
                "type": "open_session",
                "scenario_path": str(scenario),
                "prompt_path": str(prompts),
                "game_id": game_id,
            })[0]

            self.assertEqual(
                resumed["type"],
                "session_opened",
            )
            assistant = [
                item
                for item in resumed["recent_history"]
                if item.get("role") == "assistant"
            ][-1]
            self.assertEqual(
                assistant["segments"][0]["text"],
                "AI: remember me",
            )
            self.assertEqual(
                resumed["turns"][-1]["user_text"],
                "remember me",
            )

    def test_bulk_controls_persist_in_active_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            app, _, _, _ = self.make_open_app(base)

            changed = app.handle({
                "type": "set_controls",
                "controls": {
                    "language": "English",
                    "initiative": "high",
                    "world_consistency": "low",
                },
            })
            controls = changed[0]["controls"]

            self.assertEqual(
                controls["language"],
                "English",
            )
            self.assertEqual(
                controls["initiative"],
                "high",
            )
            self.assertEqual(
                controls["world_consistency"],
                "low",
            )
            self.assertEqual(
                app.active_session.workspace.load_controls()[
                    "language"
                ],
                "English",
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

    def test_repo_scaffolding_is_default_prompt_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            scenario = base / "scenario"
            scaffolding = base / ".scaffolding"
            write_scenario(scenario)
            write_prompts(scaffolding)

            with patch.dict(
                "os.environ",
                {
                    "DATEGPT_SAVE_DIR": str(base / "games"),
                    "DATEGPT_RUNTIME_DIR": str(base / "runtime"),
                    "DATEGPT_PROMPT_DIR": "",
                },
                clear=False,
            ):
                app = self.make_app(base)

            opened = app.handle({
                "type": "open_session",
                "request_id": "local-prompts",
                "scenario_path": str(scenario),
            })
            self.assertEqual(
                opened[0]["type"],
                "session_opened",
            )
            self.assertEqual(
                app.active_session.host.prompt_bundle.root,
                scaffolding.resolve(),
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
