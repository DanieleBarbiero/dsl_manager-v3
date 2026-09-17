from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from dslm3.vendor.canonical import canonical_sha256_v1


REGION_DETECTOR_ID = "connected_non_empty_cells"
REGION_DETECTOR_VERSION = "1"
_CELL_REFERENCE = re.compile(r"^\$?([A-Za-z]{1,3})\$?([1-9][0-9]*)$")


class WorkbookRegionError(RuntimeError):
    """Raised when workbook regions cannot be detected within the declared contract."""


@dataclass(frozen=True, order=True)
class CellPosition:
    row: int
    column: int

    @property
    def coordinate(self) -> str:
        return f"{column_name(self.column)}{self.row}"


@dataclass(frozen=True)
class CellRange:
    start: CellPosition
    end: CellPosition

    @property
    def reference(self) -> str:
        if self.start == self.end:
            return self.start.coordinate
        return f"{self.start.coordinate}:{self.end.coordinate}"

    def contains(self, position: CellPosition) -> bool:
        return (
            self.start.row <= position.row <= self.end.row
            and self.start.column <= position.column <= self.end.column
        )


def parse_cell_reference(value: str) -> CellPosition:
    match = _CELL_REFERENCE.fullmatch(value.strip())
    if match is None:
        raise WorkbookRegionError(f"Invalid OOXML cell reference: {value!r}.")
    column = 0
    for character in match.group(1).upper():
        column = column * 26 + ord(character) - ord("A") + 1
    return CellPosition(row=int(match.group(2)), column=column)


def parse_cell_range(value: str) -> CellRange:
    parts = value.strip().split(":", 1)
    start = parse_cell_reference(parts[0])
    end = parse_cell_reference(parts[-1])
    if end.row < start.row or end.column < start.column:
        raise WorkbookRegionError(f"Invalid OOXML cell range: {value!r}.")
    return CellRange(start=start, end=end)


def column_name(column: int) -> str:
    if column < 1:
        raise WorkbookRegionError("Cell columns are one-based positive integers.")
    result = ""
    current = column
    while current:
        current, remainder = divmod(current - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def detect_regions(
    cells: list[dict[str, Any]],
    *,
    merged_ranges: Iterable[str],
    named_range_rectangles: Iterable[str],
    max_regions: int,
) -> list[dict[str, Any]]:
    """Detect v1 regions without materialising blank rectangles.

    V1 first joins orthogonally adjacent non-blank addressed cells.  A merge or a
    resolved named-range rectangle then joins every component that it intersects.
    Empty rows or columns therefore remain segmentation boundaries unless an
    explicit merge or named range bridges them.
    """

    meaningful = {
        CellPosition(row=int(cell["row"]), column=int(cell["column"])): cell
        for cell in cells
        if _cell_is_non_empty(cell)
    }
    if not meaningful:
        return []

    parent = {position: position for position in meaningful}

    def find(position: CellPosition) -> CellPosition:
        root = position
        while parent[root] != root:
            root = parent[root]
        while parent[position] != position:
            next_position = parent[position]
            parent[position] = root
            position = next_position
        return root

    def union(left: CellPosition, right: CellPosition) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return
        if right_root < left_root:
            left_root, right_root = right_root, left_root
        parent[right_root] = left_root

    for position in sorted(meaningful):
        for neighbour in (
            CellPosition(position.row - 1, position.column),
            CellPosition(position.row, position.column - 1),
        ):
            if neighbour in meaningful:
                union(position, neighbour)

    connectors = [
        ("merge", parse_cell_range(reference)) for reference in merged_ranges
    ] + [
        ("named_range", parse_cell_range(reference))
        for reference in named_range_rectangles
    ]
    for _kind, rectangle in connectors:
        members = [position for position in meaningful if rectangle.contains(position)]
        if len(members) > 1:
            anchor = members[0]
            for member in members[1:]:
                union(anchor, member)

    groups: dict[CellPosition, list[CellPosition]] = {}
    for position in sorted(meaningful):
        groups.setdefault(find(position), []).append(position)

    ordered_groups = sorted(
        groups.values(),
        key=lambda group: (
            min(position.row for position in group),
            min(position.column for position in group),
            max(position.row for position in group),
            max(position.column for position in group),
        ),
    )
    if len(ordered_groups) > max_regions:
        raise WorkbookRegionError(
            f"Workbook exceeds excel.max_regions ({max_regions})."
        )

    regions: list[dict[str, Any]] = []
    for ordinal, positions in enumerate(ordered_groups, start=1):
        relevant_connectors = [
            (kind, rectangle)
            for kind, rectangle in connectors
            if any(rectangle.contains(position) for position in positions)
        ]
        boundary_positions = [*positions]
        for _kind, rectangle in relevant_connectors:
            boundary_positions.extend((rectangle.start, rectangle.end))
        bounds = CellRange(
            start=CellPosition(
                min(position.row for position in boundary_positions),
                min(position.column for position in boundary_positions),
            ),
            end=CellPosition(
                max(position.row for position in boundary_positions),
                max(position.column for position in boundary_positions),
            ),
        )
        region_cells = [meaningful[position] for position in sorted(positions)]
        connector_kinds = sorted({kind for kind, _rectangle in relevant_connectors})
        semantic = {
            "cells": region_cells,
            "connector_kinds": connector_kinds,
            "detector": {
                "id": REGION_DETECTOR_ID,
                "version": REGION_DETECTOR_VERSION,
            },
            "end_cell": bounds.end.coordinate,
            "region_kind": "connected_cells",
            "start_cell": bounds.start.coordinate,
        }
        regions.append(
            {
                "ordinal": ordinal,
                **semantic,
                "region_hash": canonical_sha256_v1(semantic),
            }
        )
    return regions


def _cell_is_non_empty(cell: dict[str, Any]) -> bool:
    return (
        cell.get("formula") is not None
        or cell.get("value") is not None
        or cell.get("cached_value") is not None
        or cell.get("type") != "blank"
    )
