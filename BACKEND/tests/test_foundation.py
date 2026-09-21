import tempfile
import unittest
from pathlib import Path

from dategpt.bootstrap import (
    GameInstanceSelectionRequired,
    SessionInitializer,
)
from dategpt.controls import ControlRouter, ControlState
from dategpt.fs import PathOutsideRoot, ReadOnlyStore, RootedTextStore
from dategpt.host import RuntimeHost
from dategpt.prompts import PromptBundle
from dategpt.scenarios import ScenarioPack
from dategpt.workspace import SessionWorkspace


def make_scenario(root: Path, game_name="테스트게임", content_root="content/"):
    root.mkdir(parents=True, exist_ok=True)
    (root / "file-manifest.md").write_text(
        "# FILE MANIFEST\n\n"
        "- `GAME_NAME: {}`\n"
        "- `CONTENT_ROOT: {}`\n"
        "- `control.gender: unspecified`\n".format(
            game_name,
            content_root,
        ),
        encoding="utf-8",
    )
    (root / "character_manifest.md").write_text(
        "# CHARACTER MANIFEST\n- 유나: entities/yuna.md\n",
        encoding="utf-8",
    )
    (root / "story").mkdir(exist_ok=True)
    (root / "story" / "welcome.md").write_text(
        "# WELCOME\nhello",
        encoding="utf-8",
    )


