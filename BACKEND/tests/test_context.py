import json
import tempfile
import unittest
from pathlib import Path

from dategpt.bootstrap.models import InitComplete
from dategpt.context import ContextBuilder
from dategpt.scenarios import ScenarioPack
from dategpt.workspace import SessionWorkspace


class ContextBuilderTests(unittest.TestCase):
    def test_core_player_scene_overlay_and_scratchpad_layers(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            scenario_root = base / "scenario"
            (scenario_root / "entities" / "characters").mkdir(
                parents=True
            )
            (scenario_root / "entities" / "locations").mkdir(
                parents=True
            )
            (scenario_root / "hidden").mkdir()

            (scenario_root / "entities" / "characters" / "heroine.md").write_text(
                "HEROINE SOURCE",
                encoding="utf-8",
            )
            (scenario_root / "entities" / "characters" / "seol.md").write_text(
                "SEOL SOURCE",
                encoding="utf-8",
            )
            (scenario_root / "entities" / "locations" / "station.md").write_text(
                "STATION SOURCE",
                encoding="utf-8",
            )
            (scenario_root / "hidden" / "secret.md").write_text(
                "SECRET PAYLOAD",
                encoding="utf-8",
            )
            (scenario_root / "context_manifest.json").write_text(
                json.dumps({
                    "core_files": [
                        "entities/characters/heroine.md"
                    ]
                }),
                encoding="utf-8",
            )
            (scenario_root / "character_manifest.md").write_text(
                (
                    "# CHARACTER MANIFEST\n"
                    "- 설연 | aliases: 달마대사의 재림 | "
                    "roles: 청하문 장문인의 딸 | "
                    "path: entities/characters/seol.md\n"
                ),
                encoding="utf-8",
            )

            workspace = SessionWorkspace.open(
                save_base=base / "games",
                runtime_base=base / "runtime",
                game_name="game",
                game_id="id",
            )
            workspace.save.write_text(
                "entities/main_character.md",
                "PLAYER SAVE",
            )
            workspace.save.write_text(
                "entities/characters/heroine.md",
                "HEROINE OVERLAY",
            )
            workspace.save.write_text(
                "entities/characters/seol.md",
                "SEOL OVERLAY",
            )
            workspace.save.write_text(
                "character_manifest.md",
                (
                    "# CHARACTER MANIFEST\n"
                    "- 설연 | aliases: 소연 | "
                    "path: entities/characters/seol.md\n"
                ),
            )
            workspace.scratchpad.write_text(
                "current.md",
                "NEWER SESSION STATE",
            )

            init_complete = InitComplete(
                game_name="game",
                game_id="id",
                main_character="entities/main_character.md",
                current={
                    "location": "entities/locations/station.md",
                    "scene": "",
                    "present_entities": "소연",
                    "active_story": "",
                    "relevant_flags": "",
                },
            )

            builder = ContextBuilder(
                scenario=ScenarioPack(scenario_root),
                workspace=workspace,
                init_complete=init_complete,
            )
            material = builder.build_gameplay()

            self.assertIn(
                "HEROINE SOURCE",
                material.stable_context,
            )
            dynamic = "\n".join(
                message["content"]
                for message in material.dynamic_messages
            )
            self.assertIn("PLAYER SAVE", dynamic)
            self.assertIn("HEROINE OVERLAY", dynamic)
            self.assertIn("STATION SOURCE", dynamic)
            self.assertIn("SEOL SOURCE", dynamic)
            self.assertIn("SEOL OVERLAY", dynamic)
            self.assertIn("NEWER SESSION STATE", dynamic)
            self.assertNotIn("SECRET PAYLOAD", dynamic)
            self.assertNotIn(
                "SECRET PAYLOAD",
                material.stable_context,
            )

    def test_ambiguous_present_entity_is_not_preloaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            scenario_root = base / "scenario"
            (scenario_root / "entities" / "characters").mkdir(
                parents=True
            )
            (scenario_root / "entities" / "characters" / "a.md").write_text(
                "CHARACTER A",
                encoding="utf-8",
            )
            (scenario_root / "entities" / "characters" / "b.md").write_text(
                "CHARACTER B",
                encoding="utf-8",
            )
            (scenario_root / "character_manifest.md").write_text(
                (
                    "- A | aliases: 검마 | "
                    "path: entities/characters/a.md\n"
                    "- B | aliases: 검마 | "
                    "path: entities/characters/b.md\n"
                ),
                encoding="utf-8",
            )

            workspace = SessionWorkspace.open(
                save_base=base / "games",
                runtime_base=base / "runtime",
                game_name="game",
                game_id="id",
            )
            init_complete = InitComplete(
                game_name="game",
                game_id="id",
                main_character="none",
                player_character_mode="none",
                play_mode="observer",
                current={
                    "present_entities": "검마",
                },
            )

            material = ContextBuilder(
                scenario=ScenarioPack(scenario_root),
                workspace=workspace,
                init_complete=init_complete,
            ).build_gameplay()
            dynamic = "\n".join(
                message["content"]
                for message in material.dynamic_messages
            )

            self.assertNotIn("CHARACTER A", dynamic)
            self.assertNotIn("CHARACTER B", dynamic)

    def test_onboarding_loads_welcome_public_index_and_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            scenario_root = base / "scenario"
            scenario_root.mkdir()
            (scenario_root / "character_manifest.md").write_text(
                "PUBLIC INDEX",
                encoding="utf-8",
            )

            workspace = SessionWorkspace.open(
                save_base=base / "games",
                runtime_base=base / "runtime",
                game_name="game",
                game_id="id",
            )
            workspace.scratchpad.write_text(
                "onboarding/main_character.md",
                "DRAFT CHARACTER",
            )

            builder = ContextBuilder(
                scenario=ScenarioPack(scenario_root),
                workspace=workspace,
            )
            material = builder.build_onboarding(
                welcome_text="WELCOME",
                onboarding_state={
                    "phase": "character_creation"
                },
            )
            dynamic = "\n".join(
                message["content"]
                for message in material.dynamic_messages
            )

            self.assertIn("WELCOME", dynamic)
            self.assertIn("PUBLIC INDEX", dynamic)
            self.assertIn("DRAFT CHARACTER", dynamic)

    def test_pointer_with_spaces_loads_exact_story(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            scenario_root = base / "scenario"
            (scenario_root / "story").mkdir(parents=True)
            (scenario_root / "story" / "전학 첫날.md").write_text(
                "FIRST DAY STORY",
                encoding="utf-8",
            )

            workspace = SessionWorkspace.open(
                save_base=base / "games",
                runtime_base=base / "runtime",
                game_name="game",
                game_id="id",
            )
            init_complete = InitComplete(
                game_name="game",
                game_id="id",
                main_character="none",
                player_character_mode="none",
                play_mode="observer",
                current={"active_story": "story/전학 첫날.md"},
            )

            material = ContextBuilder(
                scenario=ScenarioPack(scenario_root),
                workspace=workspace,
                init_complete=init_complete,
            ).build_gameplay()
            dynamic = "\n".join(
                message["content"]
                for message in material.dynamic_messages
            )
            self.assertIn("FIRST DAY STORY", dynamic)


if __name__ == "__main__":
    unittest.main()
