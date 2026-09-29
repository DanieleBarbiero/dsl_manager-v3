"""Capability inventory, deterministic component plans and measured coverage.

The inventory is built from evidence structure, independently of stored candidates.
No broad exception handler converts programming errors into unsupported input.
"""

from __future__ import annotations
from collections import Counter
from pathlib import PurePosixPath

from dslm3.common import DomainError, canonical, digest, uid
from dslm3.resolution import Resolver, CODE_TYPES

CONTRACT_VERSION = "4"
RULE_VERSION = "4.0"
DDL_OBJECTS = {
    "ddl_table",
    "ddl_view",
    "ddl_materialized view",
    "ddl_index",
    "ddl_sequence",
    "ddl_synonym",
    "ddl_database_link",
    "ddl_directory",
    "ddl_tablespace",
    "ddl_cluster",
    "ddl_context",
    "ddl_library",
    "ddl_type",
}
XML_TYPES = {
    "xml_form": "xml_form",
    "xml_block": "xml_form_block",
    "xml_field": "xml_form_field",
    "xml_button": "xml_form_button",
}
EXCEL = {
    "excel_workbook",
    "excel_sheet",
    "excel_region",
    "excel_named_range",
    "excel_table",
}
STRUCTURED = {
    "dataset_schema",
    "dataset_row",
    "dataset_record",
    "structured_document",
    "email_headers",
    "xml_document",
}
EVIDENCE_ONLY = {
    "document_text": "free_text_requires_interpretation",
    "xml_code": "forms_code_analyzer_not_enabled",
    "ddl_drop": "observed_ddl_no_execution",
    "ddl_grant": "observed_access_declaration",
    "ddl_revoke": "observed_access_declaration",
}
REGISTERED = (
    DDL_OBJECTS
    | CODE_TYPES
    | XML_TYPES.keys()
    | EXCEL
    | STRUCTURED
    | EVIDENCE_ONLY.keys()
    | {
        "ddl_column",
        "ddl_constraint",
        "ddl_alter",
        "sql_statement",
        "sql_dependency",
        "sql_unparsed",
        "sql_anonymous_block",
        "xml_dependency",
        "xml_button_operation",
        "log_event",
        "log_unparsed",
        "excel_explicit_reference",
    }
)
CONSTRAINTS = {"primary_key", "foreign_key", "unique", "check"}
STATEMENTS = {
    "update",
    "insert",
    "delete",
    "merge",
    "select",
    "union",
    "intersect",
    "except",
    "call",
    "transaction",
    "commit",
    "rollback",
    "set",
    "use",
    "pragma",
}
RELATIONS = {
    "reads_from",
    "writes_to",
    "calls",
    "trigger_on",
    "indexes",
    "synonym_for",
    "maps_to",
    "uses_table",
}
PARSER_TYPES = {
    "sql": DDL_OBJECTS
    | CODE_TYPES
    | {
        "ddl_column",
        "ddl_constraint",
        "ddl_alter",
        "ddl_drop",
        "ddl_grant",
        "ddl_revoke",
        "sql_statement",
        "sql_dependency",
        "sql_unparsed",
        "sql_anonymous_block",
    },
    "xml_forms": set(XML_TYPES)
    | {
        "xml_dependency",
        "xml_button_operation",
        "xml_code",
        "xml_document",
        "document_text",
    },
    "log": {"log_event", "log_unparsed"},
    "ooxml": EXCEL | {"excel_explicit_reference", "document_text"},
    "structured": STRUCTURED | {"document_text"},
    "email": {"email_headers", "document_text"},
    "legacy_spreadsheet": {"excel_sheet", "dataset_row"},
    "text": {"document_text"},
    "docling": {"document_text"},
}


def candidate_id(payload, rule):
    return uid("CAND", ["deterministic/4", payload, rule])


