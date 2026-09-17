from __future__ import annotations

import hashlib
import io
import posixpath
import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree

from dslm3.vendor.canonical import (
    canonical_json_artifact_v1,
    canonical_json_v1,
    canonical_sha256_v1,
)
from dslm3.vendor.workbook_regions import (
    CellPosition,
    WorkbookRegionError,
    detect_regions,
    parse_cell_range,
    parse_cell_reference,
)


XLSX_WORKBOOK_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
)
XLSM_WORKBOOK_CONTENT_TYPE = "application/vnd.ms-excel.sheet.macroEnabled.main+xml"
DOCX_DOCUMENT_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
)
PPTX_PRESENTATION_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"
)
RELATIONSHIPS_CONTENT_TYPE = "application/vnd.openxmlformats-package.relationships+xml"
CONTENT_TYPES_NAMESPACE = "http://schemas.openxmlformats.org/package/2006/content-types"
RELATIONSHIPS_NAMESPACE = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE_DOCUMENT_RELATIONSHIP_SUFFIX = "/officeDocument"
RELATIONSHIP_ID_ATTRIBUTE = (
    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
)
VBA_PROJECT_CONTENT_TYPE = "application/vnd.ms-office.vbaProject"
ACTIVE_EXTERNAL_SCHEMES = {
    "data",
    "file",
    "javascript",
    "ms-appx",
    "ms-appx-web",
    "ms-officecmd",
    "shell",
    "vbscript",
}
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
_DRIVE_PREFIX = re.compile(r"^[a-zA-Z]:")
_PERCENT_EVASION = re.compile(r"%(?:2e|2f|3a|5c)", re.IGNORECASE)
_INVALID_PERCENT = re.compile(r"%(?![0-9a-fA-F]{2})")


@dataclass(frozen=True)
class ExcelLimits:
    max_file_bytes: int
    max_zip_entries: int
    max_uncompressed_bytes: int
    max_compression_ratio: int
    max_xml_part_bytes: int
    max_sheets: int
    max_cells: int
    max_regions: int
    max_relationships: int
    max_output_bytes: int
    worker_timeout_seconds: int
    worker_memory_bytes: int

    @classmethod
    def from_config(cls, values: dict[str, Any]) -> ExcelLimits:
        return cls(**{field: int(values[field]) for field in cls.__dataclass_fields__})

    def preflight_dict(self) -> dict[str, int]:
        return {
            "max_compression_ratio": self.max_compression_ratio,
            "max_file_bytes": self.max_file_bytes,
            "max_relationships": self.max_relationships,
            "max_cells": self.max_cells,
            "max_regions": self.max_regions,
            "max_sheets": self.max_sheets,
            "max_uncompressed_bytes": self.max_uncompressed_bytes,
            "max_xml_part_bytes": self.max_xml_part_bytes,
            "max_zip_entries": self.max_zip_entries,
        }


@dataclass(frozen=True)
class AcquiredSource:
    data: bytes
    sha256: str
    open_count: int = 1

    def cursors(self) -> tuple[io.BytesIO, io.BytesIO]:
        return io.BytesIO(self.data), io.BytesIO(self.data)

    def cursor(self) -> io.BytesIO:
        return io.BytesIO(self.data)


@dataclass(frozen=True)
class OoxmlRelationship:
    source_part: str
    relationship_id: str
    relationship_type: str
    target: str
    target_mode: str

    def manifest_record(self) -> dict[str, str]:
        return {
            "source_part": self.source_part or "/",
            "relationship_id": self.relationship_id,
            "type": self.relationship_type,
            "target": self.target,
            "target_mode": self.target_mode,
        }


@dataclass(frozen=True)
class OoxmlPreflightResult:
    source_hash: str
    extension: str
    workbook_part: str
    workbook_content_type: str
    zip_entries: int
    uncompressed_bytes: int
    xml_parts: int
    relationships: int
    sheets: int
    external_relationships: int
    limits: ExcelLimits
    relationships_detail: tuple[OoxmlRelationship, ...]
    part_content_types: tuple[tuple[str, str], ...]
    safe_part_names: tuple[str, ...]

    def report(self) -> dict[str, Any]:
        catalog = catalog_result("completed", None)
        catalog["counters"] = {
            "external_relationships": self.external_relationships,
            "relationships": self.relationships,
            "sheets": self.sheets,
            "uncompressed_bytes": self.uncompressed_bytes,
            "xml_parts": self.xml_parts,
            "zip_entries": self.zip_entries,
        }
        return {
            "catalog": catalog,
            "external_targets_dereferenced": False,
            "input": {
                "docling_input_format": "xlsx",
                "extension": self.extension,
                "source_hash": self.source_hash,
                "source_open_count": 1,
                "stream_hash": self.source_hash,
            },
            "limits": self.limits.preflight_dict(),
            "macros_executed": False,
            "network_accessed": False,
            "package": {
                "external_relationships": self.external_relationships,
                "relationships": self.relationships,
                "sheets": self.sheets,
                "uncompressed_bytes": self.uncompressed_bytes,
                "workbook_content_type": self.workbook_content_type,
                "workbook_part": self.workbook_part,
                "xml_parts": self.xml_parts,
                "zip_entries": self.zip_entries,
            },
            "status": "completed",
        }


