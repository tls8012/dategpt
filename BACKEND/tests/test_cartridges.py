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
    (root / "story" / "story_manifest.md").write_text(
        "# STORY MANIFEST",
        encoding="utf-8",
    )
    (root / "story" / "전학 첫날.md").write_text(
        "# FIRST DAY",
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

    def test_declared_story_path_with_spaces_is_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "distribution"
            write_datellm_distribution(source)

            inspected = CartridgeLibrary(
                Path(tmp) / "installed"
            ).inspect_directory(source)

            self.assertEqual(
                inspected.content_root,
                ".",
            )

    def test_missing_declared_entrypoint_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "distribution"
            write_datellm_distribution(source)
            (
                source / "story" / "전학 첫날.md"
            ).unlink()

            with self.assertRaises(FileNotFoundError):
                CartridgeLibrary(
                    Path(tmp) / "installed"
                ).inspect_directory(source)

    def test_broken_character_manifest_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "distribution"
            write_datellm_distribution(source)
            (
                source / "character_manifest.md"
            ).write_text(
                "Missing | path: entities/characters/없음.md\n",
                encoding="utf-8",
            )

            with self.assertRaises(FileNotFoundError):
                CartridgeLibrary(
                    Path(tmp) / "installed"
                ).inspect_directory(source)

    def test_manifest_path_cannot_escape_distribution(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "distribution"
            write_datellm_distribution(source)
            manifest = (
                source / "file-manifest.md"
            ).read_text(encoding="utf-8")
            manifest = manifest.replace(
                "welcome: story/welcome.md",
                "welcome: ../outside.md",
            )
            (
                source / "file-manifest.md"
            ).write_text(
                manifest,
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                CartridgeLibrary(
                    Path(tmp) / "installed"
                ).inspect_directory(source)


if __name__ == "__main__":
    unittest.main()
