from __future__ import annotations

import json
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from ..bootstrap.markdown import parse_markdown_fields
from ..bootstrap.models import ScenarioManifest
from ..fs import safe_path_segment
from ..scenarios.character_index import parse_character_manifest


SUPPORTED_FORMAT_VERSION = "1"


class UnsupportedCartridgeFormat(ValueError):
    pass


@dataclass(frozen=True)
class InstalledCartridge:
    game_name: str
    build_version: str
    format_version: str
    content_root: str
    path: Path

    def public_dict(self) -> dict:
        return {
            "game_name": self.game_name,
            "build_version": self.build_version,
            "format_version": self.format_version,
            "content_root": self.content_root,
        }


class CartridgeLibrary:
    """Local immutable-ish cartridge installer and resolver.

    v1 stores plain Distribution directories. ScenarioPack mounts the installed
    directory read-only. Keeping install/mount behind this class lets a future
    encrypted-at-rest backend preserve the rest of the runtime API.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def inspect_directory(
        self,
        source: Path,
    ) -> InstalledCartridge:
        distribution = self._distribution_root(source)
        manifest_path = distribution / "file-manifest.md"

        manifest_text = manifest_path.read_text(
            encoding="utf-8"
        )
        manifest = ScenarioManifest.parse(
            manifest_text
        )
        if manifest.format_version != SUPPORTED_FORMAT_VERSION:
            raise UnsupportedCartridgeFormat(
                "unsupported FORMAT_VERSION: {} (supported: {})".format(
                    manifest.format_version,
                    SUPPORTED_FORMAT_VERSION,
                )
            )

        if manifest.content_root != ".":
            raise ValueError(
                "CONTENT_ROOT must be . for packaged cartridges; got: {}".format(
                    manifest.content_root
                )
            )

        game_name = safe_path_segment(
            manifest.game_name.strip(),
            "GAME_NAME",
        )
        build_version = safe_path_segment(
            manifest.build_version.strip(),
            "BUILD_VERSION",
        )

        self._validate_declared_paths(
            distribution,
            manifest_text,
        )

        return InstalledCartridge(
            game_name=game_name,
            build_version=build_version,
            format_version=manifest.format_version,
            content_root=manifest.content_root,
            path=distribution,
        )

    def install_directory(
        self,
        source: Path,
        *,
        replace: bool = False,
    ) -> InstalledCartridge:
        inspected = self.inspect_directory(source)
        self._reject_symlinks(inspected.path)

        target = (
            self.root
            / inspected.game_name
            / inspected.build_version
        ).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists() and not replace:
            existing = self.inspect_directory(target)
            return InstalledCartridge(
                game_name=existing.game_name,
                build_version=existing.build_version,
                format_version=existing.format_version,
                content_root=existing.content_root,
                path=target,
            )

        temp = target.parent / (
            ".{}.install-{}".format(
                inspected.build_version,
                uuid.uuid4().hex,
            )
        )

        if temp.exists():
            shutil.rmtree(temp)

        try:
            shutil.copytree(
                inspected.path,
                temp,
                symlinks=False,
            )
            copied = self.inspect_directory(temp)

            if (
                copied.game_name != inspected.game_name
                or copied.build_version
                != inspected.build_version
            ):
                raise ValueError(
                    "cartridge manifest changed during installation"
                )

            if target.exists():
                shutil.rmtree(target)
            os.replace(temp, target)
        finally:
            if temp.exists():
                shutil.rmtree(temp)

        return InstalledCartridge(
            game_name=inspected.game_name,
            build_version=inspected.build_version,
            format_version=inspected.format_version,
            content_root=inspected.content_root,
            path=target,
        )

    def resolve(
        self,
        game_name: str,
        *,
        build_version: Optional[str] = None,
    ) -> InstalledCartridge:
        name = safe_path_segment(
            str(game_name).strip(),
            "game_name",
        )
        game_root = (self.root / name).resolve()

        if not game_root.exists():
            raise FileNotFoundError(
                "installed cartridge not found: {}".format(name)
            )

        if build_version is not None:
            version = safe_path_segment(
                str(build_version).strip(),
                "build_version",
            )
            path = (game_root / version).resolve()
            if not path.is_dir():
                raise FileNotFoundError(
                    "installed cartridge build not found: {}/{}".format(
                        name,
                        version,
                    )
                )
            inspected = self.inspect_directory(path)
            return InstalledCartridge(
                game_name=inspected.game_name,
                build_version=inspected.build_version,
                format_version=inspected.format_version,
                content_root=inspected.content_root,
                path=path,
            )

        builds = [
            child
            for child in game_root.iterdir()
            if child.is_dir()
            and not child.name.startswith(".")
        ]
        if not builds:
            raise FileNotFoundError(
                "no installed builds for: {}".format(name)
            )

        builds.sort(
            key=lambda path: _version_key(path.name)
        )
        chosen = builds[-1]
        inspected = self.inspect_directory(chosen)
        return InstalledCartridge(
            game_name=inspected.game_name,
            build_version=inspected.build_version,
            format_version=inspected.format_version,
            content_root=inspected.content_root,
            path=chosen,
        )

    def list_installed(
        self,
    ) -> List[InstalledCartridge]:
        items: List[InstalledCartridge] = []

        for game_root in sorted(self.root.iterdir()):
            if (
                not game_root.is_dir()
                or game_root.name.startswith(".")
            ):
                continue

            for build_root in sorted(
                game_root.iterdir(),
                key=lambda path: _version_key(path.name),
            ):
                if (
                    not build_root.is_dir()
                    or build_root.name.startswith(".")
                ):
                    continue
                try:
                    inspected = self.inspect_directory(
                        build_root
                    )
                except (
                    FileNotFoundError,
                    ValueError,
                ):
                    continue

                items.append(
                    InstalledCartridge(
                        game_name=inspected.game_name,
                        build_version=inspected.build_version,
                        format_version=inspected.format_version,
                        content_root=inspected.content_root,
                        path=build_root,
                    )
                )

        return items

    @classmethod
    def _validate_declared_paths(
        cls,
        distribution: Path,
        manifest_text: str,
    ) -> None:
        fields = {
            key.casefold(): value
            for key, value in parse_markdown_fields(
                manifest_text
            ).items()
        }

        entrypoints = {}
        for name in (
            "character_manifest",
            "welcome",
            "story_manifest",
            "start_story",
        ):
            value = str(fields.get(name, "")).strip()
            if not value:
                continue
            cls._require_distribution_file(
                distribution,
                value,
                field_name=name,
            )
            entrypoints[name] = value

        character_manifest = entrypoints.get(
            "character_manifest"
        )
        if not character_manifest:
            default = distribution / "character_manifest.md"
            if default.is_file():
                character_manifest = "character_manifest.md"

        if character_manifest:
            character_text = cls._require_distribution_file(
                distribution,
                character_manifest,
                field_name="character_manifest",
            ).read_text(encoding="utf-8")

            for entry in parse_character_manifest(
                character_text
            ):
                cls._require_distribution_file(
                    distribution,
                    entry.path,
                    field_name=(
                        "character_manifest path for {}"
                    ).format(entry.name),
                )

        context_manifest = distribution / "context_manifest.json"
        if context_manifest.is_file():
            data = json.loads(
                context_manifest.read_text(encoding="utf-8")
            )
            if not isinstance(data, dict):
                raise ValueError(
                    "context_manifest.json must contain an object"
                )
            core_files = data.get("core_files", [])
            if not isinstance(core_files, list):
                raise ValueError(
                    "context_manifest.json core_files must be a list"
                )
            for value in core_files:
                if not isinstance(value, str):
                    raise ValueError(
                        "context_manifest.json core_files entries must be strings"
                    )
                cls._require_distribution_file(
                    distribution,
                    value,
                    field_name="context_manifest core_files",
                )

    @staticmethod
    def _require_distribution_file(
        distribution: Path,
        value: str,
        *,
        field_name: str,
    ) -> Path:
        raw = str(value).strip()
        if not raw:
            raise ValueError(
                "{} path is empty".format(field_name)
            )
        if raw.startswith("game:"):
            raise ValueError(
                "{} must be Distribution-relative, not a game: pointer: {}".format(
                    field_name,
                    raw,
                )
            )
        if "\\" in raw:
            raise ValueError(
                "{} must use forward slashes: {}".format(
                    field_name,
                    raw,
                )
            )

        root = distribution.resolve()
        candidate = (root / raw).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError(
                "{} escapes Distribution root: {}".format(
                    field_name,
                    raw,
                )
            ) from exc

        if not candidate.is_file():
            raise FileNotFoundError(
                "{} points to missing file: {}".format(
                    field_name,
                    raw,
                )
            )

        return candidate

    @staticmethod
    def _distribution_root(
        source: Path,
    ) -> Path:
        root = Path(source).expanduser().resolve()
        if not root.is_dir():
            raise FileNotFoundError(str(root))

        direct = root / "file-manifest.md"
        if direct.is_file():
            return root

        nested = root / "distribution" / "file-manifest.md"
        if nested.is_file():
            return (root / "distribution").resolve()

        raise FileNotFoundError(
            "file-manifest.md not found in {} or its distribution/ child".format(
                root
            )
        )

    @staticmethod
    def _reject_symlinks(
        source: Path,
    ) -> None:
        for path in source.rglob("*"):
            if path.is_symlink():
                raise ValueError(
                    "cartridge contains symlink: {}".format(
                        path.relative_to(source)
                    )
                )


def _version_key(value: str) -> Tuple:
    parts = []
    token = ""

    for char in str(value):
        if char.isdigit():
            if token and not token[-1].isdigit():
                parts.append(token.casefold())
                token = ""
        else:
            if token and token[-1].isdigit():
                parts.append(int(token))
                token = ""
        token += char

    if token:
        parts.append(
            int(token)
            if token.isdigit()
            else token.casefold()
        )

    return tuple(
        (0, part)
        if isinstance(part, int)
        else (1, part)
        for part in parts
    )
