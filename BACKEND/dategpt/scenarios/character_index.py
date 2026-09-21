from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class CharacterManifestEntry:
    """One parsed public character-manifest line.

    Optional fields distinguish "not supplied by this overlay" from an
    explicitly supplied value. The current manifest format has no explicit
    syntax for clearing a list, so absent fields inherit the Distribution
    baseline when a Save entry points at the same character path.
    """

    name: str
    path: str
    aliases: Optional[Tuple[str, ...]] = None
    roles: Optional[Tuple[str, ...]] = None
    status: Optional[str] = None


@dataclass(frozen=True)
class CharacterRecord:
    name: str
    path: str
    aliases: Tuple[str, ...] = ()
    roles: Tuple[str, ...] = ()
    status: str = ""

    def public_keys(self) -> Tuple[str, ...]:
        return _dedupe(
            (self.name, *self.aliases, *self.roles)
        )


class CharacterManifestIndex:
    """Exact public character resolver built from Distribution + Save indexes.

    This is intentionally not semantic search. It only resolves exact public
    names, aliases, and role labels already declared by character_manifest.md.
    Ambiguous keys return multiple records and are never guessed.
    """

    def __init__(
        self,
        records: Iterable[CharacterRecord],
    ) -> None:
        self._records_by_path: Dict[str, CharacterRecord] = {}
        self._paths_by_key: Dict[str, List[str]] = {}

        for record in records:
            if _is_hidden(record.path):
                continue
            self._records_by_path[record.path] = record

        for record in self._records_by_path.values():
            for key in record.public_keys():
                normalized = normalize_public_key(key)
                if not normalized:
                    continue
                paths = self._paths_by_key.setdefault(
                    normalized,
                    [],
                )
                if record.path not in paths:
                    paths.append(record.path)

    @classmethod
    def from_texts(
        cls,
        distribution_text: str = "",
        save_text: str = "",
    ) -> "CharacterManifestIndex":
        records: Dict[str, CharacterRecord] = {}

        for entry in parse_character_manifest(
            distribution_text
        ):
            records[entry.path] = _record_from_entry(
                entry
            )

        for overlay in parse_character_manifest(
            save_text
        ):
            baseline = records.get(overlay.path)
            if baseline is None:
                records[overlay.path] = _record_from_entry(
                    overlay
                )
            else:
                records[overlay.path] = _apply_overlay(
                    baseline,
                    overlay,
                )

        return cls(records.values())

    def lookup(
        self,
        query: str,
    ) -> Tuple[CharacterRecord, ...]:
        key = normalize_public_key(query)
        if not key:
            return ()

        return tuple(
            self._records_by_path[path]
            for path in self._paths_by_key.get(
                key,
                (),
            )
        )

    def resolve_unique(
        self,
        query: str,
    ) -> Optional[CharacterRecord]:
        matches = self.lookup(query)
        if len(matches) != 1:
            return None
        return matches[0]

    def records(
        self,
    ) -> Tuple[CharacterRecord, ...]:
        return tuple(
            self._records_by_path.values()
        )


def parse_character_manifest(
    text: str,
) -> Tuple[CharacterManifestEntry, ...]:
    entries = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        payload = (
            line[2:].strip()
            if line.startswith("- ")
            else line
        )
        if "|" not in payload:
            continue

        segments = [
            segment.strip()
            for segment in payload.split("|")
        ]
        if not segments:
            continue

        name = segments[0].strip()
        if not name:
            continue

        fields: Dict[str, str] = {}
        for segment in segments[1:]:
            if ":" not in segment:
                continue
            key, value = segment.split(":", 1)
            fields[key.strip().casefold()] = value.strip()

        path = fields.get("path", "")
        if not path:
            continue

        entries.append(
            CharacterManifestEntry(
                name=name,
                path=path,
                aliases=_optional_list(
                    fields,
                    "aliases",
                ),
                roles=_optional_list(
                    fields,
                    "roles",
                ),
                status=(
                    fields.get("status")
                    if "status" in fields
                    else None
                ),
            )
        )

    return tuple(entries)


def normalize_public_key(
    value: str,
) -> str:
    return " ".join(
        str(value).strip().casefold().split()
    )


def _optional_list(
    fields: Dict[str, str],
    name: str,
) -> Optional[Tuple[str, ...]]:
    if name not in fields:
        return None

    value = fields[name]
    if not value:
        return ()

    return _dedupe(
        item.strip()
        for item in value.replace("，", ",").split(",")
        if item.strip()
    )


def _record_from_entry(
    entry: CharacterManifestEntry,
) -> CharacterRecord:
    return CharacterRecord(
        name=entry.name,
        path=entry.path,
        aliases=entry.aliases or (),
        roles=entry.roles or (),
        status=entry.status or "",
    )


def _apply_overlay(
    baseline: CharacterRecord,
    overlay: CharacterManifestEntry,
) -> CharacterRecord:
    return CharacterRecord(
        name=overlay.name or baseline.name,
        path=baseline.path,
        aliases=(
            overlay.aliases
            if overlay.aliases is not None
            else baseline.aliases
        ),
        roles=(
            overlay.roles
            if overlay.roles is not None
            else baseline.roles
        ),
        status=(
            overlay.status
            if overlay.status is not None
            else baseline.status
        ),
    )


def _dedupe(
    values: Iterable[str],
) -> Tuple[str, ...]:
    result = []
    seen = set()

    for value in values:
        text = str(value).strip()
        normalized = normalize_public_key(text)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(text)

    return tuple(result)


def _is_hidden(path: str) -> bool:
    normalized = str(path).replace("\\", "/").lstrip("./")
    return (
        normalized == "hidden"
        or normalized.startswith("hidden/")
    )
