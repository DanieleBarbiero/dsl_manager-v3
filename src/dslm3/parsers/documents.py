from __future__ import annotations
import csv
import io
import json
import re
from email import policy
from email.parser import BytesParser
from pathlib import Path

import yaml
from charset_normalizer import from_bytes
from lxml import etree

from dslm3.common import DomainError, digest
from dslm3.parsers.base import ParseResult, chunks, location
from dslm3.vendor.ooxml_preflight import (
    ExcelLimits,
    preflight_ooxml,
    preflight_ooxml_metadata,
    build_workbook_manifest,
)

EXCEL_DEFAULTS = dict(
    max_file_bytes=67108864,
    max_zip_entries=20000,
    max_uncompressed_bytes=536870912,
    max_compression_ratio=100,
    max_xml_part_bytes=33554432,
    max_sheets=256,
    max_cells=2000000,
    max_regions=10000,
    max_relationships=50000,
    max_output_bytes=268435456,
    worker_timeout_seconds=300,
    worker_memory_bytes=1073741824,
)
DOCLING_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".xlsm",
    ".html",
    ".htm",
    ".md",
    ".markdown",
    ".csv",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".bmp",
    ".webp",
    ".asciidoc",
    ".adoc",
    ".vtt",
    ".tex",
    ".epub",
    ".eml",
    ".msg",
}


def decode(data: bytes) -> tuple[str, str]:
    for encoding in (
        ("utf-8-sig", "utf-16")
        if data.startswith((b"\xff\xfe", b"\xfe\xff"))
        else ("utf-8-sig",)
    ):
        try:
            return data.decode(encoding), encoding
        except UnicodeError:
            pass
    best = from_bytes(data).best()
    if best is None:
        raise DomainError(
            "unknown_encoding", "Impossibile decodificare il documento senza perdita."
        )
    return str(best), best.encoding


def docling_convert(path: Path) -> dict:
    from docling.document_converter import DocumentConverter

    result = DocumentConverter().convert(path, raises_on_error=True)
    status = result.status.value
    if status not in {"success", "partial_success"}:
        raise DomainError("docling_failed", f"Docling: {status}")
    return {
        "normalized.md": result.document.export_to_markdown(),
        "normalized.json": result.document.export_to_dict(),
        "conversion_status": status,
        "errors": [str(x) for x in result.errors],
    }


def parse_workbook(path: Path, data: bytes, revision: str, config: dict) -> ParseResult:
    limits = ExcelLimits.from_config(
        {**EXCEL_DEFAULTS, "max_file_bytes": config.get("max_file_bytes", 67108864)}
    )
    preflight = preflight_ooxml(
        io.BytesIO(data),
        original_name=path.name,
        source_hash=digest(data),
        limits=limits,
    )
    built = build_workbook_manifest(
        io.BytesIO(data),
        preflight=preflight,
        source_revision_id=revision,
        fragment_id_by_sequence={},
        next_fragment_number=1,
    )
    result = ParseResult("ooxml/1")
    manifest = built.manifest
    result.artifacts["workbook_manifest.json"] = manifest
    result.add(
        "excel_workbook",
        json.dumps(manifest["workbook"], ensure_ascii=False),
        {
            "name": path.name,
            "manifest": {k: v for k, v in manifest.items() if k != "sheets"},
        },
        {"part_name": manifest["workbook"]["part_name"]},
    )
    for sheet in manifest["sheets"]:
        name = path.name + "::" + sheet["name"]
        result.add(
            "excel_sheet",
            sheet["name"],
            {
                "name": name,
                "sheet_name": sheet["name"],
                "visibility": sheet["visibility"],
                "dimensions": sheet["dimensions"],
            },
            {"part_name": sheet["part_name"], "sheet_name": sheet["name"]},
        )
    for item in built.fragments:
        text = (
            item.get("text")
            or item.get("fragment_text")
            or json.dumps(item, ensure_ascii=False)
        )
        result.add(
            "excel_region",
            text,
            {
                "name": path.name
                + "::"
                + item["sheet"]["name"]
                + "::"
                + item["locator"]["range"],
                **{k: v for k, v in item.items() if k not in {"text", "locator"}},
            },
            {**item["locator"], "sheet_name": item["sheet"]["name"]},
        )
    for key, type_ in [
        ("named_ranges", "excel_named_range"),
        ("tables", "excel_table"),
        ("external_links", "excel_explicit_reference"),
    ]:
        for item in manifest.get(key, []):
            result.add(
                type_,
                json.dumps(item, ensure_ascii=False),
                {
                    "name": path.name
                    + "::"
                    + str(
                        item.get("name")
                        or item.get("display_name")
                        or item.get("relationship_id")
                    ),
                    **item,
                },
                {
                    "part_name": item.get(
                        "part_name", manifest["workbook"]["part_name"]
                    ),
                    "sheet_name": item.get("sheet_name"),
                    "range": item.get("refers_to"),
                },
            )
    # Both views consume the same immutable object. Formula/cache/VBA authority
    # always belongs to the manifest, never the rendering.
    normalized = docling_convert(path)
    result.artifacts.update(normalized)
    chunks(
        result,
        normalized["normalized.md"],
        config.get("chunk_chars", 5000),
        representation="docling_markdown",
    )
    if normalized["conversion_status"] == "partial_success":
        result.status = "partial"
    return result