class FoundationTests(unittest.TestCase):
    def test_rooted_store_blocks_escape_and_read_only_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RootedTextStore(Path(tmp), writable=False)
            with self.assertRaises(PathOutsideRoot):
                store.read_text("../outside.txt")
            with self.assertRaises(ReadOnlyStore):
                store.write_text("x.txt", "no")

    def test_prompt_snapshot_is_runtime_only_and_hot_reloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "init.md").write_text("SHOULD NOT BE SENT", encoding="utf-8")
            (root / "runtime.md").write_text("RUNTIME V1", encoding="utf-8")

            bundle = PromptBundle(root)
            snap1 = bundle.snapshot(controls={"initiative": "medium"})
            self.assertIn("RUNTIME V1", snap1.system_prompt)
            self.assertIn("DATEGPT HOST ADAPTER", snap1.system_prompt)
            self.assertNotIn("SHOULD NOT BE SENT", snap1.system_prompt)
            self.assertEqual(snap1.source_files, ("runtime.md",))

            (root / "runtime.md").write_text("RUNTIME V2", encoding="utf-8")
            snap2 = bundle.snapshot(controls={"initiative": "high"})
            self.assertIn("RUNTIME V2", snap2.system_prompt)
            self.assertNotEqual(snap1.fingerprint, snap2.fingerprint)

    def test_scenario_pack_is_read_only_and_searchable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "entities").mkdir()
            (root / "entities" / "yuna.md").write_text(
                "# 유나\n붉은 머리 기사",
                encoding="utf-8",
            )
            pack = ScenarioPack(root)
            hits = pack.search("붉은 머리")
            self.assertEqual(hits[0]["path"], "entities/yuna.md")

    def test_workspace_separates_save_and_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            ws = SessionWorkspace.open(
                save_base=base / "games",
                runtime_base=base / "runtime",
                game_name="테스트",
                game_id="abc123",
            )
            ws.save.write_text("init완료.md", "# save")
            ws.scratchpad.write_text("current.md", "# working")
            ws.history.append({"role": "user", "text": "hello"})

            self.assertTrue((base / "games" / "테스트" / "abc123" / "init완료.md").exists())
            self.assertTrue((base / "runtime" / "테스트" / "abc123" / "scratchpad" / "current.md").exists())
            self.assertEqual(ws.history.tail(1)[0]["text"], "hello")

    def test_control_router_handles_without_llm(self):
        state = ControlState()
        router = ControlRouter(state)

        response = router.try_handle_text("!initiative high")
        self.assertTrue(response.handled)
        self.assertEqual(state.initiative, "high")

        unknown = router.try_handle_text("안녕")
        self.assertFalse(unknown.handled)

    def test_host_builds_runtime_only_turn_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            prompts = base / "prompts"
            prompts.mkdir()
            (prompts / "runtime.md").write_text("RUNTIME", encoding="utf-8")

            ws = SessionWorkspace.open(
                save_base=base / "games",
                runtime_base=base / "runtime",
                game_name="g",
                game_id="id",
            )
            ws.scratchpad.write_text("current.md", "WORKING")

            scenario_root = base / "scenario"
            scenario_root.mkdir()
            host = RuntimeHost(
                prompt_bundle=PromptBundle(prompts),
                scenario=ScenarioPack(scenario_root),
                workspace=ws,
            )
            host.route_control({"type": "set_control", "name": "initiative", "value": "high"})
            turn = host.begin_turn("hello")

            self.assertEqual(turn.controls["initiative"], "high")
            self.assertTrue(
                any(
                    message["role"] == "system"
                    and "WORKING" in message["content"]
                    for message in turn.context_messages
                )
            )
            self.assertIn("RUNTIME", turn.system_prompt)

    def test_initializer_creates_original_compatible_skeleton(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            scenario_root = base / "scenario"
            make_scenario(scenario_root)

            initializer = SessionInitializer(
                save_base=base / "games",
                runtime_base=base / "runtime",
            )
            result = initializer.prepare(
                ScenarioPack(scenario_root),
            )

            self.assertTrue(result.is_new)
            self.assertTrue(result.needs_setup)
            game_root = base / "games" / "테스트게임"
            self.assertFalse((game_root / "game_source.md").exists())
            save_root = game_root / result.game_id
            for name in ("entities", "story", "flags", "hidden", "assets"):
                self.assertTrue((save_root / name).is_dir())
            self.assertTrue((save_root / "character_manifest.md").exists())
            self.assertEqual(result.welcome_text, "# WELCOME\nhello")
            self.assertIn("유나", result.distribution_character_manifest)

    def test_initializer_finalizes_and_resumes_single_instance(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            scenario_root = base / "scenario"
            make_scenario(scenario_root)

            initializer = SessionInitializer(
                save_base=base / "games",
                runtime_base=base / "runtime",
            )
            first = initializer.prepare(
                ScenarioPack(scenario_root),
            )
            controls = ControlState(
                initiative="high",
                world_consistency="low",
                language="English",
                dev_commands=True,
            )
            initializer.finalize_new_game(
                first,
                play_mode="observer",
                player_character_mode="none",
                main_character="none",
                current={"location": "station", "scene": "opening"},
                controls=controls,
            )

            resumed = initializer.prepare(
                ScenarioPack(scenario_root),
            )
            self.assertFalse(resumed.is_new)
            self.assertFalse(resumed.needs_setup)
            self.assertEqual(resumed.game_id, first.game_id)
            self.assertEqual(resumed.controls.initiative, "high")
            self.assertEqual(resumed.controls.world_consistency, "low")
            self.assertEqual(resumed.controls.language, "English")
            self.assertTrue(resumed.controls.dev_commands)
            self.assertEqual(
                resumed.controls.extra["gender"],
                "unspecified",
            )
            self.assertEqual(
                resumed.init_complete.extra_fields["gender"],
                "unspecified",
            )
            self.assertEqual(resumed.init_complete.current["location"], "station")

    def test_initializer_requires_choice_for_multiple_instances(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            scenario_root = base / "scenario"
            make_scenario(scenario_root)
            initializer = SessionInitializer(
                save_base=base / "games",
                runtime_base=base / "runtime",
            )
            pack = ScenarioPack(scenario_root)
            initializer.prepare(pack)
            initializer.prepare(pack, new_game=True)

            with self.assertRaises(GameInstanceSelectionRequired) as caught:
                initializer.prepare(pack)
            self.assertEqual(len(caught.exception.game_ids), 2)




if __name__ == "__main__":
    unittest.main()
