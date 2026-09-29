"""Shared structural resolver. Names are segmented before lookup, never guessed."""

from __future__ import annotations
import re
from collections import defaultdict

from dslm3.common import canonical, digest

VERSION = "1"
_PART = re.compile(r'"(?:""|[^"])*"|`(?:``|[^`])*`|\[(?:\]\]|[^\]])*\]|[^.\s]+')
CODE_TYPES = {
    "sql_procedure",
    "sql_function",
    "sql_trigger",
    "sql_package",
    "sql_package_body",
    "sql_type",
    "sql_type_body",
}
DATA_TYPES = {"ddl_table", "ddl_view", "ddl_materialized view", "ddl_synonym"}


def segments(name, dialect="oracle"):
    """Quoted dots remain part of one identifier; unquoted SQL names fold to upper."""
    return tuple(
        p[1:-1].replace(p[0] * 2, p[0])
        if p[0] in {'"', "`", "["}
        else p.lower()
        if dialect == "postgres"
        else p.upper()
        for p in _PART.findall(name)
    )


class Resolver:
    def __init__(self, evidence):
        self.evidence = evidence
        self.index = defaultdict(list)
        for e in evidence:
            kind = (
                "data_object"
                if e["type"] in DATA_TYPES
                else "column"
                if e["type"] == "ddl_column"
                else "code_unit"
                if e["type"] in CODE_TYPES
                else None
            )
            if kind:
                self.index[kind].append(e)

    def resolve(self, raw, kind="data_object"):
        key = segments(raw)
        rows = [
            e
            for e in self.index[kind]
            if segments(e["data"]["name"], e["data"].get("dialect"))[-len(key) :]
            == segments(raw, e["data"].get("dialect"))
        ]
        body_fallback = False
        if not rows and kind == "code_unit":
            # A body-only package declares callable members too. Prefer an exact
            # specification when present, without collapsing spec/body identity.
            rows = [
                e
                for e in self.index[kind]
                if "::BODY." in e["data"]["name"]
                and segments(
                    e["data"]["name"].replace("::BODY.", "."), e["data"].get("dialect")
                )[-len(key) :]
                == segments(raw, e["data"].get("dialect"))
            ]
            body_fallback = bool(rows)
        names = {segments(e["data"]["name"]) for e in rows}
        # Duplicate identical declarations are independent support; incompatible ones
        # and overloads are not disambiguated by insertion order.
        signatures = {canonical(e["data"]) for e in rows}
        if kind == "code_unit":
            signatures = {(canonical(e["data"]), e["text"]) for e in rows}
        if kind == "data_object":
            signatures = set()
            for e in rows:
                cols = [
                    c["data"]
                    for c in self.index["column"]
                    if c["revision_id"] == e["revision_id"]
                    and c["data"]["table"] == e["data"]["name"]
                ]
                signatures.add(
                    canonical([e["data"], sorted(cols, key=lambda c: c["name"])])
                )
        status = (
            "unresolved"
            if not rows
            else "ambiguous"
            if len(names) > 1 or len(signatures) > 1
            else "resolved"
        )
        reason = (
            "target_absent"
            if not rows
            else "multiple_targets"
            if status == "ambiguous"
            else "package_body_declaration"
            if body_fallback
            else "unique_declaration"
        )
        bases = sorted(e["id"] for e in rows)
        prerequisites = []
        if kind == "column" and rows:
            prerequisites = [
                self.resolve(table)
                for table in sorted({e["data"]["table"] for e in rows})
            ]
            bases = sorted(
                set(bases)
                | {eid for r in prerequisites for eid in r["basis_evidence_ids"]}
            )
            if any(r["status"] != "resolved" for r in prerequisites):
                status, reason = "ambiguous", "column_parent_ambiguous"
        answer = {
            "status": status,
            "raw_target": raw,
            "target_kind": kind,
            "canonical_target": rows[0]["data"]["name"]
            if status == "resolved"
            else None,
            "reason_code": reason,
            "basis_evidence_ids": bases,
            "alternatives": sorted({e["data"]["name"] for e in rows}),
            "prerequisites": prerequisites,
            "lookup": {
                "segments": list(key),
                "kind": kind,
                "scope": "current_structural_evidence",
            },
        }
        answer["context_fingerprint"] = digest(answer)
        return answer

    def foreign_key(self, data):
        source = self.resolve(data["table"])
        target = self.resolve(data["target_table"])
        cols = list(data["columns"])
        target_cols = list(data["target_columns"])
        prerequisites = [source, target]
        if not target_cols and target["status"] == "resolved":
            pks = [
                e
                for e in self.evidence
                if e["type"] == "ddl_constraint"
                and e["data"]["constraint_type"] == "primary_key"
                and segments(e["data"]["table"]) == segments(target["canonical_target"])
            ]
            keys = {tuple(e["data"]["columns"]) for e in pks}
            if len(keys) == 1:
                target_cols = list(next(iter(keys)))
                prerequisites.append(
                    {
                        "status": "resolved",
                        "reason_code": "target_primary_key",
                        "basis_evidence_ids": sorted(e["id"] for e in pks),
                    }
                )
        for col in cols:
            prerequisites.append(
                self.resolve(
                    (source["canonical_target"] or data["table"]) + "." + col, "column"
                )
            )
        for col in target_cols:
            prerequisites.append(
                self.resolve(
                    (target["canonical_target"] or data["target_table"]) + "." + col,
                    "column",
                )
            )
        if data["target_columns"] and len(cols) != len(target_cols) or not cols:
            status, reason = "inconsistent", "foreign_key_arity"
        elif any(r["status"] == "ambiguous" for r in prerequisites):
            status, reason = "ambiguous", "foreign_key_ambiguous_endpoint"
        elif any(r["status"] != "resolved" for r in prerequisites) or not target_cols:
            status, reason = (
                "unresolved",
                "foreign_key_missing_endpoint"
                if target_cols
                else "foreign_key_target_key_unknown",
            )
        else:
            status, reason = "resolved", "foreign_key_endpoints_verified"
        value = {
            "status": status,
            "reason_code": reason,
            "raw_target": data["target_table"],
            "canonical_target": target["canonical_target"]
            if status == "resolved"
            else None,
            "source": source["canonical_target"],
            "columns": cols,
            "target_columns": target_cols,
            "prerequisites": prerequisites,
            "basis_evidence_ids": sorted(
                {eid for r in prerequisites for eid in r["basis_evidence_ids"]}
            ),
        }
        value["context_fingerprint"] = digest(value)
        return value