def inventory(evidence):
    resolver = Resolver(evidence)
    rows = []
    for e in evidence:
        d, kind = e["data"], e["type"]
        subtype = (
            d.get("constraint_type")
            or d.get("statement_type")
            or d.get("relation_type")
            or "default"
        )
        row = {
            "evidence_id": e["id"],
            "locator": e["locator"],
            "type": kind,
            "subtype": subtype,
            "format": PurePosixPath(e.get("path", "")).suffix,
            "parser": e.get("parser_version", e.get("parse_id")),
            "components": [],
        }
        rows.append(row)

        def component(
            key,
            fields=None,
            rule=None,
            resolution=None,
            capability="supported",
            reason=None,
        ):
            res = resolution or {
                "status": "not_required",
                "reason_code": "syntactic_extraction",
                "basis_evidence_ids": [e["id"]],
            }
            blocked = capability == "supported" and res["status"] not in {
                "resolved",
                "not_required",
            }
            item = {
                "key": key,
                "capability": capability,
                "applicability": "blocked_by_resolution"
                if blocked
                else "applicable"
                if capability == "supported"
                else "not_required",
                "rule": rule,
                "rule_version": RULE_VERSION,
                "resolution": res,
                "reason_code": reason or res["reason_code"],
                "context_fingerprint": res.get(
                    "context_fingerprint", digest([e["id"], key, CONTRACT_VERSION])
                ),
                "prerequisites": res.get("prerequisites", [res]),
                "expected": [],
            }
            row["components"].append(item)
            if fields is not None and capability == "supported" and not blocked:
                payload = {
                    "record_type": "candidate_fact",
                    "assertion_type": "explicit",
                    "confidence": "high",
                    "source_revision_id": e["revision_id"],
                    "evidence_id": e["id"],
                    "fragment_id": e["id"] if e["kind"] == "fragment" else None,
                    "chunk_id": e["id"] if e["kind"] == "chunk" else None,
                    "evidence_text": e["text"],
                    **fields,
                    "deterministic_contract": CONTRACT_VERSION,
                    "derivation": {
                        "rule_version": RULE_VERSION,
                        "component": key,
                        "context_fingerprint": item["context_fingerprint"],
                        "resolution": res,
                    },
                }
                payload["candidate_id"] = uid(
                    "DER", [e["id"], key, RULE_VERSION, payload]
                )
                item["expected"] = [
                    {
                        "id": candidate_id(payload, rule),
                        "payload": payload,
                        "rule": rule,
                    }
                ]
            return item

        def fact(
            key, entity, prop, value, fact_type="technical", rule=None, attributes=None
        ):
            return component(
                key,
                {
                    "entity_name": entity,
                    "property_name": prop,
                    "property_value": value,
                    "fact_type": fact_type,
                    "attributes": attributes or {},
                },
                rule or kind,
            )

        parser = e.get("parser")
        unknown = (
            (
                parser is not None
                and kind not in PARSER_TYPES.get(parser.split("/")[0], set())
            )
            or kind not in REGISTERED
            or kind == "ddl_constraint"
            and subtype not in CONSTRAINTS
            or kind == "sql_statement"
            and subtype not in STATEMENTS
            or kind in {"sql_dependency", "xml_dependency", "xml_button_operation"}
            and subtype not in RELATIONS
        )
        if unknown:
            component(
                "unclassified",
                capability="unclassified",
                reason="unregistered_type_or_subtype",
            )
        elif kind in EVIDENCE_ONLY:
            component(
                "retained", capability="evidence_only", reason=EVIDENCE_ONLY[kind]
            )
        elif kind in {"sql_unparsed", "log_unparsed"}:
            component(
                "unparsed",
                capability="unsupported",
                reason="syntax_not_analyzed"
                if kind == "sql_unparsed"
                else "unrecognized_log_line",
            )
        elif kind == "ddl_alter":
            if d.get("supported"):
                fact(
                    "declaration",
                    d["name"],
                    "alter_declaration",
                    d["ast"],
                    attributes={"context": {"declaration": e["id"]}},
                    rule="ddl_declaration",
                )
            else:
                component(
                    "alter",
                    capability="unsupported",
                    reason="alter_outside_add_constraint",
                )
        elif kind in DDL_OBJECTS:
            fact(
                "declaration",
                d["name"],
                "object_type",
                d.get("object_type", kind[4:]),
                "database_table" if kind == "ddl_table" else "database_object",
                "ddl_table" if kind == "ddl_table" else "sql_unit",
                d,
            )
        elif kind == "ddl_column":
            fact(
                "definition",
                d["name"],
                "data_type",
                d["datatype"],
                "database_column",
                "ddl_column",
                d,
            )
        elif kind == "ddl_constraint":
            ident = d.get("constraint_id") or uid("CONSTRAINT", d)
            fact(
                "declaration",
                ident,
                "constraint",
                d,
                "database_constraint",
                "ddl_declaration",
            )
            if subtype == "foreign_key":
                res = resolver.foreign_key(d)
                component(
                    "resolved_relation",
                    {
                        "record_type": "candidate_relation",
                        "source_entity": res["source"],
                        "relation_type": "foreign_key",
                        "target_entity": res["canonical_target"],
                        "attributes": {
                            "constraint_id": ident,
                            "columns": res["columns"],
                            "target_columns": res["target_columns"],
                        },
                    },
                    "ddl_constraint",
                    res,
                )
        elif kind in CODE_TYPES | {"sql_anonymous_block"}:
            fact(
                "declaration",
                d["name"],
                "unit_type",
                d["unit_type"],
                "database_code_unit",
                "sql_unit",
                d,
            )
            if d.get("dynamic_sql"):
                component(
                    "dynamic_sql",
                    capability="unsupported",
                    reason="dynamic_sql_not_executed",
                )
        elif kind in XML_TYPES:
            fact(
                "definition",
                d["name"],
                "definition",
                {
                    "object_type": kind[4:],
                    **{k: v for k, v in d.items() if k != "name"},
                },
                XML_TYPES[kind],
                "xml_structure",
            )
        elif kind in {"sql_dependency", "xml_dependency", "xml_button_operation"}:
            if d.get("builtin"):
                fact(
                    "builtin",
                    d["source"],
                    "builtin_call",
                    d["target"],
                    "sql_operation",
                    "sql_statement",
                    {
                        "context": {"occurrence": e["locator"]},
                        "catalog": "oracle_intrinsics/1",
                    },
                )
                continue
            target_kind = d.get("target_kind") or (
                "code_unit"
                if subtype == "calls"
                else "column"
                if subtype == "maps_to"
                else "data_object"
            )
            res = resolver.resolve(d["target"], target_kind)
            if d.get("inconsistent"):
                res.update(
                    status="inconsistent",
                    reason_code=d["inconsistent"],
                    canonical_target=None,
                )
                res["context_fingerprint"] = digest(res)
            if "@" in d["target"] and subtype == "synonym_for":
                res = {
                    "status": "resolved",
                    "reason_code": "explicit_external_reference",
                    "canonical_target": d["target"],
                    "basis_evidence_ids": [e["id"]],
                }
            attrs = {
                k: v
                for k, v in d.items()
                if k not in {"source", "target", "relation_type", "target_kind"}
            }
            component(
                "relation",
                {
                    "record_type": "candidate_relation",
                    "source_entity": d["source"],
                    "relation_type": subtype,
                    "target_entity": res["canonical_target"],
                    "attributes": attrs,
                    "assertion_type": "observed"
                    if kind == "sql_dependency"
                    else "explicit",
                },
                kind,
                res,
            )
        elif kind == "sql_statement":
            context = {
                "owner": d.get("owner"),
                "statement_id": uid(
                    "STMT", [e.get("path"), d.get("statement_id"), e["locator"]]
                ),
            }
            attrs = {
                "context": context,
                "statement": {k: v for k, v in d.items() if k != "components"},
            }
            if d.get("unsupported"):
                component(
                    "statement", capability="unsupported", reason=d["unsupported"]
                )
            else:
                fact(
                    "statement",
                    d.get("target") or context["statement_id"],
                    "statement_structure",
                    attrs["statement"],
                    "sql_statement",
                    "sql_statement",
                    {"context": context},
                )
            for part in d.get("components", []):
                if part.get("unsupported"):
                    component(
                        part["key"],
                        capability="unsupported",
                        reason=part["unsupported"],
                    )
                else:
                    part_attrs = {
                        "context": {
                            **context,
                            "component": part["key"],
                            "branch": part.get("branch"),
                        },
                        **{
                            k: v
                            for k, v in part.items()
                            if k not in {"key", "entity", "property", "value"}
                        },
                    }
                    fact(
                        part["key"],
                        part["entity"],
                        part["property"],
                        part["value"],
                        "sql_operation",
                        "sql_statement",
                        part_attrs,
                    )
            for i, ref in enumerate(d.get("unresolved_references", [])):
                res = {
                    "status": "ambiguous"
                    if ref["reason"] == "ambiguous_column"
                    else "unresolved",
                    "raw_target": ref["name"],
                    "reason_code": ref["reason"],
                    "lookup": {
                        "table": ref.get("table"),
                        "owner": d.get("owner"),
                        "scope": "statement_ast",
                    },
                    "basis_evidence_ids": [e["id"]],
                }
                component(f"dependency:{i}", rule="sql_dependency", resolution=res)
        elif kind == "log_event":
            entity = "event:" + e["id"]
            item = fact("event", entity, "occurrence", d, "log_event", "log_event")
            item["expected"][0]["payload"]["assertion_type"] = "observed"
            # IDs must be computed after all epistemic fields are final.
            p = item["expected"][0]["payload"]
            item["expected"][0]["id"] = candidate_id(p, "log_event")
            if d.get("component"):
                component(
                    "component",
                    {
                        "record_type": "candidate_relation",
                        "source_entity": entity,
                        "relation_type": "observed_on",
                        "target_entity": d["component"],
                        "assertion_type": "observed",
                    },
                    "log_event",
                )
        elif kind in EXCEL:
            details = {
                k: v
                for k, v in d.items()
                if k not in {"name", "fragment_id", "source_revision_id"}
            }
            fact(
                "definition",
                d["name"],
                "definition",
                {"object_type": kind, **details},
                kind,
                kind,
            )
        elif kind == "excel_explicit_reference":
            component(
                "reference",
                {
                    "record_type": "candidate_relation",
                    "source_entity": d["name"],
                    "relation_type": "references_external",
                    "target_entity": d["target"],
                },
                "excel_explicit_reference",
            )
        elif kind in STRUCTURED:
            if not e["text"].strip():
                component("empty", capability="evidence_only", reason="empty_structure")
            else:
                fact(
                    "structure",
                    "record:" + e["id"],
                    "structure",
                    d,
                    "structured_record",
                    "structured_record",
                )
    return rows


