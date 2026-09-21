from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional

from .markdown import parse_markdown_fields


_CORE_CONTROL_NAMES = {
    "language",
    "initiative",
    "world_consistency",
    "dev_commands",
    "paused",
}

_RESERVED_CONTROL_NAMES = _CORE_CONTROL_NAMES | {
    "game_name",
    "game_id",
    "game_source",
    "play_mode",
    "player_character_mode",
    "main_character",
    "location",
    "time",
    "scene",
    "present_entities",
    "active_story",
    "relevant_flags",
}


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
    control_defaults: Dict[str, str] = field(
        default_factory=dict
    )

    @classmethod
    def parse(cls, text: str) -> "ScenarioManifest":
        fields = parse_markdown_fields(text)
        game_name = fields.get("GAME_NAME", "").strip()
        content_root = fields.get("CONTENT_ROOT", "").strip()
        if not game_name:
            raise ValueError("file-manifest.md is missing GAME_NAME")
        if not content_root:
            raise ValueError("file-manifest.md is missing CONTENT_ROOT")
        control_defaults = {}
        for key, value in fields.items():
            if not key.startswith("control."):
                continue
            name = key[len("control."):].strip()
            if not name or name in _RESERVED_CONTROL_NAMES:
                continue
            control_defaults[name] = str(value).strip()

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
            control_defaults=control_defaults,
        )


@dataclass
class InitComplete:
    game_name: str
    game_id: str
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
        values = {
            "world_consistency": self.world_consistency,
            "initiative": self.initiative,
            "language": self.language,
            "dev_commands": self.dev_commands,
            "paused": self.paused,
        }
        values.update(self.extra_fields)
        return values

    def apply_control_values(
        self,
        values: Mapping[str, Any],
    ) -> None:
        self.world_consistency = str(
            values.get(
                "world_consistency",
                self.world_consistency,
            )
        )
        self.initiative = str(
            values.get(
                "initiative",
                self.initiative,
            )
        )
        self.language = str(
            values.get("language", self.language)
        )
        self.dev_commands = _parse_bool(
            str(
                values.get(
                    "dev_commands",
                    self.dev_commands,
                )
            ),
            self.dev_commands,
        )
        self.paused = _parse_bool(
            str(
                values.get("paused", self.paused)
            ),
            self.paused,
        )

        extras = {}
        for key, value in values.items():
            name = str(key)
            if name in _CORE_CONTROL_NAMES:
                continue
            extras[name] = str(value)
        self.extra_fields = extras

    def render(self) -> str:
        lines = [
            "# INIT COMPLETE",
            "",
            "- game_name: {}".format(self.game_name),
            "- game_id: {}".format(self.game_id),
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
