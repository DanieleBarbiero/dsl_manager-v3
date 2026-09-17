"""Temporal evidence is not validity. Every interval is a reviewable proposal."""

from __future__ import annotations
import calendar
import io
import json
import re
import zipfile
from collections import defaultdict
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from lxml import etree
from dslm3.common import DomainError, canonical, now, uid
from dslm3.knowledge import Knowledge

DATE = r"\d{4}(?:-\d{2}(?:-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?)?)?"
ROLES = {
    "valid_from": "valid_from",
    "valid_to": "valid_to",
    "effective_date": "effective_date",
    "competence_year": "competence_year",
    "decorrono dal": "valid_from",
    "valido dal": "valid_from",
    "valida dal": "valid_from",
    "valido fino al": "valid_to",
}
TARGETS = {
    "source_revision": ("revisions", None),
    "source_fragment": ("evidence", None),
    "candidate_record": ("candidates", None),
    "fact": ("objects", "fact"),
    "relation": ("objects", "relation"),
}


def point(raw: str, tz: str | None = None) -> dict:
    raw = raw.strip()
    if re.fullmatch(r"\d{4}", raw):
        date(int(raw), 1, 1)
        return {
            "start": raw + "-01-01",
            "end": raw + "-12-31",
            "precision": "year",
            "timezone_status": "unknown",
            "timezone_value": None,
            "bounds_semantics": "coverage_envelope",
            "timeformat": "date",
        }
    if re.fullmatch(r"\d{4}-\d\d", raw):
        year, month = map(int, raw.split("-"))
        last = calendar.monthrange(year, month)[1]
        return {
            "start": raw + "-01",
            "end": raw + f"-{last:02}",
            "precision": "month",
            "timezone_status": "unknown",
            "timezone_value": None,
            "bounds_semantics": "coverage_envelope",
            "timeformat": "date",
        }
    if re.fullmatch(r"\d{4}-\d\d-\d\d", raw):
        date.fromisoformat(raw)
        return {
            "start": raw,
            "end": raw,
            "precision": "day",
            "timezone_status": "unknown",
            "timezone_value": None,
            "bounds_semantics": "inclusive",
            "timeformat": "date",
        }
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    status = "explicit" if value.tzinfo else "unknown"
    tzvalue = None
    if not value.tzinfo and tz:
        zone = ZoneInfo(tz)
        a = value.replace(tzinfo=zone, fold=0)
        b = value.replace(tzinfo=zone, fold=1)
        if a.utcoffset() != b.utcoffset():
            raise DomainError(
                "ambiguous_local_time",
                "Ora locale ambigua o inesistente: specificare offset.",
            )
        if a.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) != value:
            raise DomainError("invalid_local_time", "Ora locale inesistente.")
        value = a
        status = "resolved"
        tzvalue = tz
    if value.tzinfo:
        tzvalue = tzvalue or (
            "UTC"
            if value.utcoffset().total_seconds() == 0
            else value.strftime("%z")[:3] + ":" + value.strftime("%z")[3:]
        )
    fraction = re.search(r":\d{2}\.(\d+)", raw)
    if fraction and len(fraction[1]) > 6:
        raise DomainError(
            "temporal_precision",
            "Precisione oltre il microsecondo non supportata; nessun troncamento.",
        )
    precision = (
        ("millisecond" if len(fraction[1]) <= 3 else "microsecond")
        if fraction
        else ("second" if re.search(r"[T ]\d{2}:\d{2}:\d{2}", raw) else "minute")
    )
    text = value.isoformat(
        timespec="milliseconds"
        if precision == "millisecond"
        else "microseconds"
        if precision == "microsecond"
        else "seconds"
    ).replace("+00:00", "Z")
    return {
        "start": text,
        "end": text,
        "precision": precision,
        "timezone_status": status,
        "timezone_value": tzvalue,
        "bounds_semantics": "inclusive",
        "timeformat": "dateTime",
    }


