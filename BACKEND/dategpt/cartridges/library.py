from __future__ import annotations

import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from ..assets import (
    iter_asset_records,
    resolve_authored_asset_path,
)
from ..bootstrap.models import ScenarioManifest
from ..fs import safe_path_segment


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

        manifest = ScenarioManifest.parse(
            manifest_path.read_text(encoding="utf-8")
        )
        if manifest.format_version != SUPPORTED_FORMAT_VERSION:
            raise UnsupportedCartridgeFormat(
                "unsupported FORMAT_VERSION: {} (supported: {})".format(
                    manifest.format_version,
                    SUPPORTED_FORMAT_VERSION,
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
            self._mirror_authored_assets(
                source_distribution=inspected.path,
                target_distribution=temp,
                content_root=inspected.content_root,
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

    @staticmethod
    def _mirror_authored_assets(
        *,
        source_distribution: Path,
        target_distribution: Path,
        content_root: str,
    ) -> None:
        for record in iter_asset_records(
            source_distribution
        ):
            bundled = (
                source_distribution
                / Path(record.path)
            ).resolve()
            if bundled.is_file():
                continue

            source_file = resolve_authored_asset_path(
                source_distribution,
                content_root,
                record.path,
            )
            if source_file is None:
                continue
            if source_file.is_symlink():
                raise ValueError(
                    "asset path resolves to symlink: {}".format(
                        record.path
                    )
                )

            relative = Path(record.path)
            destination = (
                target_distribution
                / relative
            ).resolve()
            try:
                destination.relative_to(
                    target_distribution.resolve()
                )
            except ValueError as exc:
                raise ValueError(
                    "asset path escapes installed cartridge: {}".format(
                        record.path
                    )
                ) from exc

            destination.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            shutil.copy2(
                source_file,
                destination,
            )

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
