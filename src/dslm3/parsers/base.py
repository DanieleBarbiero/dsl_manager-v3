from __future__ import annotations
import bisect
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParseResult:
    parser: str
    evidence: list[dict] = field(default_factory=list)
    diagnostics: list[dict] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    status: str = "success"

    def add(
        self,
        type_: str,
        text: str,
        data: dict | None = None,
        locator: dict | None = None,
        kind: str = "fragment",
    ):
        item = {
            "kind": kind,
            "type": type_,
            "text": text,
            "data": data or {},
            "locator": locator or {},
        }
        self.evidence.append(item)
        return item

    def warn(self, reason: str, message: str, **details):
        self.diagnostics.append(
            {"severity": "warning", "reason": reason, "message": message, **details}
        )


def location(source: str, start: int, end: int) -> dict:
    return {
        "char_start": start,
        "char_end": end,
        "line_start": source.count("\n", 0, start) + 1,
        "line_end": source.count("\n", 0, end) + 1,
    }


def chunks(result: ParseResult, text: str, size: int = 5000, **locator):
    """Split normalized text without losing bytes, preferring semantic boundaries."""
    if size <= 0:
        raise ValueError("chunk size must be greater than zero")

    boundaries = {match.end() for match in re.finditer(r"\n[ \t]*\n+", text)}
    headings = []
    for match in re.finditer(r"(?m)^(#{1,6})[ \t]+(.+?)[ \t]*\r?$", text):
        boundaries.add(match.start())
        headings.append((match.start(), len(match.group(1)), match.group(2).strip()))
    boundaries.add(len(text))
    ordered_boundaries = sorted(boundaries)

    pos = 0
    heading_index = 0
    heading_path: list[str] = []
    while pos < len(text):
        limit = min(len(text), pos + size)
        floor = min(limit, pos + max(1, size // 2))
        index = bisect.bisect_right(ordered_boundaries, limit) - 1
        structural = ordered_boundaries[index] if index >= 0 else -1
        if structural > pos and structural >= floor:
            end = structural
        else:
            end = limit
            if end < len(text):
                newline = text.rfind("\n", floor, end)
                whitespace = max(
                    text.rfind(" ", floor, end), text.rfind("\t", floor, end)
                )
                boundary = max(newline, whitespace)
                if boundary > pos:
                    end = boundary + 1

        next_path = list(heading_path)
        while heading_index < len(headings) and headings[heading_index][0] < end:
            _, level, title = headings[heading_index]
            next_path = next_path[: max(0, level - 1)]
            next_path.append(title)
            heading_index += 1

        part = text[pos:end]
        if part.strip():
            result.add(
                "document_text",
                part,
                locator={
                    **location(text, pos, end),
                    "normalized": True,
                    "heading_path": next_path,
                    **locator,
                },
                kind="chunk",
            )
        heading_path = next_path
        pos = end
