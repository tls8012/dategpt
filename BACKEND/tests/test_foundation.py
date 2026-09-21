import tempfile
import unittest
from pathlib import Path

from dategpt.controls import ControlRouter, ControlState
from dategpt.fs import PathOutsideRoot, ReadOnlyStore, RootedTextStore
from dategpt.host import RuntimeHost
from dategpt.prompts import PromptBundle
from dategpt.scenarios import ScenarioPack
from dategpt.workspace import SessionWorkspace


class FoundationTests(unittest.TestCase):
    def test_rooted_store_blocks_escape_and_read_only_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RootedTextStore(Path(tmp), writable=False)
            with self.assertRaises(PathOutsideRoot):
                store.read_text("../outside.txt")
            with self.assertRaises(ReadOnlyStore):
                store.write_text("x.txt", "no")

    def test_prompt_snapshot_reads_current_runtime_and_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "init.md").write_text("INIT", encoding="utf-8")
            (root / "runtime.md").write_text("RUNTIME V1", encoding="utf-8")

            bundle = PromptBundle(root)
            snap1 = bundle.snapshot(controls={"initiative": "medium"})
            self.assertIn("RUNTIME V1", snap1.system_prompt)
            self.assertNotIn("INIT", snap1.system_prompt)
            self.assertIn('"initiative": "medium"', snap1.system_prompt)

            (root / "runtime.md").write_text("RUNTIME V2", encoding="utf-8")
            snap2 = bundle.snapshot(controls={"initiative": "high"}, include_init=True)
            self.assertIn("INIT", snap2.system_prompt)
            self.assertIn("RUNTIME V2", snap2.system_prompt)
            self.assertIn('"initiative": "high"', snap2.system_prompt)
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

    def test_host_builds_one_turn_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            prompts = base / "prompts"
            prompts.mkdir()
            (prompts / "init.md").write_text("INIT", encoding="utf-8")
            (prompts / "runtime.md").write_text("RUNTIME", encoding="utf-8")

            ws = SessionWorkspace.open(
                save_base=base / "games",
                runtime_base=base / "runtime",
                game_name="g",
                game_id="id",
            )
            ws.scratchpad.write_text("current.md", "WORKING")

            host = RuntimeHost(prompt_bundle=PromptBundle(prompts), workspace=ws)
            host.route_control({"type": "set_control", "name": "initiative", "value": "high"})
            turn = host.begin_turn("hello")

            self.assertEqual(turn.controls["initiative"], "high")
            self.assertEqual(turn.scratchpad["current.md"], "WORKING")
            self.assertIn("RUNTIME", turn.system_prompt)


if __name__ == "__main__":
    unittest.main()
