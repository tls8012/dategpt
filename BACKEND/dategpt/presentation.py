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
        return self

    def public_dict(self) -> Dict[str, str]:
        return {
            "kind": self.kind,
            "speaker": self.speaker,
            "text": self.text,
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

    def public_segments(self) -> List[Dict[str, str]]:
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