def comparable(value):
    if value is None:
        return None
    if "T" not in value:
        return date.fromisoformat(value)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate_interval(p: dict, strict=False):
    if p.get("target_subject_type") not in TARGETS:
        raise DomainError("temporal_target", "Tipo soggetto temporale non ammesso.")
    a = p.get("normalized_start")
    b = p.get("normalized_end")
    if not a and not b:
        raise DomainError("temporal_bounds", "Intervallo senza limiti.")
    if p.get("original_precision") not in {
        "year",
        "month",
        "day",
        "second",
        "minute",
        "millisecond",
        "microsecond",
    }:
        raise DomainError("temporal_precision", "Precisione non ammessa.")
    if p.get("timezone_status") not in {
        "explicit",
        "resolved",
        "unknown",
        "incompatible",
    }:
        raise DomainError("temporal_timezone", "Stato timezone non ammesso.")
    if p.get("bounds_semantics") not in {"inclusive", "coverage_envelope"}:
        raise DomainError("temporal_bounds", "Semantica limiti non ammessa.")
    try:
        for value in (a, b):
            if value:
                point(value)
        if a and b:
            if ("T" in a) != ("T" in b):
                raise DomainError(
                    "mixed_timeformat", "Data e timestamp non possono essere mescolati."
                )
            if comparable(a) > comparable(b):
                raise DomainError("temporal_order", "Fine precedente all’inizio.")
        if strict and any(
            value and "T" in value and comparable(value).tzinfo is None
            for value in (a, b)
        ):
            raise DomainError(
                "temporal_timezone_unknown",
                "Timestamp senza timezone: serve una correzione con offset.",
            )
        if strict and p["timezone_status"] == "incompatible":
            raise DomainError(
                "temporal_timezone_incompatible", "Timezone incompatibili."
            )
    except (ValueError, TypeError) as exc:
        if isinstance(exc, DomainError):
            raise
        raise DomainError("temporal_invalid", str(exc)) from exc


def overlap(a, b):
    # Incompatible granularity is uncertain, not proof of non-overlap.
    try:
        if (
            a.get("normalized_end")
            and b.get("normalized_start")
            and comparable(a["normalized_end"]) < comparable(b["normalized_start"])
        ):
            return False
        if (
            b.get("normalized_end")
            and a.get("normalized_start")
            and comparable(b["normalized_end"]) < comparable(a["normalized_start"])
        ):
            return False
    except TypeError:
        return True
    return True


