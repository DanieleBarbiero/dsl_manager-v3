from __future__ import annotations
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
    pos = 0
    while pos < len(text):
        end = min(len(text), pos + size)
        if end < len(text):
            boundary = text.rfind("\n", pos + size // 2, end)
            if boundary > pos:
                end = boundary + 1
        part = text[pos:end]
        if part.strip():
            result.add(
                "document_text",
                part,
                locator={**location(text, pos, end), "normalized": True, **locator},
                kind="chunk",
            )
        pos = end
