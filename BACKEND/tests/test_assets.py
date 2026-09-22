import tempfile
import unittest
from pathlib import Path

from dategpt.assets import (
    AssetCatalog,
    infer_content_base,
    resolve_authored_asset_path,
)


class AssetCatalogTests(unittest.TestCase):
    def test_raw_repo_path_resolves_from_content_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            distribution = repo / "datellm" / "distribution"
            assets = distribution / "assets"
            assets.mkdir(parents=True)

            raw = (
                repo
                / "datellm"
                / "raw"
                / "assets"
                / "characters"
                / "chatgpt"
                / "female"
                / "logo"
                / "uniform_neutral.png"
            )
            raw.parent.mkdir(parents=True)
            raw.write_bytes(b"fake-png")

            (assets / "characters.md").write_text(
                "# Character Asset Manifest\n\n"
                "format: ID | character | gender | head_mode | outfit | pose | path\n"
                "A005 | ChatGPT | female | logo | uniform | neutral | "
                "datellm/raw/assets/characters/chatgpt/female/logo/uniform_neutral.png\n",
                encoding="utf-8",
            )

            self.assertEqual(
                infer_content_base(
                    distribution,
                    "datellm/distribution",
                ),
                repo,
            )
            self.assertEqual(
                resolve_authored_asset_path(
                    distribution,
                    "datellm/distribution",
                    "datellm/raw/assets/characters/chatgpt/female/logo/uniform_neutral.png",
                ),
                raw.resolve(),
            )

            catalog = AssetCatalog(
                distribution,
                content_root="datellm/distribution",
            )
            resolved = catalog.resolve_ids(["A005"])
            self.assertEqual(len(resolved), 1)
            self.assertEqual(resolved[0]["id"], "A005")
            self.assertEqual(
                Path(resolved[0]["local_path"]),
                raw.resolve(),
            )

    def test_character_head_mode_remaps_only_matching_variant(self):
        with tempfile.TemporaryDirectory() as tmp:
            distribution = Path(tmp) / "distribution"
            assets = distribution / "assets"
            assets.mkdir(parents=True)

            (assets / "characters.md").write_text(
                "format: `ID | character | gender | head_mode | outfit | pose | path`\n"
                "A001 | ChatGPT | female | human | uniform | neutral | female_human.png\n"
                "A005 | ChatGPT | female | logo | uniform | neutral | female_logo.png\n"
                "A009 | ChatGPT | male | human | uniform | neutral | male_human.png\n",
                encoding="utf-8",
            )
            for name in (
                "female_human.png",
                "female_logo.png",
                "male_human.png",
            ):
                (distribution / name).write_bytes(
                    b"fake-png"
                )

            catalog = AssetCatalog(distribution)

            human = catalog.resolve_ids(
                ["A005"],
                head_mode="human",
            )[0]
            self.assertEqual(human["id"], "A001")
            self.assertEqual(
                human["source_asset_id"],
                "A005",
            )
            self.assertEqual(
                human["metadata"]["gender"],
                "female",
            )

            logo = catalog.resolve_ids(
                ["A001"],
                head_mode="logo",
            )[0]
            self.assertEqual(logo["id"], "A005")
            self.assertEqual(
                logo["metadata"]["gender"],
                "female",
            )

            unchanged = catalog.resolve_ids(
                ["A009"],
                head_mode="logo",
            )[0]
            self.assertEqual(
                unchanged["id"],
                "A009",
            )
            self.assertEqual(
                unchanged["metadata"]["gender"],
                "male",
            )

    def test_background_kind_and_metadata_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            distribution = Path(tmp) / "distribution"
            assets = distribution / "assets"
            assets.mkdir(parents=True)

            background = distribution / "background.png"
            background.write_bytes(b"fake-png")
            character = distribution / "character.png"
            character.write_bytes(b"fake-png")

            (assets / "backgrounds.md").write_text(
                "# Background Asset Manifest\n\n"
                "format: `ID | kind | location | variant | path`\n"
                "B001 | background | school_gate | "
                "spring_cherry_blossom | background.png\n",
                encoding="utf-8",
            )
            (assets / "characters.md").write_text(
                "# Character Asset Manifest\n\n"
                "format: `ID | character | gender | pose | path`\n"
                "A001 | ChatGPT | female | neutral | character.png\n",
                encoding="utf-8",
            )

            catalog = AssetCatalog(distribution)
            resolved = catalog.resolve_ids(
                ["B001", "A001"]
            )

            self.assertEqual(
                [item["kind"] for item in resolved],
                ["background", "character"],
            )
            self.assertEqual(
                resolved[0]["metadata"]["location"],
                "school_gate",
            )
            self.assertEqual(
                resolved[0]["metadata"]["variant"],
                "spring_cherry_blossom",
            )
            self.assertEqual(
                resolved[1]["metadata"]["character"],
                "ChatGPT",
            )

    def test_background_does_not_consume_character_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            distribution = Path(tmp) / "distribution"
            assets = distribution / "assets"
            assets.mkdir(parents=True)

            (assets / "backgrounds.md").write_text(
                "format: `ID | kind | location | variant | path`\n"
                "B001 | background | room | day | bg.png\n",
                encoding="utf-8",
            )
            (assets / "characters.md").write_text(
                "format: `ID | character | pose | path`\n"
                "A001 | One | neutral | a1.png\n"
                "A002 | Two | neutral | a2.png\n"
                "A003 | Three | neutral | a3.png\n",
                encoding="utf-8",
            )

            for name in ("bg.png", "a1.png", "a2.png", "a3.png"):
                (distribution / name).write_bytes(b"fake-png")

            catalog = AssetCatalog(distribution)
            resolved = catalog.resolve_ids(
                ["B001", "A001", "A002", "A003"]
            )
            self.assertEqual(
                [item["id"] for item in resolved],
                ["B001", "A001", "A002", "A003"],
            )

    def test_first_resolved_background_returns_registered_asset(self):
        with tempfile.TemporaryDirectory() as tmp:
            distribution = Path(tmp) / "distribution"
            assets = distribution / "assets"
            assets.mkdir(parents=True)
            (assets / "backgrounds.md").write_text(
                "format: `ID | kind | location | variant | path`\n"
                "B001 | background | room | day | bg.png\n",
                encoding="utf-8",
            )
            (distribution / "bg.png").write_bytes(
                b"fake-png"
            )

            catalog = AssetCatalog(distribution)
            fallback = catalog.first_resolved(
                kind="background"
            )
            self.assertIsNotNone(fallback)
            self.assertEqual(fallback["id"], "B001")
            self.assertEqual(
                fallback["kind"],
                "background",
            )

    def test_unknown_or_unsafe_asset_ids_do_not_resolve(self):
        with tempfile.TemporaryDirectory() as tmp:
            distribution = Path(tmp) / "distribution"
            assets = distribution / "assets"
            assets.mkdir(parents=True)
            (assets / "characters.md").write_text(
                "A001 | Test | ../outside.png\n",
                encoding="utf-8",
            )

            catalog = AssetCatalog(distribution)
            self.assertEqual(len(catalog), 0)
            self.assertEqual(
                catalog.resolve_ids(["A001", "NOPE"]),
                [],
            )


if __name__ == "__main__":
    unittest.main()