class OoxmlPreflightError(RuntimeError):
    def __init__(
        self,
        reason: str,
        message: str,
        *,
        status: str = "rejected",
        exit_code: int = 3,
        source_hash: str | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.status = status
        self.exit_code = exit_code
        self.source_hash = source_hash

    def report(self, *, source_hash: str | None = None) -> dict[str, Any]:
        return {
            "catalog": catalog_result(self.status, self.reason),
            "external_targets_dereferenced": False,
            "input": {
                "source_hash": source_hash or self.source_hash,
                "source_open_count": 1,
            },
            "macros_executed": False,
            "message": str(self),
            "network_accessed": False,
            "status": self.status,
        }


def acquire_source_once(
    source_path: Path,
    *,
    expected_hash: str,
    max_file_bytes: int,
) -> AcquiredSource:
    digest = hashlib.sha256()
    chunks: list[bytes] = []
    total = 0
    with source_path.open("rb") as source:
        while True:
            chunk = source.read(min(1024 * 1024, max_file_bytes - total + 1))
            if not chunk:
                break
            total += len(chunk)
            if total > max_file_bytes:
                raise OoxmlPreflightError(
                    "ooxml_budget_exceeded",
                    f"Source exceeds excel.max_file_bytes ({max_file_bytes}).",
                )
            digest.update(chunk)
            chunks.append(chunk)
    actual_hash = digest.hexdigest()
    if actual_hash != expected_hash:
        raise OoxmlPreflightError(
            "source_revision_changed",
            "Source bytes do not match source_revisions.content_hash.",
            status="failed",
            exit_code=4,
            source_hash=actual_hash,
        )
    return AcquiredSource(data=b"".join(chunks), sha256=actual_hash)


def enforce_output_budget(serialized: dict[str, str], max_output_bytes: int) -> int:
    total = sum(len(value.encode("utf-8")) for value in serialized.values())
    if total > max_output_bytes:
        raise _budget("excel.max_output_bytes", max_output_bytes)
    return total


def preflight_ooxml(
    cursor: io.BytesIO,
    *,
    original_name: str,
    source_hash: str,
    limits: ExcelLimits,
) -> OoxmlPreflightResult:
    extension = Path(original_name).suffix.lower()
    if extension not in {".xlsx", ".xlsm"}:
        raise _security("Excel preflight requires an .xlsx or .xlsm name.")
    if cursor.read(4) != b"PK\x03\x04":
        raise _security("The source does not have an OOXML ZIP signature.")
    cursor.seek(0)

    try:
        package = zipfile.ZipFile(cursor)
    except (OSError, zipfile.BadZipFile) as exc:
        raise _security("The source has no valid ZIP central directory.") from exc

    with package:
        infos = package.infolist()
        if len(infos) > limits.max_zip_entries:
            raise _budget("excel.max_zip_entries", limits.max_zip_entries)
        names = _validated_names(infos)
        required_names = {"[Content_Types].xml", "_rels/.rels"}
        missing = sorted(required_names - names)
        if missing:
            raise _security(f"Required OOXML part is missing: {missing[0]}.")

        declared_total = 0
        for info in infos:
            if info.is_dir():
                continue
            declared_total += info.file_size
            if declared_total > limits.max_uncompressed_bytes:
                raise _budget(
                    "excel.max_uncompressed_bytes", limits.max_uncompressed_bytes
                )
            ratio = info.file_size / max(1, info.compress_size)
            if ratio > limits.max_compression_ratio:
                raise _budget(
                    "excel.max_compression_ratio", limits.max_compression_ratio
                )

        content_types_bytes = _read_member(
            package,
            package.getinfo("[Content_Types].xml"),
            total_before=0,
            limits=limits,
            retain=True,
            xml_part=True,
        )[0]
        content_types_root = _parse_xml(content_types_bytes, "[Content_Types].xml")
        defaults, overrides = _parse_content_types(content_types_root)
        missing_overrides = sorted(set(overrides) - names)
        if missing_overrides:
            raise _security(
                f"Content type Override references a missing part: {missing_overrides[0]!r}."
            )
        workbook_part, workbook_content_type = _select_workbook(
            extension, overrides, names
        )
        workbook_rels = _relationship_part_for(workbook_part)
        if workbook_rels not in names:
            raise _security(f"Required OOXML part is missing: {workbook_rels}.")

        retained_roots: dict[str, ElementTree.Element] = {
            "[Content_Types].xml": content_types_root
        }
        actual_total = len(content_types_bytes)
        xml_parts = 1
        for info in infos:
            if info.is_dir() or info.filename == "[Content_Types].xml":
                continue
            xml_part = _is_xml_part(info.filename, defaults, overrides)
            data, actual_total = _read_member(
                package,
                info,
                total_before=actual_total,
                limits=limits,
                retain=xml_part,
                xml_part=xml_part,
            )
            if xml_part:
                xml_parts += 1
                root = _parse_xml(data, info.filename)
                if info.filename.endswith(".rels") or info.filename == workbook_part:
                    retained_roots[info.filename] = root

        root_relationships = retained_roots.get("_rels/.rels")
        workbook_relationships = retained_roots.get(workbook_rels)
        workbook_root = retained_roots.get(workbook_part)
        if (
            root_relationships is None
            or workbook_relationships is None
            or workbook_root is None
        ):
            raise _security("A required OOXML XML part could not be parsed.")

        relationship_count = 0
        external_count = 0
        relationships_by_part: dict[str, dict[str, OoxmlRelationship]] = {}
        relationship_details: list[OoxmlRelationship] = []
        for name, root in sorted(retained_roots.items()):
            if not name.endswith(".rels"):
                continue
            owner = _owner_part_for_relationships(name)
            relation_map, external = _validate_relationships(root, owner, names)
            relationship_count += len(relation_map)
            external_count += external
            if relationship_count > limits.max_relationships:
                raise _budget("excel.max_relationships", limits.max_relationships)
            relationships_by_part[name] = relation_map
            relationship_details.extend(relation_map.values())

        root_office_targets = [
            relationship.target
            for relationship in relationships_by_part.get("_rels/.rels", {}).values()
            if relationship.relationship_type.endswith(
                OFFICE_DOCUMENT_RELATIONSHIP_SUFFIX
            )
            and relationship.target_mode == "internal"
        ]
        if root_office_targets != [workbook_part]:
            raise _security(
                "The package officeDocument relationship is invalid or ambiguous."
            )

        sheet_count = _validate_workbook_sheets(
            workbook_root,
            relationships_by_part.get(workbook_rels, {}),
            names,
        )
        if sheet_count > limits.max_sheets:
            raise _budget("excel.max_sheets", limits.max_sheets)

        return OoxmlPreflightResult(
            source_hash=source_hash,
            extension=extension,
            workbook_part=workbook_part,
            workbook_content_type=workbook_content_type,
            zip_entries=len(infos),
            uncompressed_bytes=actual_total,
            xml_parts=xml_parts,
            relationships=relationship_count,
            sheets=sheet_count,
            external_relationships=external_count,
            limits=limits,
            relationships_detail=tuple(
                sorted(
                    relationship_details,
                    key=lambda item: (item.source_part, item.relationship_id),
                )
            ),
            part_content_types=tuple(
                sorted(
                    (
                        name,
                        overrides.get(name)
                        or defaults.get(_part_extension(name))
                        or "",
                    )
                    for name in names
                    if not name.endswith("/")
                )
            ),
            safe_part_names=tuple(sorted(names)),
        )


def preflight_ooxml_metadata(
    cursor: io.BytesIO,
    *,
    original_name: str,
    source_hash: str,
    limits: ExcelLimits,
) -> None:
    """Validate an Office OOXML package before reading temporal metadata."""
    extension = Path(original_name).suffix.lower()
    if extension in {".xlsx", ".xlsm"}:
        preflight_ooxml(
            cursor,
            original_name=original_name,
            source_hash=source_hash,
            limits=limits,
        )
        return

    required_content_type = {
        ".docx": DOCX_DOCUMENT_CONTENT_TYPE,
        ".pptx": PPTX_PRESENTATION_CONTENT_TYPE,
    }.get(extension)
    if required_content_type is None:
        raise _security(
            "OOXML metadata preflight requires a .docx, .pptx, .xlsx, or .xlsm name."
        )
    if cursor.read(4) != b"PK\x03\x04":
        raise _security("The source does not have an OOXML ZIP signature.")
    cursor.seek(0)

    try:
        package = zipfile.ZipFile(cursor)
    except (OSError, zipfile.BadZipFile) as exc:
        raise _security("The source has no valid ZIP central directory.") from exc

    with package:
        infos = package.infolist()
        if len(infos) > limits.max_zip_entries:
            raise _budget("excel.max_zip_entries", limits.max_zip_entries)
        names = _validated_names(infos)
        required_names = {"[Content_Types].xml", "_rels/.rels"}
        missing = sorted(required_names - names)
        if missing:
            raise _security(f"Required OOXML part is missing: {missing[0]}.")

        declared_total = 0
        for info in infos:
            if info.is_dir():
                continue
            declared_total += info.file_size
            if declared_total > limits.max_uncompressed_bytes:
                raise _budget(
                    "excel.max_uncompressed_bytes", limits.max_uncompressed_bytes
                )
            ratio = info.file_size / max(1, info.compress_size)
            if ratio > limits.max_compression_ratio:
                raise _budget(
                    "excel.max_compression_ratio", limits.max_compression_ratio
                )

        content_types_bytes = _read_member(
            package,
            package.getinfo("[Content_Types].xml"),
            total_before=0,
            limits=limits,
            retain=True,
            xml_part=True,
        )[0]
        content_types_root = _parse_xml(content_types_bytes, "[Content_Types].xml")
        defaults, overrides = _parse_content_types(content_types_root)
        missing_overrides = sorted(set(overrides) - names)
        if missing_overrides:
            raise _security(
                f"Content type Override references a missing part: {missing_overrides[0]!r}."
            )
        main_parts = sorted(
            name for name, value in overrides.items() if value == required_content_type
        )
        if len(main_parts) != 1:
            raise _security(
                f"The {extension} extension does not match one unique main document content type."
            )
        main_part = main_parts[0]

        retained_relationships: dict[str, ElementTree.Element] = {}
        actual_total = len(content_types_bytes)
        for info in infos:
            if info.is_dir() or info.filename == "[Content_Types].xml":
                continue
            xml_part = _is_xml_part(info.filename, defaults, overrides)
            data, actual_total = _read_member(
                package,
                info,
                total_before=actual_total,
                limits=limits,
                retain=xml_part,
                xml_part=xml_part,
            )
            if xml_part:
                root = _parse_xml(data, info.filename)
                if info.filename.endswith(".rels"):
                    retained_relationships[info.filename] = root

        relationship_count = 0
        relationships_by_part: dict[str, dict[str, OoxmlRelationship]] = {}
        for name, root in sorted(retained_relationships.items()):
            owner = _owner_part_for_relationships(name)
            relation_map, _external_count = _validate_relationships(root, owner, names)
            relationship_count += len(relation_map)
            if relationship_count > limits.max_relationships:
                raise _budget("excel.max_relationships", limits.max_relationships)
            relationships_by_part[name] = relation_map

        root_office_targets = [
            relationship.target
            for relationship in relationships_by_part.get("_rels/.rels", {}).values()
            if relationship.relationship_type.endswith(
                OFFICE_DOCUMENT_RELATIONSHIP_SUFFIX
            )
            and relationship.target_mode == "internal"
        ]
        if root_office_targets != [main_part]:
            raise _security(
                "The package officeDocument relationship is invalid or ambiguous."
            )


def _validated_names(infos: list[zipfile.ZipInfo]) -> set[str]:
    names: set[str] = set()
    folded: dict[str, str] = {}
    decoded_folded: dict[str, str] = {}
    for info in infos:
        name = info.filename
        decoded = unquote(name)
        if (
            not name
            or "\\" in name
            or "//" in name
            or name.startswith(("/", "//"))
            or _DRIVE_PREFIX.match(name)
            or _CONTROL_CHARACTERS.search(name)
            or _PERCENT_EVASION.search(name)
            or _INVALID_PERCENT.search(name)
            or any(part in {"", ".", ".."} for part in PurePosixPath(name).parts)
            or decoded.startswith(("/", "//"))
            or "\\" in decoded
            or "//" in decoded
            or _DRIVE_PREFIX.match(decoded)
            or ".." in PurePosixPath(decoded).parts
        ):
            raise _security(f"Unsafe OOXML member name: {name!r}.")
        if name in names:
            raise _security(f"Duplicate OOXML member name: {name!r}.")
        folded_name = name.casefold()
        if folded_name in folded:
            raise _security(
                f"Case-fold collision between OOXML members: {folded[folded_name]!r} and {name!r}."
            )
        decoded_folded_name = decoded.casefold()
        if decoded_folded_name in decoded_folded:
            raise _security(
                "Percent-decoded collision between OOXML members: "
                f"{decoded_folded[decoded_folded_name]!r} and {name!r}."
            )
        if info.flag_bits & 0x1:
            raise _security(f"Encrypted OOXML member is not allowed: {name!r}.")
        names.add(name)
        folded[folded_name] = name
        decoded_folded[decoded_folded_name] = name
    return names


def _read_member(
    package: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    *,
    total_before: int,
    limits: ExcelLimits,
    retain: bool,
    xml_part: bool,
) -> tuple[bytes, int]:
    data = bytearray()
    total = total_before
    try:
        with package.open(info, "r") as member:
            while True:
                chunk = member.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > limits.max_uncompressed_bytes:
                    raise _budget(
                        "excel.max_uncompressed_bytes", limits.max_uncompressed_bytes
                    )
                if xml_part and len(data) + len(chunk) > limits.max_xml_part_bytes:
                    raise _budget("excel.max_xml_part_bytes", limits.max_xml_part_bytes)
                if retain:
                    data.extend(chunk)
    except OoxmlPreflightError:
        raise
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise _security(
            f"OOXML member could not be read safely: {info.filename!r}."
        ) from exc
    return bytes(data), total


def _parse_xml(data: bytes, name: str) -> ElementTree.Element:
    upper = data.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise _security(
            f"DTD or entity declaration is forbidden in OOXML part {name!r}."
        )
    try:
        return ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise _security(f"Malformed XML in OOXML part {name!r}.") from exc


def _parse_content_types(
    root: ElementTree.Element,
) -> tuple[dict[str, str], dict[str, str]]:
    if root.tag != f"{{{CONTENT_TYPES_NAMESPACE}}}Types":
        raise _security("[Content_Types].xml has an invalid root element.")
    defaults: dict[str, str] = {}
    overrides: dict[str, str] = {}
    default_names: dict[str, str] = {}
    override_names: dict[str, str] = {}
    for child in root:
        if child.tag == f"{{{CONTENT_TYPES_NAMESPACE}}}Default":
            extension = child.attrib.get("Extension", "")
            content_type = child.attrib.get("ContentType", "")
            key = extension.casefold()
            if not extension or not content_type or key in default_names:
                raise _security("Duplicate or invalid Default in [Content_Types].xml.")
            default_names[key] = extension
            defaults[key] = content_type
        elif child.tag == f"{{{CONTENT_TYPES_NAMESPACE}}}Override":
            raw_name = child.attrib.get("PartName", "")
            content_type = child.attrib.get("ContentType", "")
            if not raw_name.startswith("/") or not content_type:
                raise _security("Invalid Override in [Content_Types].xml.")
            name = raw_name[1:]
            _validate_internal_part_name(name)
            key = name.casefold()
            if key in override_names:
                raise _security("Duplicate Override in [Content_Types].xml.")
            override_names[key] = name
            overrides[name] = content_type
    if defaults.get("rels") != RELATIONSHIPS_CONTENT_TYPE:
        raise _security("The .rels content type declaration is missing or invalid.")
    return defaults, overrides


def _select_workbook(
    extension: str,
    overrides: dict[str, str],
    names: set[str],
) -> tuple[str, str]:
    required_type = (
        XLSM_WORKBOOK_CONTENT_TYPE
        if extension == ".xlsm"
        else XLSX_WORKBOOK_CONTENT_TYPE
    )
    forbidden_type = (
        XLSX_WORKBOOK_CONTENT_TYPE
        if extension == ".xlsm"
        else XLSM_WORKBOOK_CONTENT_TYPE
    )
    matching = sorted(
        name for name, value in overrides.items() if value == required_type
    )
    if len(matching) != 1:
        raise _security(
            f"The {extension} extension does not match one unique workbook content type."
        )
    if any(value == forbidden_type for value in overrides.values()):
        raise _security("Conflicting workbook content types are not allowed.")
    workbook_part = matching[0]
    if workbook_part not in names:
        raise _security(f"Required workbook part is missing: {workbook_part}.")
    return workbook_part, required_type


def _is_xml_part(
    name: str,
    defaults: dict[str, str],
    overrides: dict[str, str],
) -> bool:
    content_type = overrides.get(name)
    suffix = _part_extension(name)
    content_type = content_type or defaults.get(suffix)
    if not content_type:
        raise _security(f"OOXML part has no content type: {name!r}.")
    return (
        name.endswith((".xml", ".rels", ".vml"))
        or content_type.endswith("+xml")
        or content_type
        in {
            "application/xml",
            "text/xml",
        }
    )


def _part_extension(name: str) -> str:
    return (
        "rels"
        if name.endswith(".rels")
        else PurePosixPath(name).suffix.removeprefix(".").casefold()
    )


def _relationship_part_for(part_name: str) -> str:
    part = PurePosixPath(part_name)
    parent = "" if str(part.parent) == "." else f"{part.parent.as_posix()}/"
    return f"{parent}_rels/{part.name}.rels"


def _owner_part_for_relationships(name: str) -> str:
    if name == "_rels/.rels":
        return ""
    path = PurePosixPath(name)
    if path.parent.name != "_rels" or not path.name.endswith(".rels"):
        raise _security(f"Invalid relationship part name: {name!r}.")
    owner_name = path.name[: -len(".rels")]
    owner_parent = path.parent.parent
    return (
        owner_name
        if str(owner_parent) == "."
        else f"{owner_parent.as_posix()}/{owner_name}"
    )


def _validate_relationships(
    root: ElementTree.Element,
    owner_part: str,
    package_names: set[str],
) -> tuple[dict[str, OoxmlRelationship], int]:
    if root.tag != f"{{{RELATIONSHIPS_NAMESPACE}}}Relationships":
        raise _security("A relationship part has an invalid root element.")
    relations: dict[str, OoxmlRelationship] = {}
    external_count = 0
    for rel in _relationship_elements(root):
        rel_id = rel.attrib.get("Id", "")
        rel_type = rel.attrib.get("Type", "")
        target = rel.attrib.get("Target", "")
        if not rel_id or not rel_type or not target or rel_id in relations:
            raise _security("Relationship attributes are missing or duplicated.")
        target_mode = rel.attrib.get("TargetMode", "Internal").casefold()
        if target_mode not in {"internal", "external"}:
            raise _security("Relationship TargetMode is invalid.")
        if target_mode == "external":
            _validate_external_target(target)
            external_count += 1
            relations[rel_id] = OoxmlRelationship(
                source_part=owner_part,
                relationship_id=rel_id,
                relationship_type=rel_type,
                target=target,
                target_mode="external",
            )
            continue
        normalized = _normalize_internal_target(owner_part, target)
        if normalized not in package_names:
            raise _security(f"Internal relationship target is missing: {normalized!r}.")
        relations[rel_id] = OoxmlRelationship(
            source_part=owner_part,
            relationship_id=rel_id,
            relationship_type=rel_type,
            target=normalized,
            target_mode="internal",
        )
    return relations, external_count


def _relationship_elements(root: ElementTree.Element) -> list[ElementTree.Element]:
    expected = f"{{{RELATIONSHIPS_NAMESPACE}}}Relationship"
    elements = list(root)
    if any(child.tag != expected for child in elements):
        raise _security("A relationship part contains an unexpected element.")
    return elements


def _normalize_internal_target(owner_part: str, target: str) -> str:
    decoded = unquote(target)
    if (
        not decoded
        or _CONTROL_CHARACTERS.search(decoded)
        or "\\" in decoded
        or _DRIVE_PREFIX.match(decoded)
        or _PERCENT_EVASION.search(target)
    ):
        raise _security("An internal relationship target is invalid.")
    try:
        split = urlsplit(decoded)
    except ValueError as exc:
        raise _security(
            "An internal relationship target is not a valid URI reference."
        ) from exc
    if split.scheme or split.netloc or split.query:
        raise _security(
            "An internal relationship target must remain inside the package."
        )
    rooted = split.path.startswith("/")
    target_path = split.path.lstrip("/")
    base = "" if rooted else posixpath.dirname(owner_part)
    normalized = posixpath.normpath(posixpath.join(base, target_path))
    if normalized in {"", ".", ".."} or normalized.startswith("../"):
        raise _security("An internal relationship target escapes the package.")
    _validate_internal_part_name(normalized)
    return normalized


def _validate_internal_part_name(name: str) -> None:
    if (
        not name
        or name.startswith("/")
        or "\\" in name
        or _DRIVE_PREFIX.match(name)
        or _CONTROL_CHARACTERS.search(name)
        or any(part in {"", ".", ".."} for part in PurePosixPath(name).parts)
    ):
        raise _security(f"Invalid OOXML part name: {name!r}.")


def _validate_external_target(target: str) -> None:
    if _CONTROL_CHARACTERS.search(target):
        raise OoxmlPreflightError(
            "ooxml_external_target_invalid",
            "An external relationship target contains control characters.",
        )
    try:
        split = urlsplit(target)
        username = split.username
        password = split.password
    except ValueError as exc:
        raise OoxmlPreflightError(
            "ooxml_external_target_invalid",
            "An external relationship target is not a valid absolute URI.",
        ) from exc
    if (
        not split.scheme
        or split.scheme.casefold() in ACTIVE_EXTERNAL_SCHEMES
        or username is not None
        or password is not None
    ):
        raise OoxmlPreflightError(
            "ooxml_external_target_invalid",
            "An external relationship target is not an allowed absolute URI.",
        )


def _validate_workbook_sheets(
    workbook_root: ElementTree.Element,
    relationships: dict[str, OoxmlRelationship],
    package_names: set[str],
) -> int:
    sheets = [
        element
        for element in workbook_root.iter()
        if element.tag.rsplit("}", 1)[-1] == "sheet"
    ]
    for sheet in sheets:
        rel_id = sheet.attrib.get(RELATIONSHIP_ID_ATTRIBUTE)
        relationship = relationships.get(rel_id or "")
        if (
            not rel_id
            or relationship is None
            or relationship.target_mode != "internal"
            or not relationship.relationship_type.endswith("/worksheet")
            or relationship.target not in package_names
        ):
            raise _security("A workbook sheet has no valid relationship.")
    return len(sheets)


@dataclass(frozen=True)
class WorkbookManifestBuild:
    manifest: dict[str, Any]
    fragments: tuple[dict[str, Any], ...]
    manifest_json: str
    manifest_hash: str
    fragments_jsonl: str
    fragments_hash: str
    cell_count: int
    region_count: int


def build_workbook_manifest(
    cursor: io.BytesIO,
    *,
    preflight: OoxmlPreflightResult,
    source_revision_id: str,
    fragment_id_by_sequence: dict[int, str],
    next_fragment_number: int,
) -> WorkbookManifestBuild:
    """Build the Slice 24 structural view from an already validated byte stream."""

    cursor.seek(0)
    try:
        package = zipfile.ZipFile(cursor)
    except (OSError, zipfile.BadZipFile) as exc:  # pragma: no cover - preflight guard.
        raise _security("Validated OOXML bytes no longer form a ZIP package.") from exc

    relationships = list(preflight.relationships_detail)
    relation_by_owner_and_id = {
        (relationship.source_part, relationship.relationship_id): relationship
        for relationship in relationships
    }
    warnings: list[dict[str, str]] = []
    with package:
        workbook_meta = _parse_workbook_metadata(
            package,
            preflight.workbook_part,
            preflight.limits,
        )
        sheets_meta = workbook_meta["sheets"]
        named_ranges = _named_ranges(workbook_meta["defined_names"], sheets_meta)
        shared_strings_part = _related_part(
            relationships,
            preflight.workbook_part,
            "/sharedStrings",
        )
        styles_part = _related_part(
            relationships,
            preflight.workbook_part,
            "/styles",
        )
        shared_strings = (
            _parse_shared_strings(package, shared_strings_part, preflight.limits)
            if shared_strings_part is not None
            else []
        )
        date_styles = (
            _parse_date_styles(package, styles_part, preflight.limits)
            if styles_part is not None
            else {}
        )

        sheets: list[dict[str, Any]] = []
        tables: list[dict[str, Any]] = []
        cell_count = 0
        region_count = 0
        for sheet_meta in sheets_meta:
            relationship = relation_by_owner_and_id.get(
                (preflight.workbook_part, sheet_meta["relationship_id"])
            )
            if (
                relationship is None
                or relationship.target_mode != "internal"
                or not relationship.relationship_type.endswith("/worksheet")
            ):
                raise _security(
                    f"Worksheet relationship is invalid: {sheet_meta['relationship_id']}."
                )
            parsed = _parse_worksheet(
                package,
                relationship.target,
                limits=preflight.limits,
                shared_strings=shared_strings,
                date_styles=date_styles,
                date_system=workbook_meta["date_system"],
            )
            cell_count += len(parsed["cells"])
            if cell_count > preflight.limits.max_cells:
                raise _budget("excel.max_cells", preflight.limits.max_cells)
            named_rectangles = _named_rectangles_for_sheet(
                named_ranges,
                sheet_meta["name"],
            )
            try:
                regions = detect_regions(
                    parsed["cells"],
                    merged_ranges=parsed["merged_ranges"],
                    named_range_rectangles=named_rectangles,
                    max_regions=preflight.limits.max_regions,
                )
            except WorkbookRegionError as exc:
                if "max_regions" in str(exc):
                    raise _budget(
                        "excel.max_regions", preflight.limits.max_regions
                    ) from exc
                raise _security(str(exc)) from exc
            region_count += len(regions)
            if region_count > preflight.limits.max_regions:
                raise _budget("excel.max_regions", preflight.limits.max_regions)
            tables.extend(
                _parse_worksheet_tables(
                    package,
                    relationships,
                    worksheet_part=relationship.target,
                    sheet_index=sheet_meta["index"],
                    sheet_name=sheet_meta["name"],
                    limits=preflight.limits,
                )
            )
            sheets.append(
                {
                    "index": sheet_meta["index"],
                    "name": sheet_meta["name"],
                    "visibility": sheet_meta["visibility"],
                    "part_name": relationship.target,
                    "relationship_id": sheet_meta["relationship_id"],
                    "dimensions": parsed["dimensions"],
                    "cells": parsed["cells"],
                    "merged_ranges": parsed["merged_ranges"],
                    "regions": regions,
                }
            )

        macro_parts = sorted(
            name
            for name, content_type in preflight.part_content_types
            if content_type == VBA_PROJECT_CONTENT_TYPE
        )
        if len(macro_parts) > 1:
            raise _security("More than one VBA project part is not supported.")
        macro_part = macro_parts[0] if macro_parts else None
        macro_hash = (
            _hash_member(package, macro_part, preflight.limits)
            if macro_part is not None
            else None
        )

    fragments = _attach_fragments(
        sheets,
        source_revision_id=source_revision_id,
        fragment_id_by_sequence=fragment_id_by_sequence,
        next_fragment_number=next_fragment_number,
    )
    external_links = [
        {
            "source_part": relationship.source_part or "/",
            "relationship_id": relationship.relationship_id,
            "target": relationship.target,
            "disposition": "not_dereferenced",
        }
        for relationship in relationships
        if relationship.target_mode == "external"
    ]
    external_links.sort(key=lambda item: (item["source_part"], item["relationship_id"]))
    warning_records = sorted(
        warnings,
        key=lambda item: (item["reason"], item["locator"], item["severity"]),
    )
    manifest = {
        "source_revision": {
            "id": source_revision_id,
            "content_hash": preflight.source_hash,
            "extension": preflight.extension,
            "package_content_type": preflight.workbook_content_type,
        },
        "workbook": {
            "part_name": preflight.workbook_part,
            "date_system": workbook_meta["date_system"],
            "calculation_properties": workbook_meta["calculation_properties"],
            "macro_presence": macro_part is not None,
        },
        "sheets": sheets,
        "named_ranges": named_ranges,
        "relationships": [
            relationship.manifest_record() for relationship in relationships
        ],
        "external_links": external_links,
        "macros": {
            "present": macro_part is not None,
            "part_name": macro_part,
            "content_hash": macro_hash,
            "executed": False,
        },
        "warnings": warning_records,
        "schema_version": "1",
    }
    if tables:
        manifest["tables"] = sorted(
            tables,
            key=lambda item: (
                item["sheet_index"],
                _range_sort_key(item["refers_to"]),
                item["display_name"],
                item["part_name"],
            ),
        )
    manifest_json = canonical_json_artifact_v1(manifest)
    fragments_jsonl = "".join(
        canonical_json_v1(fragment) + "\n" for fragment in fragments
    )
    return WorkbookManifestBuild(
        manifest=manifest,
        fragments=tuple(fragments),
        manifest_json=manifest_json,
        manifest_hash=hashlib.sha256(manifest_json.encode("utf-8")).hexdigest(),
        fragments_jsonl=fragments_jsonl,
        fragments_hash=hashlib.sha256(fragments_jsonl.encode("utf-8")).hexdigest(),
        cell_count=cell_count,
        region_count=region_count,
    )


def _parse_workbook_metadata(
    package: zipfile.ZipFile,
    part_name: str,
    limits: ExcelLimits,
) -> dict[str, Any]:
    date_system = "1900"
    calculation_properties: dict[str, str] = {}
    sheets: list[dict[str, Any]] = []
    defined_names: list[dict[str, Any]] = []
    with _open_limited_xml(package, part_name, limits) as stream:
        try:
            for _event, element in ElementTree.iterparse(stream, events=("end",)):
                local_name = _local_name(element.tag)
                if local_name == "workbookPr":
                    if element.attrib.get("date1904", "0").casefold() in {"1", "true"}:
                        date_system = "1904"
                elif local_name == "calcPr":
                    calculation_properties = {
                        _local_name(key): value
                        for key, value in sorted(element.attrib.items())
                    }
                elif local_name == "sheet":
                    relationship_id = element.attrib.get(RELATIONSHIP_ID_ATTRIBUTE)
                    name = element.attrib.get("name")
                    if not relationship_id or name is None:
                        raise _security(
                            "A workbook sheet is missing name or relationship id."
                        )
                    raw_visibility = element.attrib.get("state", "visible")
                    visibility = {
                        "visible": "visible",
                        "hidden": "hidden",
                        "veryHidden": "very_hidden",
                    }.get(raw_visibility)
                    if visibility is None:
                        raise _security(
                            f"Unsupported worksheet visibility: {raw_visibility!r}."
                        )
                    sheets.append(
                        {
                            "index": len(sheets),
                            "name": name,
                            "visibility": visibility,
                            "relationship_id": relationship_id,
                        }
                    )
                elif local_name == "definedName":
                    defined_names.append(
                        {
                            "name": element.attrib.get("name"),
                            "local_sheet_id": element.attrib.get("localSheetId"),
                            "refers_to": element.text or "",
                        }
                    )
                element.clear()
        except ElementTree.ParseError as exc:  # pragma: no cover - preflight parsed it.
            raise _security(f"Malformed XML in OOXML part {part_name!r}.") from exc
    return {
        "date_system": date_system,
        "calculation_properties": calculation_properties,
        "sheets": sheets,
        "defined_names": defined_names,
    }


def _named_ranges(
    raw_names: list[dict[str, Any]],
    sheets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for raw in raw_names:
        name = raw.get("name")
        if not isinstance(name, str) or not name:
            raise _security("A defined name has no name.")
        raw_sheet_id = raw.get("local_sheet_id")
        if raw_sheet_id is None:
            scope = "workbook"
            sheet_name = None
        else:
            try:
                sheet_index = int(raw_sheet_id)
                sheet_name = sheets[sheet_index]["name"]
            except (TypeError, ValueError, IndexError) as exc:
                raise _security("A defined name has an invalid localSheetId.") from exc
            scope = "sheet"
        result.append(
            {
                "scope": scope,
                "sheet_name": sheet_name,
                "name": name,
                "refers_to": str(raw.get("refers_to", "")),
            }
        )
    return sorted(
        result,
        key=lambda item: (
            0 if item["scope"] == "workbook" else 1,
            item["sheet_name"] or "",
            item["name"],
            item["refers_to"],
        ),
    )


def _parse_worksheet_tables(
    package: zipfile.ZipFile,
    relationships: list[OoxmlRelationship],
    *,
    worksheet_part: str,
    sheet_index: int,
    sheet_name: str,
    limits: ExcelLimits,
) -> list[dict[str, Any]]:
    """Inventory declared OOXML tables without interpreting their cell values."""

    table_relationships = sorted(
        (
            relationship
            for relationship in relationships
            if relationship.source_part == worksheet_part
            and relationship.target_mode == "internal"
            and relationship.relationship_type.endswith("/table")
        ),
        key=lambda item: (item.relationship_id, item.target),
    )
    result: list[dict[str, Any]] = []
    for relationship in table_relationships:
        table_attributes: dict[str, str] | None = None
        columns: list[dict[str, str]] = []
        with _open_limited_xml(package, relationship.target, limits) as stream:
            try:
                for event, element in ElementTree.iterparse(
                    stream, events=("start", "end")
                ):
                    local_name = _local_name(element.tag)
                    if event == "start" and local_name == "table":
                        if table_attributes is not None:
                            raise _security(
                                "An OOXML table part contains multiple tables."
                            )
                        table_attributes = {
                            _local_name(key): value
                            for key, value in element.attrib.items()
                        }
                    elif event == "end" and local_name == "tableColumn":
                        column_id = element.attrib.get("id")
                        name = element.attrib.get("name")
                        if not column_id or name is None:
                            raise _security("An OOXML table column is incomplete.")
                        columns.append({"id": column_id, "name": name})
                    if event == "end":
                        element.clear()
            except (
                ElementTree.ParseError
            ) as exc:  # pragma: no cover - preflight parsed it.
                raise _security(
                    f"Malformed XML in OOXML table part {relationship.target!r}."
                ) from exc
        if table_attributes is None:
            raise _security("An OOXML table part has no table root.")
        name = table_attributes.get("name")
        display_name = table_attributes.get("displayName")
        raw_reference = table_attributes.get("ref")
        if not name or not display_name or not raw_reference:
            raise _security("An OOXML table is missing name, displayName, or ref.")
        try:
            reference = parse_cell_range(raw_reference).reference
        except WorkbookRegionError as exc:
            raise _security("An OOXML table has an invalid ref.") from exc
        result.append(
            {
                "columns": columns,
                "display_name": display_name,
                "name": name,
                "part_name": relationship.target,
                "refers_to": reference,
                "relationship_id": relationship.relationship_id,
                "sheet_index": sheet_index,
                "sheet_name": sheet_name,
            }
        )
    return result


def _parse_shared_strings(
    package: zipfile.ZipFile,
    part_name: str,
    limits: ExcelLimits,
) -> list[str]:
    strings: list[str] = []
    with _open_limited_xml(package, part_name, limits) as stream:
        try:
            for _event, element in ElementTree.iterparse(stream, events=("end",)):
                if _local_name(element.tag) == "si":
                    strings.append(
                        "".join(
                            child.text or ""
                            for child in element.iter()
                            if _local_name(child.tag) == "t"
                        )
                    )
                    element.clear()
        except ElementTree.ParseError as exc:  # pragma: no cover - preflight parsed it.
            raise _security(f"Malformed XML in OOXML part {part_name!r}.") from exc
    return strings


def _parse_date_styles(
    package: zipfile.ZipFile,
    part_name: str,
    limits: ExcelLimits,
) -> dict[int, bool]:
    custom_formats: dict[int, str] = {}
    cell_formats: list[int] = []
    in_cell_xfs = False
    with _open_limited_xml(package, part_name, limits) as stream:
        try:
            for event, element in ElementTree.iterparse(
                stream, events=("start", "end")
            ):
                local_name = _local_name(element.tag)
                if event == "start" and local_name == "cellXfs":
                    in_cell_xfs = True
                elif event == "end" and local_name == "numFmt":
                    try:
                        custom_formats[int(element.attrib["numFmtId"])] = (
                            element.attrib["formatCode"]
                        )
                    except (KeyError, ValueError) as exc:
                        raise _security(
                            "A number format declaration is invalid."
                        ) from exc
                    element.clear()
                elif event == "end" and local_name == "xf" and in_cell_xfs:
                    try:
                        cell_formats.append(int(element.attrib.get("numFmtId", "0")))
                    except ValueError as exc:
                        raise _security("A cell style numFmtId is invalid.") from exc
                    element.clear()
                elif event == "end" and local_name == "cellXfs":
                    in_cell_xfs = False
                    element.clear()
        except ElementTree.ParseError as exc:  # pragma: no cover - preflight parsed it.
            raise _security(f"Malformed XML in OOXML part {part_name!r}.") from exc
    result: dict[int, bool] = {}
    for style_id, number_format_id in enumerate(cell_formats):
        code = custom_formats.get(number_format_id)
        if code is None:
            code = _BUILTIN_DATE_FORMATS.get(number_format_id)
        if code is not None and _looks_like_date_format(code):
            result[style_id] = _format_contains_time(code)
    return result


def _parse_worksheet(
    package: zipfile.ZipFile,
    part_name: str,
    *,
    limits: ExcelLimits,
    shared_strings: list[str],
    date_styles: dict[int, bool],
    date_system: str,
) -> dict[str, Any]:
    cells: list[dict[str, Any]] = []
    merged_ranges: list[str] = []
    declared_dimension: str | None = None
    with _open_limited_xml(package, part_name, limits) as stream:
        try:
            for _event, element in ElementTree.iterparse(stream, events=("end",)):
                local_name = _local_name(element.tag)
                if local_name == "dimension":
                    declared_dimension = element.attrib.get("ref")
                    element.clear()
                elif local_name == "c":
                    cells.append(
                        _parse_cell(
                            element,
                            shared_strings=shared_strings,
                            date_styles=date_styles,
                            date_system=date_system,
                        )
                    )
                    if len(cells) > limits.max_cells:
                        raise _budget("excel.max_cells", limits.max_cells)
                    element.clear()
                elif local_name == "mergeCell":
                    reference = element.attrib.get("ref")
                    if not reference:
                        raise _security("A merged range has no reference.")
                    merged_ranges.append(parse_cell_range(reference).reference)
                    element.clear()
        except ElementTree.ParseError as exc:  # pragma: no cover - preflight parsed it.
            raise _security(f"Malformed XML in OOXML part {part_name!r}.") from exc
        except WorkbookRegionError as exc:
            raise _security(str(exc)) from exc
    cells.sort(key=lambda item: (item["row"], item["column"]))
    merged_ranges.sort(key=_range_sort_key)
    addressed_positions = [
        CellPosition(row=cell["row"], column=cell["column"]) for cell in cells
    ]
    merge_bounds = [parse_cell_range(reference) for reference in merged_ranges]
    rows = [position.row for position in addressed_positions]
    columns = [position.column for position in addressed_positions]
    for bounds in merge_bounds:
        rows.extend((bounds.start.row, bounds.end.row))
        columns.extend((bounds.start.column, bounds.end.column))
    dimensions = {
        "declared": declared_dimension,
        "min_row": min(rows) if rows else 0,
        "max_row": max(rows) if rows else 0,
        "min_column": min(columns) if columns else 0,
        "max_column": max(columns) if columns else 0,
    }
    return {
        "cells": cells,
        "merged_ranges": merged_ranges,
        "dimensions": dimensions,
    }


def _parse_cell(
    element: ElementTree.Element,
    *,
    shared_strings: list[str],
    date_styles: dict[int, bool],
    date_system: str,
) -> dict[str, Any]:
    coordinate = element.attrib.get("r")
    if not coordinate:
        raise _security("An addressed worksheet cell has no coordinate.")
    try:
        position = parse_cell_reference(coordinate)
        style_id = int(element.attrib.get("s", "0"))
    except (ValueError, WorkbookRegionError) as exc:
        raise _security(f"A worksheet cell is invalid: {coordinate!r}.") from exc
    raw_type = element.attrib.get("t", "n")
    formula_element = next(
        (child for child in element if _local_name(child.tag) == "f"),
        None,
    )
    value_element = next(
        (child for child in element if _local_name(child.tag) == "v"),
        None,
    )
    inline_element = next(
        (child for child in element if _local_name(child.tag) == "is"),
        None,
    )
    formula = formula_element.text if formula_element is not None else None
    raw_value = value_element.text if value_element is not None else None
    inline_value = None
    if inline_element is not None:
        inline_value = "".join(
            child.text or ""
            for child in inline_element.iter()
            if _local_name(child.tag) == "t"
        )
    value_type, parsed_value = _typed_cell_value(
        raw_value,
        inline_value=inline_value,
        raw_type=raw_type,
        style_id=style_id,
        shared_strings=shared_strings,
        date_styles=date_styles,
        date_system=date_system,
    )
    if formula is not None and raw_value is None:
        value_type = _formula_result_type(
            raw_type,
            style_id=style_id,
            date_styles=date_styles,
        )
    return {
        "coordinate": position.coordinate,
        "row": position.row,
        "column": position.column,
        "type": value_type,
        "value": None if formula is not None else parsed_value,
        "formula": formula,
        "cached_value": parsed_value if formula is not None else None,
        "style_id": style_id,
    }


def _typed_cell_value(
    raw_value: str | None,
    *,
    inline_value: str | None,
    raw_type: str,
    style_id: int,
    shared_strings: list[str],
    date_styles: dict[int, bool],
    date_system: str,
) -> tuple[str, Any]:
    if raw_type == "inlineStr":
        return "string", inline_value if inline_value is not None else ""
    if raw_value is None:
        return "blank", None
    if raw_type == "s":
        try:
            return "string", shared_strings[int(raw_value)]
        except (ValueError, IndexError) as exc:
            raise _security(
                "A shared-string cell references an invalid index."
            ) from exc
    if raw_type == "b":
        if raw_value not in {"0", "1", "false", "true"}:
            raise _security("A boolean cell has an invalid value.")
        return "bool", raw_value in {"1", "true"}
    if raw_type == "e":
        return "error", raw_value
    if raw_type in {"str", "inlineStr"}:
        return "string", raw_value
    if raw_type == "d":
        return "date", raw_value
    if raw_type not in {"n", ""}:
        raise _security(f"Unsupported worksheet cell type: {raw_type!r}.")
    try:
        number = Decimal(raw_value)
    except InvalidOperation as exc:
        raise _security(f"A numeric cell has an invalid value: {raw_value!r}.") from exc
    if style_id in date_styles:
        return "date", _excel_date_value(
            number,
            date_system=date_system,
            include_time=date_styles[style_id],
        )
    return "number", _decimal_text(number)


def _formula_result_type(
    raw_type: str,
    *,
    style_id: int,
    date_styles: dict[int, bool],
) -> str:
    if raw_type in {"str", "inlineStr", "s"}:
        return "string"
    if raw_type == "b":
        return "bool"
    if raw_type == "e":
        return "error"
    if raw_type == "d" or style_id in date_styles:
        return "date"
    if raw_type in {"n", ""}:
        return "number"
    raise _security(f"Unsupported formula result type: {raw_type!r}.")


def _excel_date_value(
    serial: Decimal,
    *,
    date_system: str,
    include_time: bool,
) -> str:
    day = int(serial // 1)
    fraction = serial - Decimal(day)
    if fraction < 0:
        day -= 1
        fraction += 1
    if date_system == "1904":
        epoch = datetime.combine(date(1904, 1, 1), time())
    else:
        epoch = datetime.combine(date(1899, 12, 31), time())
        if day >= 60:
            day -= 1
    microseconds = int((fraction * Decimal(86_400_000_000)).to_integral_value())
    result = epoch + timedelta(days=day, microseconds=microseconds)
    if not include_time and result.time() == time():
        return result.date().isoformat()
    return result.isoformat(timespec="microseconds").rstrip("0").rstrip(".")


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise _security("A numeric cell contains NaN or infinity.")
    if value.is_zero():
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _named_rectangles_for_sheet(
    named_ranges: list[dict[str, Any]],
    sheet_name: str,
) -> list[str]:
    rectangles: set[str] = set()
    sheet_pattern = re.compile(
        r"(?:'((?:[^']|'')+)'|([^'!,]+))!"
        r"(\$?[A-Za-z]{1,3}\$?[1-9][0-9]*(?::\$?[A-Za-z]{1,3}\$?[1-9][0-9]*)?)"
    )
    local_pattern = re.compile(
        r"^=?\s*(\$?[A-Za-z]{1,3}\$?[1-9][0-9]*(?::\$?[A-Za-z]{1,3}\$?[1-9][0-9]*)?)\s*$"
    )
    for item in named_ranges:
        refers_to = item["refers_to"].lstrip("=")
        for match in sheet_pattern.finditer(refers_to):
            referenced_sheet = (match.group(1) or match.group(2) or "").replace(
                "''", "'"
            )
            if referenced_sheet == sheet_name:
                rectangles.add(parse_cell_range(match.group(3)).reference)
        if item["scope"] == "sheet" and item["sheet_name"] == sheet_name:
            local = local_pattern.fullmatch(item["refers_to"])
            if local is not None:
                rectangles.add(parse_cell_range(local.group(1)).reference)
    return sorted(rectangles, key=_range_sort_key)


def _attach_fragments(
    sheets: list[dict[str, Any]],
    *,
    source_revision_id: str,
    fragment_id_by_sequence: dict[int, str],
    next_fragment_number: int,
) -> list[dict[str, Any]]:
    used_ids = set(fragment_id_by_sequence.values())
    fragments: list[dict[str, Any]] = []
    sequence = 0
    for sheet in sheets:
        for region in sheet["regions"]:
            sequence += 1
            fragment_id = fragment_id_by_sequence.get(sequence)
            if fragment_id is None:
                while f"FRAG_{next_fragment_number:06d}" in used_ids:
                    next_fragment_number += 1
                fragment_id = f"FRAG_{next_fragment_number:06d}"
                next_fragment_number += 1
            if not re.fullmatch(r"FRAG_[0-9]{6}", fragment_id):
                raise _security("Workbook fragment id seed is invalid.")
            used_ids.add(fragment_id)
            region["fragment_id"] = fragment_id
            semantic = {
                "sheet": {"index": sheet["index"], "name": sheet["name"]},
                "start_cell": region["start_cell"],
                "end_cell": region["end_cell"],
                "region_kind": region["region_kind"],
                "region_hash": region["region_hash"],
                "detector": region["detector"],
                "cells": region["cells"],
                "locator": {
                    "part_name": sheet["part_name"],
                    "range": (
                        region["start_cell"]
                        if region["start_cell"] == region["end_cell"]
                        else f"{region['start_cell']}:{region['end_cell']}"
                    ),
                },
            }
            fragments.append(
                {
                    "fragment_id": fragment_id,
                    "fragment_type": "excel_region",
                    "sequence": sequence,
                    "source_revision_id": source_revision_id,
                    "fragment_hash": canonical_sha256_v1(semantic),
                    **semantic,
                }
            )
    return fragments


def _related_part(
    relationships: list[OoxmlRelationship],
    owner: str,
    relationship_suffix: str,
) -> str | None:
    matches = [
        relationship.target
        for relationship in relationships
        if relationship.source_part == owner
        and relationship.target_mode == "internal"
        and relationship.relationship_type.endswith(relationship_suffix)
    ]
    if len(matches) > 1:
        raise _security(f"Ambiguous workbook relationship: {relationship_suffix}.")
    return matches[0] if matches else None


class _LimitedXmlReader:
    def __init__(self, stream: Any, maximum: int, part_name: str) -> None:
        self._stream = stream
        self._maximum = maximum
        self._part_name = part_name
        self._read = 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = min(64 * 1024, self._maximum - self._read + 1)
        data = self._stream.read(size)
        self._read += len(data)
        if self._read > self._maximum:
            raise _budget("excel.max_xml_part_bytes", self._maximum)
        return data

    def __enter__(self) -> _LimitedXmlReader:
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self._stream.close()


def _open_limited_xml(
    package: zipfile.ZipFile,
    part_name: str,
    limits: ExcelLimits,
) -> _LimitedXmlReader:
    try:
        return _LimitedXmlReader(
            package.open(part_name, "r"),
            limits.max_xml_part_bytes,
            part_name,
        )
    except (KeyError, OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise _security(f"OOXML part could not be read safely: {part_name!r}.") from exc


def _hash_member(
    package: zipfile.ZipFile,
    part_name: str,
    limits: ExcelLimits,
) -> str:
    digest = hashlib.sha256()
    total = 0
    try:
        with package.open(part_name, "r") as stream:
            while True:
                chunk = stream.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > limits.max_uncompressed_bytes:
                    raise _budget(
                        "excel.max_uncompressed_bytes",
                        limits.max_uncompressed_bytes,
                    )
                digest.update(chunk)
    except OoxmlPreflightError:
        raise
    except (KeyError, OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise _security(
            f"OOXML part could not be hashed safely: {part_name!r}."
        ) from exc
    return digest.hexdigest()


def _range_sort_key(reference: str) -> tuple[int, int, int, int]:
    bounds = parse_cell_range(reference)
    return (
        bounds.start.row,
        bounds.start.column,
        bounds.end.row,
        bounds.end.column,
    )


def _local_name(value: str) -> str:
    return value.rsplit("}", 1)[-1]


_BUILTIN_DATE_FORMATS = {
    14: "mm-dd-yy",
    15: "d-mmm-yy",
    16: "d-mmm",
    17: "mmm-yy",
    18: "h:mm AM/PM",
    19: "h:mm:ss AM/PM",
    20: "h:mm",
    21: "h:mm:ss",
    22: "m/d/yy h:mm",
    27: "yyyy-mm-dd",
    30: "m/d/yy",
    36: "yyyy-mm-dd",
    45: "mm:ss",
    46: "[h]:mm:ss",
    47: "mmss.0",
    50: "yyyy-mm-dd",
    57: "yyyy-mm-dd",
}


def _clean_number_format(code: str) -> str:
    without_literals = re.sub(r'"(?:[^"]|"")*"', "", code)
    without_escapes = re.sub(r"\\.", "", without_literals)
    without_conditions = re.sub(r"\[(?!h+\]|m+\]|s+\])[^\]]*\]", "", without_escapes)
    return without_conditions.casefold()


def _looks_like_date_format(code: str) -> bool:
    cleaned = _clean_number_format(code)
    return bool(re.search(r"(?:^|[^a-z])[ymdhis]+", cleaned))


def _format_contains_time(code: str) -> bool:
    cleaned = _clean_number_format(code)
    return bool(re.search(r"[hs]|am/pm|\[[hms]+\]", cleaned))


def _budget(name: str, maximum: int) -> OoxmlPreflightError:
    return OoxmlPreflightError(
        "ooxml_budget_exceeded",
        f"OOXML package exceeds {name} ({maximum}).",
    )


def _security(message: str) -> OoxmlPreflightError:
    return OoxmlPreflightError("ooxml_security_violation", message)


def catalog_result(status: str, reason: str | None) -> dict[str, Any]:
    resolved_reason = reason or "success"
    condition = "operation_completed"
    exit_code = 0
    mutations = "artifacts_published"
    retryable = False
    severity = "info"
    if reason == "source_revision_changed":
        condition = "source_revision_bytes_changed"
        exit_code, mutations, retryable, severity = 4, "none", True, "error"
    elif reason in {
        "ooxml_security_violation",
        "ooxml_budget_exceeded",
        "ooxml_external_target_invalid",
    }:
        condition = {
            "ooxml_security_violation": "unsafe_ooxml_package",
            "ooxml_budget_exceeded": "ooxml_limit_exceeded",
            "ooxml_external_target_invalid": "invalid_external_relationship",
        }[reason]
        exit_code, mutations, severity = 3, "report_only", "warning"
        retryable = reason == "ooxml_budget_exceeded"
    elif reason == "normalization_operational_failure":
        condition = "docling_timeout_or_error"
        exit_code, mutations, retryable, severity = (
            5,
            "partial_artifacts_discarded",
            True,
            "error",
        )
    elif reason == "normalization_partial":
        condition = "acceptable_partial_conversion"
        exit_code, mutations, retryable, severity = (
            6,
            "artifacts_marked_partial",
            True,
            "warning",
        )
    return {
        "artifact_paths": [],
        "catalog_version": 1,
        "condition": condition,
        "counters": {},
        "exit_code": exit_code,
        "mutations": mutations,
        "outcome": None,
        "reason": resolved_reason,
        "retryable": retryable,
        "run_id": None,
        "severity": severity,
        "status": status,
        "subject_ids": {},
    }
