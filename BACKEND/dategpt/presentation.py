from __future__ import annotations

from typing import Dict, List, Literal

from pydantic import BaseModel, Field, model_validator


class VNLine(BaseModel):
    """One visual-novel presentation unit.

    Keep each unit as close to one complete sentence as practical. Narration
    has no speaker. Dialogue names the speaking character explicitly.
    """

    kind: Literal["narration", "dialogue", "system"] = Field(
        description=(
            "narration for prose/action, dialogue for spoken character lines, "
            "system only for out-of-world notices"
        )
    )
    speaker: str = Field(
        default="",
        description=(
            "Exact visible speaker name for dialogue; empty for narration/system"
        ),
    )
    text: str = Field(
        min_length=1,
        description=(
            "One complete display unit, preferably one sentence. "
            "Do not include a 'Speaker:' prefix."
        ),
    )
    assets: List[str] = Field(
        default_factory=list,
        description=(
            "Registered asset IDs to display with this unit. "
            "Use a matching registered background at scene start or when "
            "location/time changes, and matching registered SCGs for visible "
            "named characters when available. Use only IDs explicitly "
            "available in the current game context; never invent file paths "
            "or URLs."
        ),
    )

    @model_validator(mode="after")
    def validate_speaker(self):
        self.text = self.text.strip()
        self.speaker = self.speaker.strip()

        if self.kind == "dialogue" and not self.speaker:
            raise ValueError(
                "dialogue segments require a speaker"
            )
        if self.kind != "dialogue":
            self.speaker = ""

        normalized_assets = []
        seen_assets = set()
        for asset_id in self.assets:
            value = str(asset_id).strip()
            if not value or value in seen_assets:
                continue
            normalized_assets.append(value)
            seen_assets.add(value)
        self.assets = normalized_assets
        return self

    def public_dict(self) -> Dict[str, object]:
        return {
            "kind": self.kind,
            "speaker": self.speaker,
            "text": self.text,
            "assets": list(self.assets),
        }


class VNResponse(BaseModel):
    """Structured final response rendered by the DateGPT visual-novel UI."""

    segments: List[VNLine] = Field(
        min_length=1,
        description=(
            "Ordered visual-novel display units. Split narration and every "
            "speaker change. Prefer one sentence per segment so the UI can "
            "advance naturally with Space."
        ),
    )

    def plain_text(self) -> str:
        lines = []
        for segment in self.segments:
            if segment.kind == "dialogue":
                lines.append(
                    "{}: {}".format(
                        segment.speaker,
                        segment.text,
                    )
                )
            else:
                lines.append(segment.text)
        return "\n".join(lines).strip()

    def public_segments(self) -> List[Dict[str, object]]:
        return [
            segment.public_dict()
            for segment in self.segments
        ]


def coerce_vn_response(value) -> VNResponse:
    if isinstance(value, VNResponse):
        return value
    if isinstance(value, dict):
        return VNResponse.model_validate(value)
    if hasattr(value, "model_dump"):
        return VNResponse.model_validate(
            value.model_dump()
        )
    raise TypeError(
        "structured_response is not a VNResponse-compatible value"
    )
