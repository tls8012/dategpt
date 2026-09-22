import tempfile
import unittest
from pathlib import Path

from dategpt.cartridges import (
    CartridgeLibrary,
    UnsupportedCartridgeFormat,
)
from dategpt.scenarios import CharacterManifestIndex


def write_datellm_distribution(
    root: Path,
    *,
    build_version: str = "1",
    format_version: str = "1",
):
    root.mkdir(parents=True)
    (root / "file-manifest.md").write_text(
        "# datellm Distribution\n\n"
        "GAME_NAME: datellm\n"
        "BUILD_VERSION: {}\n"
        "FORMAT_VERSION: {}\n"
        "CONTENT_ROOT: datellm/distribution\n".format(
            build_version,
            format_version,
        ),
        encoding="utf-8",
    )
    (root / "character_manifest.md").write_text(
        (
            "ChatGPT | roles: 같은 반 학생, 연애 대상, LLM | "
            "path: entities/characters/ChatGPT.md\n"
            "Claude | roles: 같은 반 학생, 연애 대상, LLM | "
            "path: entities/characters/Claude.md\n"
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
    (root / "entities" / "characters" / "Claude.md").write_text(
        "# Claude",
        encoding="utf-8",
    )
    (root / "story").mkdir()
    (root / "story" / "welcome.md").write_text(
        "welcome",
        encoding="utf-8",
    )


class CartridgeTests(unittest.TestCase):
    def test_datellm_shape_installs_without_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "datellm" / "distribution"
            write_datellm_distribution(source)

            library = CartridgeLibrary(
                base / "installed"
            )
            installed = library.install_directory(
                source.parent
            )

            self.assertEqual(
                installed.game_name,
                "datellm",
            )
            self.assertEqual(
                installed.build_version,
                "1",
            )
            self.assertTrue(
                (
                    installed.path
                    / "entities"
                    / "characters"
                    / "ChatGPT.md"
                ).is_file()
            )
            self.assertFalse(
                (installed.path / "assets").exists()
            )

            resolved = library.resolve(
                "datellm",
                build_version="1",
            )
            self.assertEqual(
                resolved.path,
                installed.path,
            )

    def test_install_mirrors_raw_assets_referenced_by_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cartridge_root = base / "repo" / "datellm"
            distribution = cartridge_root / "distribution"
            write_datellm_distribution(distribution)

            assets = distribution / "assets"
            assets.mkdir()
            raw_relative = (
                "datellm/raw/assets/characters/chatgpt/"
                "female/logo/uniform_neutral.png"
            )
            (assets / "characters.md").write_text(
                "A005 | ChatGPT | female | logo | uniform | "
                "neutral | {}\n".format(raw_relative),
                encoding="utf-8",
            )

            raw = (
                base
                / "repo"
                / Path(raw_relative)
            )
            raw.parent.mkdir(parents=True)
            raw.write_bytes(b"fake-png")

            library = CartridgeLibrary(
                base / "installed"
            )
            installed = library.install_directory(
                cartridge_root
            )

            mirrored = installed.path / Path(
                raw_relative
            )
            self.assertTrue(mirrored.is_file())
            self.assertEqual(
                mirrored.read_bytes(),
                b"fake-png",
            )
            self.assertEqual(
                installed.asset_count,
                1,
            )

    def test_install_rejects_missing_referenced_asset(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cartridge_root = base / "repo" / "datellm"
            distribution = cartridge_root / "distribution"
            write_datellm_distribution(distribution)

            assets = distribution / "assets"
            assets.mkdir()
            (assets / "backgrounds.md").write_text(
                "format: `ID | kind | location | variant | path`\n"
                "B001 | background | classroom | day | "
                "datellm/raw/assets/background/missing.png\n",
                encoding="utf-8",
            )

            library = CartridgeLibrary(
                base / "installed"
            )
            with self.assertRaisesRegex(
                FileNotFoundError,
                "referenced asset not found",
            ):
                library.install_directory(
                    cartridge_root
                )

    def test_datellm_character_manifest_without_bullets_parses(self):
        text = (
            "ChatGPT | roles: 같은 반 학생, 연애 대상, LLM | "
            "path: entities/characters/ChatGPT.md\n"
        )
        index = CharacterManifestIndex.from_texts(
            distribution_text=text
        )
        self.assertEqual(
            index.resolve_unique("ChatGPT").path,
            "entities/characters/ChatGPT.md",
        )
        self.assertEqual(
            index.resolve_unique("LLM").path,
            "entities/characters/ChatGPT.md",
        )

    def test_unsupported_format_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "distribution"
            write_datellm_distribution(
                source,
                format_version="2",
            )
            library = CartridgeLibrary(
                Path(tmp) / "installed"
            )

            with self.assertRaises(
                UnsupportedCartridgeFormat
            ):
                library.install_directory(source)

    def test_latest_build_is_selected_when_omitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            library = CartridgeLibrary(
                base / "installed"
            )

            for version in ("1", "2", "10"):
                source = (
                    base / ("source-" + version)
                )
                write_datellm_distribution(
                    source,
                    build_version=version,
                )
                library.install_directory(source)

            self.assertEqual(
                library.resolve(
                    "datellm"
                ).build_version,
                "10",
            )


if __name__ == "__main__":
    unittest.main()
