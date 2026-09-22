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
