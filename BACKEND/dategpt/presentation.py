from __future__ import annotations

import re
from typing import Dict, List


_SPEAKER_RE = re.compile(
    r"^\s*(?:\*\*)?([^\n:：]{1,40}?)(?:\*\*)?\s*[:：]\s*(.+?)\s*$"
)
_SENTENCE_RE = re.compile(
    r".+?(?:[.!?…。！？]+(?:[\"'”’」』)\]]*)|$)",
    re.DOTALL,
)


def parse_presentation(text: str) -> List[Dict[str, str]]:
    """Split one model reply into VN-sized narration/dialogue segments.

    The runtime prompt asks the model to format spoken dialogue as
    Character: text. We preserve that convention and split each block into
    sentence-sized units so the frontend can page through them.
    """

    raw = str(text or "").replace("\r\n", "\n").strip()
    if not raw:
        return []

    segments: List[Dict[str, str]] = []
    narration_lines: List[str] = []

    def flush_narration() -> None:
        if not narration_lines:
            return
        paragraph = " ".join(
            line.strip()
            for line in narration_lines
            if line.strip()
        ).strip()
        narration_lines.clear()
        for sentence in _split_sentences(paragraph):
            segments.append(
                {
                    "kind": "narration",
                    "speaker": "",
                    "text": sentence,
                }
            )

    for line in raw.split("\n"):
        stripped = line.strip()
        if not stripped:
            flush_narration()
            continue

        match = _SPEAKER_RE.match(stripped)
        if match and _looks_like_speaker(match.group(1)):
            flush_narration()
            speaker = _clean_speaker(match.group(1))
            for sentence in _split_sentences(
                match.group(2).strip()
            ):
                segments.append(
                    {
                        "kind": "dialogue",
                        "speaker": speaker,
                        "text": sentence,
                    }
                )
            continue

        narration_lines.append(stripped)

    flush_narration()

    if not segments:
        return [
            {
                "kind": "narration",
                "speaker": "",
                "text": raw,
            }
        ]
    return segments


def _split_sentences(text: str) -> List[str]:
    value = " ".join(str(text).split())
    if not value:
        return []

    parts = [
        match.group(0).strip()
        for match in _SENTENCE_RE.finditer(value)
        if match.group(0).strip()
    ]
    return parts or [value]


def _clean_speaker(value: str) -> str:
    return str(value).strip().strip("*").strip()


def _looks_like_speaker(value: str) -> bool:
    speaker = _clean_speaker(value)
    if not speaker or len(speaker) > 30:
        return False
    if any(mark in speaker for mark in ".!?…。！？/\\"):
        return False
    return True