def parse_xml(text: str) -> ParseResult:
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.I):
        raise DomainError("unsafe_xml", "DTD ed entity non sono ammessi.")
    root = etree.fromstring(
        text.encode(),
        parser=etree.XMLParser(
            resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False
        ),
    )
    result = ParseResult("xml_forms/3")
    lines = text.splitlines(keepends=True)
    tree = root.getroottree()

    def tag(e):
        return etree.QName(e).localname.casefold()

    def attrs(e):
        return {etree.QName(k).localname.casefold(): v for k, v in e.attrib.items()}

    def record(e, type_, data):
        line = max(1, e.sourceline or 1)
        start = sum(len(x) for x in lines[: line - 1])
        end = start + len(lines[line - 1])
        # Preserve literal source; XPath differentiates nodes sharing a line.
        return result.add(
            type_,
            text[start:end],
            data,
            {**location(text, start, end), "xpath": tree.getpath(e)},
        )

    forms = [
        e
        for e in root.iter()
        if isinstance(e.tag, str) and tag(e) in {"form", "formmodule", "forms-module"}
    ]
    if not forms:
        result.add(
            "xml_document", text, {"root": tag(root)}, {"xpath": "/" + tag(root)}
        )
        chunks(result, text)
        return result
    for form in forms:
        fa = attrs(form)
        fname = fa.get("name") or fa.get("modulename") or "FORM"
        record(form, "xml_form", {"name": fname, "title": fa.get("title")})
        for e in form.iterdescendants():
            if not isinstance(e.tag, str):
                continue
            a = attrs(e)
            kind = tag(e)
            name = a.get("name") or a.get("itemname") or a.get("triggername")
            parents = [
                x
                for x in e.iterancestors()
                if isinstance(x.tag, str) and tag(x) == "block"
            ]
            block = attrs(parents[0]) if parents else {}
            table = (
                block.get("table")
                or block.get("querydatasourcename")
                or block.get("basetable")
            )
            if kind == "block":
                table = (
                    a.get("table") or a.get("querydatasourcename") or a.get("basetable")
                )
                record(
                    e,
                    "xml_block",
                    {
                        "name": fname + "." + str(name or table or "block"),
                        "table": table,
                    },
                )
                if table:
                    record(
                        e,
                        "xml_dependency",
                        {
                            "source": fname,
                            "relation_type": "uses_table",
                            "target": table,
                        },
                    )
            button = kind == "button" or (
                kind == "item"
                and a.get("itemtype", "").replace(" ", "").lower()
                in {"pushbutton", "button"}
            )
            if kind in {"field", "item", "button"} and name:
                full = fname + "." + name
                data = {
                    "name": full,
                    "form": fname,
                    "table": table,
                    "column": a.get("column") or a.get("columnname") or name,
                    "datatype": a.get("datatype"),
                    "required": a.get("required", "false").lower()
                    in {"true", "yes", "1"},
                    "label": a.get("label"),
                }
                record(e, "xml_button" if button else "xml_field", data)
                if table and not button:
                    record(
                        e,
                        "xml_dependency",
                        {
                            "source": full,
                            "relation_type": "maps_to",
                            "target": table + "." + data["column"],
                        },
                    )
                operation = a.get("operation") or a.get("procedure") or a.get("call")
                if operation:
                    record(
                        e,
                        "xml_dependency",
                        {"source": full, "relation_type": "calls", "target": operation},
                    )
            if kind in {"trigger", "programunit"}:
                code = (
                    a.get("triggertext")
                    or a.get("programunittext")
                    or "".join(e.itertext())
                )
                record(
                    e,
                    "xml_code",
                    {"name": fname + "." + str(name or kind), "code": code},
                )
    return result