class Temporal:
    def __init__(self, app):
        self.app, self.store, self.knowledge = app, app.store, Knowledge(app)

    def require_target(self, conn, kind, ident):
        if kind not in TARGETS:
            raise DomainError("temporal_target", "Tipo soggetto temporale ignoto.")
        table, object_kind = TARGETS[kind]
        row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (ident,)).fetchone()
        if row is None or object_kind and row["kind"] != object_kind:
            raise DomainError("temporal_target", "Soggetto temporale inesistente.")

    def add_raw(self, revision, subject_type, subject_id, records):
        ids = []
        if len(records) > self.store.config()["max_evidence"]:
            raise DomainError("temporal_budget", "Troppe evidenze temporali.")
        with self.store.connect(True) as conn:
            self.require_target(conn, subject_type, subject_id)
            for r in records:
                value = {
                    **r,
                    "extraction_version": "3",
                    "warnings": r.get("warnings", []),
                }
                try:
                    value.update(
                        {
                            k: v
                            for k, v in point(str(r["raw_value"])).items()
                            if k not in {"start", "end"}
                        }
                    )
                except Exception:
                    value["warnings"].append("date_not_normalizable")
                ident = uid("TEV", [revision, subject_type, subject_id, value])
                ids.append(ident)
                conn.execute(
                    "INSERT OR IGNORE INTO temporal_raw VALUES(?,?,?,?,?)",
                    (ident, revision, subject_type, subject_id, canonical(value)),
                )
        return ids

    def extract(self, revision):
        r = self.store.one(
            "SELECT r.*,s.path,s.first_seen FROM revisions r JOIN sources s ON s.id=r.source_id WHERE r.id=?",
            (revision,),
        )
        if not r:
            raise DomainError("unknown_revision", "Revisione inesistente.")
        path = self.app.root / r["object_path"]
        data = path.read_bytes()
        suffix = path.suffix.lower()
        records = []

        def add(
            key,
            raw,
            source_format,
            role="document_time",
            reliability="low",
            family=None,
        ):
            records.append(
                {
                    "source_key": key,
                    "raw_value": raw,
                    "source_format": source_format,
                    "date_role": role,
                    "initial_reliability": reliability,
                    "correlation_family": family or source_format,
                    "extraction_method": "static_metadata",
                    "warnings": ["not_semantic_validity"]
                    if role
                    not in {
                        "valid_from",
                        "valid_to",
                        "effective_date",
                        "competence_year",
                    }
                    else ["requires_review"],
                }
            )

        add("sources.first_seen_at", r["first_seen"], "registry", "operational_time")
        for m in re.finditer(r"(?<!\d)\d{4}(?:-\d{2}(?:-\d{2})?)?(?!\d)", path.name):
            add("filename:" + str(m.start()), m[0], "filename", "filename_time")
        text = "\n".join(
            e["text"] for e in self.app.evidence(revision) if e["kind"] == "chunk"
        )
        if suffix in {
            ".txt",
            ".md",
            ".sql",
            ".xml",
            ".log",
            ".html",
            ".htm",
            ".json",
            ".yaml",
            ".yml",
        }:
            from dslm3.parsers.documents import decode

            text = decode(data)[0]
        if zipfile.is_zipfile(io.BytesIO(data)) and suffix in {
            ".xlsx",
            ".xlsm",
            ".docx",
            ".pptx",
            ".ods",
            ".odt",
        }:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for info in archive.infolist():
                    if len(records) >= self.store.config()["max_evidence"]:
                        raise DomainError("temporal_budget", "Troppe parti ZIP.")
                    try:
                        stamp = datetime(*info.date_time).isoformat()
                        add(
                            "zip:" + info.filename,
                            stamp,
                            "zip_timestamp",
                            "archive_time",
                            family="zip",
                        )
                    except ValueError:
                        pass
                for name in ["docProps/core.xml", "docProps/app.xml", "meta.xml"]:
                    if name not in archive.namelist():
                        continue
                    raw = archive.read(name)
                    if re.search(rb"<!\s*(DOCTYPE|ENTITY)", raw, re.I):
                        raise DomainError("unsafe_xml", "Metadata XML non sicuri.")
                    root = etree.fromstring(
                        raw, etree.XMLParser(resolve_entities=False, no_network=True)
                    )
                    for node in root.iter():
                        local = etree.QName(node).localname
                        if node.text and re.fullmatch(DATE, node.text.strip()):
                            add(
                                name + ":" + local,
                                node.text.strip(),
                                "ooxml_property",
                                "document_" + local,
                                reliability="medium",
                                family="ooxml_properties",
                            )
        for m in re.finditer(
            r"(?i)(?<![A-Za-z0-9])[_*]*("
            + "|".join(re.escape(x).replace("_", r"\\?_") for x in ROLES)
            + r')(?![A-Za-z0-9])[_*]*\s*(?:[:=]|>)?\s*[_*]*["\']?('
            + DATE
            + r")",
            text,
        ):
            add(
                "declaration:" + str(m.start()),
                m[2],
                suffix.lstrip(".") + "_declaration",
                ROLES[m[1].lower().replace("\\", "")],
                "high",
                "explicit_text",
            )
        if suffix == ".pdf":
            raw = data.decode("latin1")
            for m in re.finditer(
                r"/(CreationDate|ModDate)\s*\(D:(\d{14})([Z+-])?(\d\d)?\x27?(\d\d)?",
                raw,
            ):
                v = m[2]
                value = f"{v[:4]}-{v[4:6]}-{v[6:8]}T{v[8:10]}:{v[10:12]}:{v[12:14]}"
                if m[3] == "Z":
                    value += "Z"
                elif m[3] and m[4]:
                    value += m[3] + m[4] + ":" + (m[5] or "00")
                add("pdf:" + m[1], value, "pdf_info", "document_" + m[1], "medium")
            for m in re.finditer(
                r"<(?:\w+:)?(CreateDate|ModifyDate|MetadataDate)[^>]*>(" + DATE + r")<",
                raw,
            ):
                add("xmp:" + m[1], m[2], "pdf_xmp", "document_" + m[1], "medium")
        if suffix in {".html", ".htm"}:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(text, "html.parser")
            for i, node in enumerate(soup.find_all("time")):
                if node.get("datetime"):
                    add("html:time:" + str(i), node["datetime"], "html_time")
            for i, node in enumerate(soup.find_all("meta")):
                name = (
                    node.get("name")
                    or node.get("property")
                    or node.get("itemprop")
                    or ""
                )
                if any(
                    k in name.lower() for k in ["date", "time", "modified", "published"]
                ) and node.get("content"):
                    add(
                        "html:meta:" + str(i),
                        node["content"],
                        "html_meta",
                        "document_" + name,
                        "medium",
                    )
            for i, node in enumerate(
                soup.find_all("script", type="application/ld+json")
            ):
                try:
                    obj = json.loads(node.string or "")
                except json.JSONDecodeError:
                    continue

                def walk(value, pointer=""):
                    if isinstance(value, dict):
                        for k, v in value.items():
                            if k in {
                                "dateCreated",
                                "dateModified",
                                "datePublished",
                                "validFrom",
                                "validThrough",
                            } and isinstance(v, str):
                                add(
                                    "jsonld:" + pointer + "/" + k,
                                    v,
                                    "json_ld",
                                    {
                                        "validFrom": "valid_from",
                                        "validThrough": "valid_to",
                                    }.get(k, "document_" + k),
                                    "medium",
                                )
                            walk(v, pointer + "/" + k)
                    elif isinstance(value, list):
                        for n, v in enumerate(value):
                            walk(v, pointer + "/" + str(n))

                walk(obj)
        return {
            "revision_id": revision,
            "evidence_ids": self.add_raw(
                revision, "source_revision", revision, records
            ),
            "count": len(records),
        }

    def raw(self, subject_type=None, subject_id=None):
        where = ""
        args = ()
        if subject_type and subject_id:
            where = " WHERE subject_type=? AND subject_id=?"
            args = (subject_type, subject_id)
        rows = self.store.rows(
            "SELECT * FROM temporal_raw" + where + " ORDER BY id", args
        )
        for r in rows:
            r["payload"] = json.loads(r["payload"])
        return rows

    def propose(
        self,
        revision,
        subject_type,
        subject_id,
        ids,
        start=None,
        end=None,
        precision=None,
        tz=None,
        policy="explicit_copy",
        confidence="low",
    ):
        records = {r["id"]: r for r in self.raw()}
        selected = [records.get(i) for i in ids]
        if not selected or any(r is None for r in selected):
            raise DomainError(
                "temporal_evidence_missing", "Evidenze temporali mancanti."
            )
        with self.store.connect() as conn:
            self.require_target(conn, subject_type, subject_id)
        if start is None and end is None:
            start = selected[0]["payload"]["raw_value"]
            end = start
        a = point(start, tz) if start else None
        b = point(end, tz) if end else None
        template = a or b
        precision = precision or template["precision"]
        p = {
            "record_type": "temporal_interval",
            "candidate_id": uid(
                "TEMP", [subject_type, subject_id, ids, start, end, tz, policy]
            ),
            "source_revision_id": revision,
            "assertion_type": "inferred",
            "confidence": confidence,
            "evidence_text": " | ".join(r["payload"]["raw_value"] for r in selected),
            "target_subject_type": subject_type,
            "target_subject_id": subject_id,
            "normalized_start": a["start"] if a else None,
            "normalized_end": b["end"] if b else None,
            "original_precision": precision,
            "timezone_status": template["timezone_status"],
            "timezone_value": template["timezone_value"],
            "bounds_semantics": "coverage_envelope"
            if precision in {"year", "month"}
            else "inclusive",
            "temporal_evidence_ids": ids,
            "derivation_policy_id": policy,
            "derivation_policy_version": "3",
        }
        return self.knowledge.import_candidates([p], "temporal:" + policy)

    def consolidate(self, subject_type, subject_id):
        records = self.raw(subject_type, subject_id)
        by_role = defaultdict(list)
        groups = []
        proposals = []
        for r in records:
            if "date_not_normalizable" not in r["payload"]["warnings"]:
                by_role[r["payload"]["date_role"]].append(r)
        for role, items in sorted(by_role.items()):
            buckets = defaultdict(list)
            for r in items:
                p = point(r["payload"]["raw_value"])

                def normalized(value):
                    parsed = comparable(value)
                    return (
                        parsed.astimezone(timezone.utc).isoformat()
                        if isinstance(parsed, datetime) and parsed.tzinfo
                        else value
                    )

                buckets[
                    canonical(
                        [
                            normalized(p["start"]),
                            normalized(p["end"]),
                            p["precision"],
                            p["timezone_status"],
                        ]
                    )
                ].append(r)
            conflict = len(buckets) > 1
            for _, same in sorted(buckets.items()):
                independent = set()
                for r in same:
                    rev = self.store.one(
                        "SELECT sha256 FROM revisions WHERE id=?", (r["revision_id"],)
                    )
                    independent.add(rev["sha256"])
                assessment = (
                    "conflicting"
                    if conflict
                    else "concordant"
                    if len(independent) > 1
                    else "single_or_correlated"
                )
                group = {
                    "subject_type": subject_type,
                    "subject_id": subject_id,
                    "role": role,
                    "assessment": assessment,
                    "independent_sources": len(independent),
                    "evidence_ids": [r["id"] for r in same],
                }
                gid = uid("TGROUP", group)
                with self.store.connect(True) as conn:
                    conn.execute(
                        "INSERT OR IGNORE INTO temporal_groups VALUES(?,?,?)",
                        (gid, canonical(group), now()),
                    )
                groups.append({"id": gid, **group})
                # Preserve raw metadata as reviewable alternatives. Explicit validity
                # declarations are distinguished by policy; neither auto-confirms.
                if (
                    role in {"valid_to", "valid_from"}
                    and len(by_role.get("valid_from", [])) == 1
                    and len(by_role.get("valid_to", [])) == 1
                ):
                    if role == "valid_to":
                        continue
                    first = by_role["valid_from"][0]
                    last = by_role["valid_to"][0]
                    ids = [first["id"], last["id"]]
                    start = first["payload"]["raw_value"]
                    end = last["payload"]["raw_value"]
                else:
                    ids = [r["id"] for r in same]
                    start = end = same[0]["payload"]["raw_value"]
                try:
                    proposals.append(
                        self.propose(
                            same[0]["revision_id"],
                            subject_type,
                            subject_id,
                            ids,
                            start,
                            end,
                            policy="consolidate:" + role,
                            confidence="medium"
                            if len(independent) > 1 and not conflict
                            else "low",
                        )
                    )
                except (ValueError, DomainError) as exc:
                    groups[-1]["proposal_error"] = str(exc)
        return {
            "groups": groups,
            "proposals": proposals,
            "conflict_count": sum(g["assessment"] == "conflicting" for g in groups),
        }

    def propagate(
        self, source_subjects, target_type, target_id, policy="explicit_copy"
    ):
        if policy not in {"explicit_copy", "intersection", "aggregation", "conflict"}:
            raise DomainError("temporal_policy", "Policy di propagazione ignota.")
        selected = [
            o
            for o in self.knowledge.objects()
            if o["kind"] == "interval"
            and (
                o["payload"]["target_subject_type"]
                + ":"
                + o["payload"]["target_subject_id"]
            )
            in source_subjects
        ]
        if not selected:
            raise DomainError(
                "temporal_source_missing",
                "Nessun intervallo confermato e consolidato sui soggetti indicati.",
            )
        groups = {s: [] for s in source_subjects}
        for o in selected:
            groups[
                o["payload"]["target_subject_type"]
                + ":"
                + o["payload"]["target_subject_id"]
            ].append(o["payload"])
        if any(not v for v in groups.values()):
            raise DomainError(
                "temporal_source_missing", "Un soggetto non ha intervalli effettivi."
            )
        if policy == "conflict":
            data = {
                "policy": policy,
                "sources": source_subjects,
                "target_type": target_type,
                "target_id": target_id,
                "assessment": "conflicting",
            }
            gid = uid("TGROUP", data)
            with self.store.connect(True) as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO temporal_groups VALUES(?,?,?)",
                    (gid, canonical(data), now()),
                )
            return {"status": "conflict", "group_id": gid, "proposals": []}
        intervals = [o["payload"] for o in selected]
        if policy == "intersection":
            current = next(iter(groups.values()))
            for others in list(groups.values())[1:]:
                next_ = []
                for a in current:
                    for b in others:
                        if not overlap(a, b):
                            continue
                        try:
                            start = max(
                                (
                                    v
                                    for v in [
                                        a.get("normalized_start"),
                                        b.get("normalized_start"),
                                    ]
                                    if v
                                ),
                                key=comparable,
                                default=None,
                            )
                            end = min(
                                (
                                    v
                                    for v in [
                                        a.get("normalized_end"),
                                        b.get("normalized_end"),
                                    ]
                                    if v
                                ),
                                key=comparable,
                                default=None,
                            )
                        except TypeError:
                            raise DomainError(
                                "mixed_timeformat", "Profili temporali incompatibili."
                            )
                        next_.append(
                            {**a, "normalized_start": start, "normalized_end": end}
                        )
                current = next_
            intervals = current
        # aggregation is a union preserving disjoint spells, not a filled envelope.
        ids = sorted(
            {
                i
                for o in selected
                for s in o["supports"]
                for i in s["candidate_payload"]["temporal_evidence_ids"]
            }
        )
        revision = selected[0]["supports"][0]["candidate_payload"]["source_revision_id"]
        proposals = []
        for p in {canonical(v): v for v in intervals}.values():
            proposals.append(
                self.propose(
                    revision,
                    target_type,
                    target_id,
                    ids,
                    p.get("normalized_start"),
                    p.get("normalized_end"),
                    p["original_precision"],
                    policy=policy,
                )
            )
        return {"policy": policy, "proposals": proposals, "count": len(proposals)}
