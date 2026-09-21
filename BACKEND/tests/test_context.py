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
                    "present_entities": (
                        "entities/characters/heroine.md"
                    ),
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
            self.assertIn("NEWER SESSION STATE", dynamic)
            self.assertNotIn("SECRET PAYLOAD", dynamic)
            self.assertNotIn(
                "SECRET PAYLOAD",
                material.stable_context,
            )

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


if __name__ == "__main__":
    unittest.main()
