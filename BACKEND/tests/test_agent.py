import tempfile
import unittest
from pathlib import Path

from dategpt.agent import AgentFilesystem, AgentRunner
from dategpt.host import RuntimeHost
from dategpt.presentation import VNResponse
from dategpt.prompts import PromptBundle
from dategpt.scenarios import ScenarioPack
from dategpt.workspace import SessionWorkspace


class FakeAgent:
    def __init__(self, capture):
        self.capture = capture

    def invoke(self, payload):
        self.capture["payload"] = payload
        return {
            "messages": [
                {"role": "assistant", "content": "최종 응답"},
            ],
            "structured_response": {
                "segments": [
                    {
                        "kind": "narration",
                        "speaker": "",
                        "text": "최종 응답",
                    }
                ]
            },
        }


class AgentTests(unittest.TestCase):
    def make_runtime(self, base: Path):
        prompts = base / "prompts"
        prompts.mkdir()
        (prompts / "runtime.md").write_text(
            "RUNTIME POLICY",
            encoding="utf-8",
        )

        scenario = base / "scenario"
        (scenario / "entities").mkdir(parents=True)
        (scenario / "hidden").mkdir()
        (scenario / "entities" / "yuna.md").write_text(
            "붉은 머리 기사 유나",
            encoding="utf-8",
        )
        (scenario / "hidden" / "secret.md").write_text(
            "붉은 머리의 비밀",
            encoding="utf-8",
        )

        workspace = SessionWorkspace.open(
            save_base=base / "games",
            runtime_base=base / "runtime",
            game_name="game",
            game_id="id",
        )
        return PromptBundle(prompts), ScenarioPack(scenario), workspace

    def test_raw_filesystem_permissions_and_hidden_search_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _, scenario, workspace = self.make_runtime(base)
            fs = AgentFilesystem(
                scenario=scenario,
                workspace=workspace,
            )

            self.assertIn("유나", fs.content_read("entities/yuna.md"))
            results = fs.content_search("붉은 머리")
            self.assertEqual(
                [item["path"] for item in results],
                ["entities/yuna.md"],
            )

            hidden = fs.content_search(
                "붉은 머리",
                scope="hidden",
            )
            self.assertEqual(hidden[0]["path"], "hidden/secret.md")

            fallback = fs.save_read("entities/yuna.md")
            self.assertIn(
                "## SOURCE: entities/yuna.md",
                fallback,
            )
            self.assertIn(
                "붉은 머리 기사 유나",
                fallback,
            )

            fs.save_write("entities/yuna.md", "관계 변화")
            layered = fs.save_read("entities/yuna.md")
            self.assertIn(
                "## SOURCE: entities/yuna.md",
                layered,
            )
            self.assertIn(
                "붉은 머리 기사 유나",
                layered,
            )
            self.assertIn(
                "## SAVE OVERLAY: entities/yuna.md",
                layered,
            )
            self.assertIn("관계 변화", layered)

            fs.scratchpad_write("current.md", "다음 장면 준비")
            self.assertEqual(
                fs.scratchpad_read("current.md"),
                "다음 장면 준비",
            )

    def test_runner_journals_only_mutated_files_and_rolls_them_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            prompts, scenario, workspace = self.make_runtime(base)
            workspace.save.write_text(
                "entities/state.md",
                "before",
            )

            captured = {}

            class MutatingAgent:
                def invoke(self, payload):
                    captured["fs"].save_write(
                        "entities/state.md",
                        "after",
                    )
                    captured["fs"].scratchpad_write(
                        "temp.md",
                        "created",
                    )
                    return {
                        "messages": [
                            {
                                "role": "assistant",
                                "content": "done",
                            }
                        ],
                        "structured_response": {
                            "segments": [
                                {
                                    "kind": "narration",
                                    "speaker": "",
                                    "text": "done",
                                }
                            ]
                        },
                    }

            def tool_factory(fs):
                captured["fs"] = fs
                return []

            runner = AgentRunner(
                host=RuntimeHost(
                    prompt_bundle=prompts,
                    scenario=scenario,
                    workspace=workspace,
                ),
                model="fake:model",
                agent_factory=lambda **kwargs: MutatingAgent(),
                tool_factory=tool_factory,
            )
            result = runner.run_turn("change")
            self.assertEqual(result.text, "done")

            turns = workspace.turns.list_turns()
            self.assertEqual(len(turns), 1)
            self.assertEqual(turns[0]["changed_files"], 2)
            self.assertEqual(
                workspace.save.read_text(
                    "entities/state.md"
                ),
                "after",
            )
            self.assertTrue(
                workspace.scratchpad.exists("temp.md")
            )

            workspace.turns.rollback(
                turns[0]["turn_id"]
            )
            self.assertEqual(
                workspace.save.read_text(
                    "entities/state.md"
                ),
                "before",
            )
            self.assertFalse(
                workspace.scratchpad.exists("temp.md")
            )
            self.assertEqual(
                workspace.history.tail(10),
                [],
            )

    def test_runner_failure_restores_uncommitted_tool_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            prompts, scenario, workspace = self.make_runtime(base)
            workspace.save.write_text(
                "entities/state.md",
                "before",
            )

            captured = {}

            class FailingAgent:
                def invoke(self, payload):
                    captured["fs"].save_write(
                        "entities/state.md",
                        "broken",
                    )
                    captured["fs"].scratchpad_write(
                        "temp.md",
                        "broken",
                    )
                    raise RuntimeError("boom")

            def tool_factory(fs):
                captured["fs"] = fs
                return []

            runner = AgentRunner(
                host=RuntimeHost(
                    prompt_bundle=prompts,
                    scenario=scenario,
                    workspace=workspace,
                ),
                model="fake:model",
                agent_factory=lambda **kwargs: FailingAgent(),
                tool_factory=tool_factory,
            )

            with self.assertRaises(RuntimeError):
                runner.run_turn("change")

            self.assertEqual(
                workspace.save.read_text(
                    "entities/state.md"
                ),
                "before",
            )
            self.assertFalse(
                workspace.scratchpad.exists("temp.md")
            )
            self.assertEqual(
                workspace.turns.list_turns(),
                [],
            )
            self.assertEqual(
                workspace.history.tail(10),
                [],
            )

    def test_runner_uses_one_turn_system_prompt_and_own_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            prompts, scenario, workspace = self.make_runtime(base)
            workspace.scratchpad.write_text(
                "current.md",
                "WORKING MEMORY",
            )
            workspace.history.append(
                {"role": "user", "text": "이전 입력"}
            )
            workspace.history.append(
                {"role": "assistant", "text": "이전 응답"}
            )

            host = RuntimeHost(
                prompt_bundle=prompts,
                scenario=scenario,
                workspace=workspace,
            )

            capture = {}

            def fake_factory(**kwargs):
                capture["factory"] = kwargs
                return FakeAgent(capture)

            runner = AgentRunner(
                host=host,
                model="fake:model",
                agent_factory=fake_factory,
                tool_factory=lambda fs: ["tool-placeholder"],
            )
            result = runner.run_turn("현재 입력")

            self.assertEqual(result.text, "최종 응답")
            self.assertEqual(
                capture["factory"]["system_prompt"].count("RUNTIME POLICY"),
                1,
            )
            self.assertEqual(
                capture["factory"]["tools"],
                ["tool-placeholder"],
            )
            self.assertIs(
                capture["factory"]["response_format"],
                VNResponse,
            )

            messages = capture["payload"]["messages"]
            self.assertEqual(messages[-1]["content"], "현재 입력")
            self.assertTrue(
                any(
                    message["role"] == "system"
                    and "WORKING MEMORY" in message["content"]
                    for message in messages
                )
            )
            self.assertTrue(
                any(
                    message["role"] == "user"
                    and message["content"] == "이전 입력"
                    for message in messages
                )
            )

            tail = workspace.history.tail(2)
            self.assertEqual(tail[0]["role"], "user")
            self.assertEqual(tail[0]["text"], "현재 입력")
            self.assertEqual(tail[1]["role"], "assistant")
            self.assertEqual(tail[1]["text"], "최종 응답")


if __name__ == "__main__":
    unittest.main()
