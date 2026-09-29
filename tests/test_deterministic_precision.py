"""Boundary assertions for exact NULL/default/literal contracts."""

import copy
import json

import pytest

from dslm3.common import DomainError
from dslm3.exports import Exports
from dslm3.parsers.sql import parse_sql
from test_deterministic_core import evidence, prepared, facts


def test_default_null_distinct_from_absent_and_string_literal():
    ev = evidence(
        "CREATE TABLE T(A NUMBER, B NUMBER DEFAULT NULL, C VARCHAR2(10) DEFAULT 'NULL', D NUMBER DEFAULT ABS(-1), E NUMBER NULL);"
    )
    cols = {e["data"]["column"]: e["data"] for e in ev if e["type"] == "ddl_column"}
    assert cols["A"]["default"] == {
        "present": False,
        "sql": None,
        "expression_ast": None,
    }
    assert cols["B"]["default"] == {
        "present": True,
        "sql": "NULL",
        "expression_ast": {"node": "literal", "type": "null", "value": None},
    }
    assert cols["C"]["default"]["expression_ast"] == {
        "node": "literal",
        "type": "string",
        "value": "NULL",
    }
    assert cols["D"]["default"]["expression_ast"]["node"] == "abs"
    assert cols["E"]["nullability_declaration"] == "null" and cols["E"]["nullable"]


def test_sqlite_primary_key_does_not_force_not_null():
    ev = parse_sql(
        "CREATE TABLE T(K TEXT PRIMARY KEY, N TEXT NOT NULL);", "sqlite"
    ).evidence
    cols = {e["data"]["column"]: e["data"] for e in ev if e["type"] == "ddl_column"}
    assert cols["K"]["nullable"] and cols["K"]["nullability_basis"] == "dialect_default"
    assert not cols["N"]["nullable"] and cols["N"]["nullability_basis"] == "declared"


def test_typed_null_boolean_exact_decimal_full_roundtrip(tmp_path):
    app, k = prepared(
        tmp_path,
        "CREATE TABLE T(A NUMBER, B NUMBER, C NUMBER, D NUMBER); UPDATE T SET A=NULL, B=FALSE, C=12345678901234567890.12345678901234567890, D='';",
    )
    expected = {
        "T.A": {"type": "null", "value": None},
        "T.B": {"type": "boolean", "value": False},
        "T.C": {"type": "number", "value": "12345678901234567890.12345678901234567890"},
        "T.D": {"type": "null", "value": None, "source_literal": "empty_string"},
    }
    assert {
        f["entity_name"]: f["property_value"] for f in facts(k, "assigned_value")
    } == expected
    base = facts(k, "assigned_value")[0]
    for invalid in (
        None,
        "",
        {"type": "boolean", "value": 0},
        {"type": "number", "value": 1.2},
    ):
        candidate = {
            **copy.deepcopy(base),
            "candidate_id": "invalid",
            "property_value": invalid,
        }
        with pytest.raises(DomainError):
            k.import_candidates([candidate], "manual:test")
    k.review_many(
        [c["id"] for c in k.candidates()],
        "confirmed",
        reason="Exact SQL literals checked",
    )
    k.merge()
    snap = Exports(app).snapshot()
    exported = json.loads(
        (app.root / "artifacts" / snap["id"] / "dsl.json").read_text(encoding="utf-8")
    )
    actual = {
        entity["name"]: fact["property_value"]
        for entity in exported["entities"]
        for fact in entity["facts"]
        if fact["property_name"] == "assigned_value"
    }
    assert actual == expected
