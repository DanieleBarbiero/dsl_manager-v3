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
        "offset_unit": "character",
        "end_exclusive": True,
        "representation": "decoded_source",
        "line_start": source.count("\n", 0, start) + 1,
        "line_end": source.count("\n", 0, end) + 1,
    }


CHUNK_OPTIONS = __import__("contextvars").ContextVar("chunk_options", default={})


def chunks(
    result: ParseResult,
    text: str,
    size: int | None = None,
    *,
    minimum: int | None = None,
    strategy: str | None = None,
    **locator,
):
    """Reconstruct decoded normalized text exactly; offsets are characters [a,b)."""
    from dslm3.common import digest

    options = CHUNK_OPTIONS.get()
    size = size if size is not None else options.get("chunk_chars", 5000)
    minimum = minimum if minimum is not None else options.get("chunk_min_chars", 1)
    strategy = strategy or options.get("chunk_strategy", "heading_paragraph")
    if (
        type(size) is not int
        or size <= 0
        or type(minimum) is not int
        or not 1 <= minimum <= size
    ):
        raise ValueError("chunk size/minimum must satisfy 1 <= minimum <= size")
    if strategy not in {"heading_paragraph", "paragraph"}:
        raise ValueError("unknown chunk strategy")
    normalized_hash = digest(text.encode("utf-8"))
    result.metadata["chunk_contract"] = {
        "version": "4",
        "size": size,
        "minimum": minimum,
        "strategy": strategy,
    }
    boundaries = {m.end() for m in re.finditer(r"\n[ \t]*\n+", text)} | {len(text)}
    headings = []
    fence = None
    offset = 0
    for line in text.splitlines(keepends=True):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if marker:
            token = marker[1]
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
        elif fence is None and strategy == "heading_paragraph":
            match = re.match(r"^(#{1,6})[ \t]+(.+?)[ \t]*\r?\n?$", line)
            if match:
                headings.append((offset, len(match[1]), match[2].strip()))
                boundaries.add(offset)
        offset += len(line)
    ordered = sorted(boundaries)
    heading_starts = [h[0] for h in headings]
    stack = []
    hi = 0
    pos = 0
    while pos < len(text):
        while hi < len(headings) and headings[hi][0] <= pos:
            _, level, title = headings[hi]
            stack = [h for h in stack if h[0] < level] + [(level, title)]
            hi += 1
        limit = min(len(text), pos + size)
        # A new heading starts a new interval, even when the preceding paragraph
        # is smaller than the preferred minimum. This preserves exact context.
        next_heading = bisect.bisect_right(heading_starts, pos)
        if next_heading < len(heading_starts):
            limit = min(limit, heading_starts[next_heading])
        index = bisect.bisect_right(ordered, limit) - 1
        end = (
            ordered[index] if index >= 0 and ordered[index] >= pos + minimum else limit
        )
        if end <= pos:
            end = limit
        part = text[pos:end]
        result.add(
            "document_text",
            part,
            locator={
                **location(text, pos, end),
                "normalized": True,
                "normalized_sha256": normalized_hash,
                "offset_unit": "character",
                "end_exclusive": True,
                "heading_path": [h[1] for h in stack],
                **locator,
            },
            kind="chunk",
        )
        pos = end
