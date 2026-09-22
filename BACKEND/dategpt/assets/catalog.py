from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, Iterator, List, Optional


_IMAGE_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
}


@dataclass(frozen=True)
class AssetRecord:
    asset_id: str
    path: str
    kind: str = "image"
    metadata: Dict[str, str] = field(
        default_factory=dict
    )

    def public_dict(
        self,
        *,
        local_path: Optional[Path] = None,
    ) -> dict:
        data = {
            "id": self.asset_id,
            "kind": self.kind,
            "path": self.path,
            "metadata": dict(self.metadata),
        }
        if local_path is not None:
            data["local_path"] = str(local_path)
        return data


def normalize_asset_path(value: str) -> Optional[str]:
    text = str(value).strip().replace("\\", "/")
    if text.startswith("./"):
        text = text[2:]

    path = PurePosixPath(text)
    if (
        not text
        or path.is_absolute()
        or any(part == ".." for part in path.parts)
    ):
        return None

    normalized = str(path)
    if Path(normalized).suffix.casefold() not in _IMAGE_SUFFIXES:
        return None
    return normalized



def _format_columns(line: str) -> Optional[List[str]]:
    stripped = line.strip()
    if not stripped.casefold().startswith("format:"):
        return None

    value = stripped.split(":", 1)[1].strip()
    value = value.strip("\`").strip()
    columns = [
        item.strip()
        for item in value.split("|")
    ]
    if (
        len(columns) < 2
        or columns[0].casefold() != "id"
        or columns[-1].casefold() != "path"
    ):
        return None
    return columns


def _asset_kind(
    manifest: Path,
    metadata: Dict[str, str],
) -> str:
    explicit = metadata.get("kind", "").strip()
    if explicit:
        return explicit.casefold()
    if (
        "character" in metadata
        or manifest.stem.casefold()
        in {"character", "characters"}
    ):
        return "character"
    if manifest.stem.casefold() in {
        "background",
        "backgrounds",
    }:
        return "background"
    return "image"


def iter_asset_records(
    distribution_root: Path,
) -> Iterator[AssetRecord]:
    root = Path(distribution_root).expanduser().resolve()
    assets_root = root / "assets"
    if not assets_root.is_dir():
        return

    seen: Dict[str, str] = {}
    for manifest in sorted(assets_root.rglob("*.md")):
        try:
            text = manifest.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        columns_spec: Optional[List[str]] = None
        for raw_line in text.splitlines():
            line = raw_line.strip()
            parsed_format = _format_columns(line)
            if parsed_format is not None:
                columns_spec = parsed_format
                continue

            if (
                not line
                or line.startswith("#")
                or "|" not in line
            ):
                continue

            columns = [
                item.strip()
                for item in line.split("|")
            ]
            if len(columns) < 2:
                continue

            asset_id = columns[0]
            asset_path = normalize_asset_path(
                columns[-1]
            )
            if not asset_id or asset_path is None:
                continue

            if asset_id in seen:
                continue

            metadata: Dict[str, str] = {}
            if (
                columns_spec is not None
                and len(columns_spec) == len(columns)
            ):
                metadata = {
                    key.strip().casefold(): value
                    for key, value in zip(
                        columns_spec[1:-1],
                        columns[1:-1],
                    )
                    if key.strip()
                }

            seen[asset_id] = asset_path
            yield AssetRecord(
                asset_id=asset_id,
                path=asset_path,
                kind=_asset_kind(
                    manifest,
                    metadata,
                ),
                metadata=metadata,
            )

def infer_content_base(
    distribution_root: Path,
    content_root: str,
) -> Optional[Path]:
    root = Path(distribution_root).expanduser().resolve()
    parts = [
        part
        for part in PurePosixPath(
            str(content_root).strip().replace("\\", "/")
        ).parts
        if part not in {"", "."}
    ]
    if not parts:
        return None

    cursor = root
    for expected in reversed(parts):
        if cursor.name != expected:
            return None
        cursor = cursor.parent
    return cursor


def resolve_authored_asset_path(
    distribution_root: Path,
    content_root: str,
    authored_path: str,
) -> Optional[Path]:
    normalized = normalize_asset_path(authored_path)
    if normalized is None:
        return None

    root = Path(distribution_root).expanduser().resolve()
    relative = Path(*PurePosixPath(normalized).parts)

    candidates: List[Path] = [
        root / relative,
        root.parent / relative,
    ]

    content_base = infer_content_base(
        root,
        content_root,
    )
    if content_base is not None:
        candidates.append(content_base / relative)

    seen = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.is_file():
            return resolved
    return None


class AssetCatalog:
    def __init__(
        self,
        distribution_root: Path,
        *,
        content_root: str = "",
    ) -> None:
        self.root = Path(
            distribution_root
        ).expanduser().resolve()
        self.content_root = str(content_root).strip()
        self.records: Dict[str, AssetRecord] = {
            record.asset_id: record
            for record in iter_asset_records(self.root)
        }

    def resolve(
        self,
        asset_id: str,
    ) -> Optional[dict]:
        record = self.records.get(
            str(asset_id).strip()
        )
        if record is None:
            return None

        local_path = resolve_authored_asset_path(
            self.root,
            self.content_root,
            record.path,
        )
        if local_path is None:
            return None

        return record.public_dict(
            local_path=local_path,
        )

    def first_resolved(
        self,
        *,
        kind: str,
    ) -> Optional[dict]:
        wanted = str(kind).strip().casefold()
        for record in self.records.values():
            if record.kind.casefold() != wanted:
                continue
            resolved = self.resolve(record.asset_id)
            if resolved is not None:
                return resolved
        return None

    def resolve_ids(
        self,
        asset_ids: Iterable[str],
        *,
        character_limit: int = 3,
    ) -> List[dict]:
        resolved = []
        seen = set()
        backgrounds = 0
        characters = 0

        for value in asset_ids:
            asset_id = str(value).strip()
            if not asset_id or asset_id in seen:
                continue
            seen.add(asset_id)

            record = self.resolve(asset_id)
            if record is None:
                continue

            kind = str(
                record.get("kind", "")
            ).casefold()
            if kind == "background":
                if backgrounds >= 1:
                    continue
                backgrounds += 1
            elif kind == "character":
                if characters >= max(
                    1,
                    int(character_limit),
                ):
                    continue
                characters += 1

            resolved.append(record)

        return resolved

    def __len__(self) -> int:
        return len(self.records)