def planned(rows):
    return [
        expected
        for row in rows
        for c in row["components"]
        for expected in c["expected"]
    ]


def coverage(rows, actual):
    """Compare ALL required results, not merely existence of any candidate."""
    counts = Counter()
    output = []
    for row in rows:
        components = []
        for c in row["components"]:
            item = {k: v for k, v in c.items() if k != "expected"}
            expected = c["expected"]
            valid = [
                r
                for r in expected
                if r["id"] in actual
                and canonical(actual[r["id"]]["payload"]) == canonical(r["payload"])
            ]
            item["candidate_ids"] = [r["id"] for r in valid]
            item["required_candidate_ids"] = [r["id"] for r in expected]
            item["governance"] = {r["id"]: actual[r["id"]]["state"] for r in valid}
            counts["expected_components"] += 1
            counts[c["capability"] + "_components"] += 1
            if c["applicability"] == "applicable":
                counts["due_applicable_components"] += 1
                outcome = (
                    "materialized_deterministically"
                    if expected and len(valid) == len(expected)
                    else "due_missing"
                )
                counts[
                    "derived_components"
                    if outcome == "materialized_deterministically"
                    else "due_missing_components"
                ] += 1
            elif c["applicability"] == "blocked_by_resolution":
                outcome = c["resolution"]["status"]
                counts["blocked_" + outcome + "_components"] += 1
            else:
                outcome = {
                    "evidence_only": "evidence_only_by_design",
                    "unsupported": "unsupported_with_reason",
                    "unclassified": "unclassified",
                }[c["capability"]]
            item["outcome"] = outcome
            components.append(item)
        outcomes = {c["outcome"] for c in components}
        outcome = next(iter(outcomes)) if len(outcomes) == 1 else "partial"
        counts["unclassified_evidence_count"] += int("unclassified" in outcomes)
        output.append(
            {
                **{k: v for k, v in row.items() if k != "components"},
                "outcome": outcome,
                "components": components,
            }
        )
    for key in (
        "expected_components",
        "supported_components",
        "due_applicable_components",
        "derived_components",
        "due_missing_components",
        "blocked_unresolved_components",
        "blocked_inconsistent_components",
        "blocked_ambiguous_components",
        "evidence_only_components",
        "unsupported_components",
        "unclassified_components",
        "unclassified_evidence_count",
        "internal_errors",
    ):
        counts.setdefault(key, 0)
    counts["active_evidence_count"] = len(rows)
    return {
        "contract_version": CONTRACT_VERSION,
        "rule_version": RULE_VERSION,
        "counts": dict(counts),
        "context_fingerprint": digest(
            [
                [r["evidence_id"], [c["context_fingerprint"] for c in r["components"]]]
                for r in rows
            ]
        ),
        "by_format_type_subtype": dict(
            Counter("/".join([r["format"], r["type"], r["subtype"]]) for r in rows)
        ),
        "complete": not any(
            counts[k]
            for k in (
                "unclassified_components",
                "due_missing_components",
                "internal_errors",
            )
        ),
        "evidence": output,
    }


def require_complete(report, expected_resolution=None):
    if not report["complete"]:
        raise DomainError(
            "deterministic_coverage_gap",
            "Copertura incompleta: " + canonical(report["counts"]),
        )
    if expected_resolution is not None:
        actual = {
            (r["evidence_id"], c["key"]): c["resolution"]["status"]
            for r in report["evidence"]
            for c in r["components"]
        }
        if any(
            actual.get(key) != status for key, status in expected_resolution.items()
        ):
            raise DomainError(
                "unexpected_resolution",
                "Risoluzione incompatibile con le attese della verifica.",
            )
    return report
