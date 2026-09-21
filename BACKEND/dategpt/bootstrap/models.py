from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional

from .markdown import parse_markdown_fields


def _parse_bool(value: str, default: bool = False) -> bool:
    normalized = str(value).strip().casefold()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    return default


@dataclass(frozen=True)
class ScenarioManifest:
    game_name: str
    content_root: str
    build_version: str = "unversioned"
    format_version: str = "1"

    @classmethod
    def parse(cls, text: str) -> "ScenarioManifest":
        fields = parse_markdown_fields(text)
        game_name = fields.get("GAME_NAME", "").strip()
        content_root = fields.get("CONTENT_ROOT", "").strip()
        if not game_name:
            raise ValueError("file-manifest.md is missing GAME_NAME")
        if not content_root:
            raise ValueError("file-manifest.md is missing CONTENT_ROOT")
        return cls(
            game_name=game_name,
            content_root=content_root,
            build_version=(
                fields.get("BUILD_VERSION", "").strip()
                or "unversioned"
            ),
            format_version=(
                fields.get("FORMAT_VERSION", "").strip()
                or "1"
            ),
        )


@dataclass(frozen=True)
class GameSource:
    game_name: str
    distribution_url: str
    manifest_url: str
    content_root: str

    @classmethod
    def parse(cls, text: str) -> "GameSource":
        fields = parse_markdown_fields(text)
        game_name = fields.get("game_name", "").strip()
        if not game_name:
            raise ValueError("game_source.md is missing game_name")
        return cls(
            game_name=game_name,
            distribution_url=fields.get("distribution_url", "").strip(),
            manifest_url=fields.get("manifest_url", "").strip(),
            content_root=fields.get("content_root", "").strip(),
        )

    def render(self) -> str:
        return (
            "# GAME SOURCE\n\n"
            "- game_name: {}\n"
            "- distribution_url: {}\n"
            "- manifest_url: {}\n"
            "- content_root: {}\n"
        ).format(
            self.game_name,
            self.distribution_url,
            self.manifest_url,
            self.content_root,
        )


@dataclass
class InitComplete:
    game_name: str
    game_id: str
    game_source: str = "../game_source.md"
    play_mode: str = "player"
    player_character_mode: str = "original"
    main_character: str = "entities/main_character.md"
    world_consistency: str = "medium"
    initiative: str = "medium"
    language: str = "한국어"
    dev_commands: bool = False
    paused: bool = False
    current: Dict[str, str] = field(default_factory=dict)
    extra_fields: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def parse(cls, text: str) -> "InitComplete":
        fields = parse_markdown_fields(text)
        required = ("game_name", "game_id")
        for key in required:
            if not fields.get(key):
                raise ValueError("init완료.md is missing {}".format(key))

        known = {
            "game_name",
            "game_id",
            "game_source",
            "play_mode",
            "player_character_mode",
            "main_character",
            "world_consistency",
            "initiative",
            "language",
            "dev_commands",
            "paused",
            "location",
            "time",
            "scene",
            "present_entities",
            "active_story",
            "relevant_flags",
        }
        current_keys = {
            "location",
            "time",
            "scene",
            "present_entities",
            "active_story",
            "relevant_flags",
        }
        return cls(
            game_name=fields["game_name"],
            game_id=fields["game_id"],
            game_source=fields.get("game_source", "../game_source.md"),
            play_mode=fields.get("play_mode", "player"),
            player_character_mode=fields.get("player_character_mode", "original"),
            main_character=fields.get("main_character", "entities/main_character.md"),
            world_consistency=fields.get("world_consistency", "medium"),
            initiative=fields.get("initiative", "medium"),
            language=fields.get("language", "한국어"),
            dev_commands=_parse_bool(fields.get("dev_commands", "false")),
            paused=_parse_bool(fields.get("paused", "false")),
            current={key: fields.get(key, "") for key in current_keys},
            extra_fields={
                key: value for key, value in fields.items() if key not in known
            },
        )

    def control_values(self) -> Dict[str, Any]:
        return {
            "world_consistency": self.world_consistency,
            "initiative": self.initiative,
            "language": self.language,
            "dev_commands": self.dev_commands,
            "paused": self.paused,
        }

    def render(self) -> str:
        lines = [
            "# INIT COMPLETE",
            "",
            "- game_name: {}".format(self.game_name),
            "- game_id: {}".format(self.game_id),
            "- game_source: {}".format(self.game_source),
            "- play_mode: {}".format(self.play_mode),
            "- player_character_mode: {}".format(self.player_character_mode),
            "- main_character: {}".format(self.main_character),
            "- world_consistency: {}".format(self.world_consistency),
            "- initiative: {}".format(self.initiative),
            "- language: {}".format(self.language),
            "- dev_commands: {}".format(str(self.dev_commands).lower()),
            "- paused: {}".format(str(self.paused).lower()),
        ]
        for key, value in self.extra_fields.items():
            lines.append("- {}: {}".format(key, value))

        lines.extend(["", "## Current"])
        for key in (
            "location",
            "time",
            "scene",
            "present_entities",
            "active_story",
            "relevant_flags",
        ):
            lines.append("- {}: {}".format(key, self.current.get(key, "")))
        return "\n".join(lines) + "\n"