def parse_log(text: str) -> ParseResult:
    result = ParseResult("log/3")
    offset = 0
    pattern = re.compile(
        r"^(?P<timestamp>\d{4}-\d\d-\d\d[ T]\d\d:\d\d:\d\d(?:[.,]\d+)?(?:Z|[+-]\d\d:?\d\d)?)\s+(?P<level>\w+)\s+(?P<component>\S+)\s+(?P<message>.*)$"
    )
    for n, line in enumerate(text.splitlines(keepends=True), 1):
        raw = line.rstrip("\r\n")
        if not raw:
            offset += len(line)
            continue
        match = pattern.match(raw)
        data = None
        if raw.lstrip().startswith("{"):
            try:
                obj = json.loads(raw)
                if isinstance(obj, dict):
                    data = {
                        "timestamp": obj.get("timestamp") or obj.get("time"),
                        "level": obj.get("level"),
                        "component": obj.get("component") or obj.get("logger") or "log",
                        "message": obj.get("message") or obj.get("msg") or "",
                        "attributes": obj,
                    }
            except json.JSONDecodeError:
                pass
        if match:
            data = match.groupdict()
        if data is None:
            result.add(
                "log_unparsed",
                raw,
                {"line": n},
                location(text, offset, offset + len(raw)),
            )
            result.warn(
                "log_unparsed",
                "Riga conservata, formato evento non riconosciuto.",
                line=n,
            )
        else:
            data["event_kind"] = str(data["message"]).split(" ", 1)[0].lower()
            data["attributes"] = data.get("attributes") or dict(
                re.findall(r"([\w.-]+)=([^\s]+)", raw)
            )
            data["occurrence_line"] = n
            result.add(
                "log_event", raw, data, location(text, offset, offset + len(raw))
            )
        offset += len(line)
    return result


def parse_structured(text: str, suffix: str) -> ParseResult:
    result = ParseResult("structured/3")
    if suffix in {".csv", ".tsv"}:
        try:
            dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel_tab if suffix == ".tsv" else csv.excel
        reader = csv.reader(io.StringIO(text), dialect)
        header = next(reader, [])
        result.add(
            "dataset_schema",
            text.splitlines()[0] if text.splitlines() else "",
            {"columns": header},
            {"row": 1},
        )
        lines = text.splitlines(keepends=True)
        previous = 1
        for n, row in enumerate(reader, 2):
            end = reader.line_num
            raw = "".join(lines[previous:end])
            previous = end
            result.add(
                "dataset_row",
                raw,
                {"columns": header, "values": row},
                {"row": n, "line_end": end},
            )
    elif suffix in {".jsonl", ".ndjson"}:
        for n, line in enumerate(text.splitlines(), 1):
            if line.strip():
                result.add(
                    "dataset_record",
                    line,
                    {"value": json.loads(line)},
                    {"line_start": n, "line_end": n},
                )
    else:

        class TextDateLoader(yaml.SafeLoader):
            pass

        TextDateLoader.yaml_implicit_resolvers = {
            k: [
                (tag, pattern)
                for tag, pattern in v
                if tag != "tag:yaml.org,2002:timestamp"
            ]
            for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()
        }
        obj = (
            yaml.load(text, Loader=TextDateLoader)
            if suffix in {".yaml", ".yml"}
            else json.loads(text)
        )
        result.add("structured_document", text, {"value": obj}, {"pointer": ""})
    chunks(result, text)
    return result


def parse_legacy_sheet(path: Path, data: bytes) -> ParseResult:
    result = ParseResult("legacy_spreadsheet/3")
    sheets = []
    if path.suffix.lower() == ".xls":
        import xlrd

        book = xlrd.open_workbook(file_contents=data, on_demand=True)
        for s in book.sheets():
            sheets.append(
                (
                    s.name,
                    [
                        [s.cell_value(r, c) for c in range(s.ncols)]
                        for r in range(s.nrows)
                    ],
                )
            )
        book.release_resources()
    elif path.suffix.lower() == ".xlsb":
        from pyxlsb import open_workbook

        with open_workbook(str(path)) as book:
            for name in book.sheets:
                with book.get_sheet(name) as sheet:
                    sheets.append((name, [[c.v for c in row] for row in sheet.rows()]))
    else:
        from odf.opendocument import load
        from odf.table import Table, TableRow, TableCell
        from odf.teletype import extractText

        book = load(io.BytesIO(data))
        for table in book.spreadsheet.getElementsByType(Table):
            rows = []
            for row in table.getElementsByType(TableRow):
                values = []
                for cell in row.getElementsByType(TableCell):
                    repeated = int(cell.getAttribute("numbercolumnsrepeated") or 1)
                    if repeated < 1 or len(values) + repeated > 10000:
                        raise DomainError(
                            "spreadsheet_budget",
                            "Troppe colonne ODS; nessun troncamento.",
                        )
                    values.extend(
                        [
                            {
                                "value": cell.getAttribute("value")
                                or extractText(cell),
                                "formula": cell.getAttribute("formula"),
                            }
                        ]
                        * repeated
                    )
                repeat = int(row.getAttribute("numberrowsrepeated") or 1)
                if (
                    repeat < 1
                    or len(rows) + repeat > 100000
                    or (len(rows) + repeat) * max(len(values), 1) > 2000000
                ):
                    raise DomainError(
                        "spreadsheet_budget", "Troppe celle ODS; nessun troncamento."
                    )
                if values:
                    rows.extend([values] * repeat)
                if len(rows) > 100000:
                    raise DomainError("spreadsheet_budget", "Troppe righe ODS.")
            sheets.append((table.getAttribute("name"), rows))
    for name, rows in sheets:
        result.add(
            "excel_sheet",
            name,
            {"name": path.name + "::" + name, "sheet_name": name},
            {"sheet_name": name},
        )
        for i, row in enumerate(rows, 1):
            result.add(
                "dataset_row",
                json.dumps(row, ensure_ascii=False, default=str),
                {"values": row},
                {"sheet_name": name, "row": i},
            )
    result.warn(
        "legacy_spreadsheet_limits",
        "XLS/XLSB: valori letti; formule e cache complete richiedono OOXML. ODS conserva le formule disponibili. Macro e link non eseguiti.",
    )
    result.artifacts["legacy_workbook.json"] = {
        "format": path.suffix,
        "sheets": [{"name": n, "rows": r} for n, r in sheets],
    }
    return result


def parse_email(data: bytes, suffix: str) -> ParseResult:
    message = BytesParser(policy=policy.default).parsebytes(data)
    result = ParseResult("email/3")
    headers = {
        k: str(message.get(k, ""))
        for k in ["Subject", "From", "To", "Date", "Message-ID"]
    }
    result.add(
        "email_headers",
        "\n".join(k + ": " + v for k, v in headers.items()),
        headers,
        {"part": "headers"},
    )
    for i, part in enumerate(message.walk()):
        if part.get_content_type() not in {"text/plain", "text/html"}:
            continue
        payload = part.get_payload(decode=True) or b""
        text = payload.decode(part.get_content_charset() or "utf-8", errors="strict")
        if part.get_content_type() == "text/html":
            from bs4 import BeautifulSoup

            text = BeautifulSoup(text, "html.parser").get_text("\n")
        chunks(result, text, part=i, content_type=part.get_content_type())
    return result


def parse_document(
    path: Path, revision: str, config: dict, schema: dict | None = None
) -> ParseResult:
    data = path.read_bytes()
    suffix = path.suffix.lower()
    if len(data) > config.get("max_file_bytes", 67108864):
        raise DomainError("file_budget", "File oltre il limite configurato.")
    if suffix in {".xlsx", ".xlsm"}:
        return parse_workbook(path, data, revision, config)
    if suffix in {".xls", ".xlsb", ".ods"}:
        return parse_legacy_sheet(path, data)
    if suffix in {".eml", ".mhtml", ".mht"}:
        return parse_email(data, suffix)
    if suffix in {
        ".sql",
        ".pls",
        ".plsql",
        ".pks",
        ".pkb",
        ".prc",
        ".fnc",
        ".trg",
        ".ddl",
        ".dml",
        ".pck",
        ".tpb",
        ".tps",
    }:
        from dslm3.parsers.sql import parse_sql

        text, encoding = decode(data)
        result = parse_sql(text, config.get("sql_dialect", "auto"), schema)
        result.metadata["encoding"] = encoding
        return result
    if suffix in {".xml", ".fmb.xml"}:
        text, _ = decode(data)
        return parse_xml(text)
    if suffix in {".log"}:
        text, _ = decode(data)
        return parse_log(text)
    if suffix in {".json", ".jsonl", ".ndjson", ".yaml", ".yml", ".csv", ".tsv"}:
        text, _ = decode(data)
        return parse_structured(text, suffix)
    if suffix in {".txt", ".md", ".markdown", ".rst", ".ini", ".cfg", ".properties"}:
        text, encoding = decode(data)
        result = ParseResult("text/3")
        result.metadata["encoding"] = encoding
        chunks(result, text, config.get("chunk_chars", 5000))
        return result
    if suffix in DOCLING_EXTENSIONS:
        if suffix in {".docx", ".pptx"}:
            preflight_ooxml_metadata(
                io.BytesIO(data),
                original_name=path.name,
                source_hash=digest(data),
                limits=ExcelLimits.from_config(EXCEL_DEFAULTS),
            )
        result = ParseResult("docling/2.128.0")
        normalized = docling_convert(path)
        result.artifacts.update(normalized)
        chunks(
            result,
            normalized["normalized.md"],
            config.get("chunk_chars", 5000),
            representation="docling_markdown",
        )
        if normalized["conversion_status"] == "partial_success":
            result.status = "partial"
        return result
    raise DomainError(
        "unsupported_format",
        f"Formato non supportato: {suffix or 'senza estensione'}. I byte sono conservati.",
    )
