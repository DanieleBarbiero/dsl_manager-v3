"""Independent semantic acceptance. COV/BIZ labels map to prompt v1.3."""

import copy
import json
import os
from pathlib import Path

import pytest
from dslm3.ai import AI
from dslm3.common import DomainError, digest, uid, dump_json
from dslm3.deterministic import inventory, planned, coverage, require_complete
from dslm3.exports import Exports
from dslm3.knowledge import Knowledge, POLICIES
from dslm3.parsers.base import ParseResult, chunks
from dslm3.parsers.sql import parse_sql
from dslm3.resolution import Resolver
from dslm3.service import Application

FIXTURES = Path(__file__).parent / "fixtures/deterministic"


def audit(name, expected, actual):
    """Optional acceptance artifacts contain observations after assertions pass."""
    if directory := os.environ.get("DSLM3_ACCEPTANCE_DETAILS"):
        dump_json(
            Path(directory) / (name + ".json"),
            {
                "status": "passed",
                "expected": expected,
                "actual": actual,
                "origin": "executed_pytest_assertions",
            },
        )


def evidence(sql):
    result = parse_sql(sql, "oracle")
    return [
        {**e, "id": uid("EV", [i, e]), "revision_id": "REV_test", "path": "test.sql"}
        for i, e in enumerate(result.evidence)
    ]


def prepared(tmp_path, sql, name="test.sql"):
    app = Application(tmp_path)
    app.store.configure({"sql_dialect": "oracle"})
    app.ingest(name, sql.encode("utf-8"))
    result = app.parse_all()
    assert result["errors"] == result["partial"] == 0, result
    k = Knowledge(app)
    result = k.derive()
    assert result["coverage"]["complete"], result["coverage"]
    return app, k


def materialized(rows):
    return {
        r["id"]: {"payload": r["payload"], "state": "pending"} for r in planned(rows)
    }


def facts(k, prop=None):
    return [
        c["payload"]
        for c in k.candidates()
        if c["current_derivation"]
        and c["current_revision"]
        and c["current_parse"]
        and c["record_type"] == "candidate_fact"
        and (prop is None or c["payload"]["property_name"] == prop)
    ]


def test_cov_01_missing_fk_retains_declaration():
    rows = inventory(
        evidence("CREATE TABLE A(ID NUMBER, B_ID NUMBER REFERENCES B(ID));")
    )
    report = require_complete(coverage(rows, materialized(rows)))
    fk = next(r for r in report["evidence"] if r["subtype"] == "foreign_key")
    assert fk["outcome"] == "partial"
    declaration, relation = fk["components"]
    assert declaration["outcome"] == "materialized_deterministically"
    assert relation["outcome"] == "unresolved"
    assert relation["applicability"] == "blocked_by_resolution"
    assert relation["resolution"]["prerequisites"][1]["basis_evidence_ids"] == []
    assert relation["resolution"]["raw_target"] == "B"
    assert not relation["candidate_ids"]
    assert report["counts"]["due_missing_components"] == 0
    audit(
        "COV-01",
        {"relation": "unresolved", "declaration": "derived", "due_missing": 0},
        report,
    )


def test_cov_02_missing_due_result_is_failure():
    rows = inventory(
        evidence(
            "CREATE TABLE B(ID NUMBER PRIMARY KEY); CREATE TABLE A(B_ID NUMBER REFERENCES B(ID));"
        )
    )
    actual = materialized(rows)
    assert (
        require_complete(coverage(rows, actual))["counts"][
            "blocked_unresolved_components"
        ]
        == 0
    )
    relation = next(
        r for r in planned(rows) if r["payload"].get("relation_type") == "foreign_key"
    )
    del actual[relation["id"]]
    report = coverage(rows, actual)
    assert report["counts"]["due_missing_components"] == 1
    with pytest.raises(DomainError, match="Copertura incompleta"):
        require_complete(report)
    audit(
        "COV-02",
        {"probe": "omit required FK relation", "due_missing": 1, "gate_rejects": True},
        report,
    )


def test_cov_03_ambiguous_and_inconsistent():
    ambiguous = evidence(
        "CREATE TABLE S1.B(ID NUMBER); CREATE TABLE S2.B(ID NUMBER); CREATE TABLE A(X NUMBER REFERENCES B(ID));"
    )
    resolution = Resolver(ambiguous).resolve("B")
    assert resolution["status"] == "ambiguous"
    assert resolution["alternatives"] == ["S1.B", "S2.B"]
    assert len(resolution["basis_evidence_ids"]) == 2
    rows = inventory(
        evidence(
            "CREATE TABLE B(ID NUMBER, X NUMBER); CREATE TABLE A(X NUMBER, FOREIGN KEY (X) REFERENCES B(ID,X));"
        )
    )
    c = next(
        c for r in rows for c in r["components"] if c["key"] == "resolved_relation"
    )
    assert c["resolution"]["status"] == "inconsistent"
    assert c["reason_code"] == "foreign_key_arity"
    assert not c["expected"]
    audit(
        "COV-03",
        {
            "ambiguous_alternatives": ["S1.B", "S2.B"],
            "incompatible_reason": "foreign_key_arity",
        },
        {"ambiguous": resolution, "inconsistent": c},
    )


def test_cov_04_composite_counts_and_cov_05_unexpected_resolution(monkeypatch):
    rows = inventory(
        evidence(
            "CREATE TABLE T(A NUMBER, B NUMBER, C NUMBER); UPDATE T SET A=1,B=2,C=3;"
        )
    )
    statement = next(r for r in rows if r["type"] == "sql_statement")
    assert [c["key"] for c in statement["components"]] == [
        "statement",
        "assignment:0",
        "assignment:1",
        "assignment:2",
    ]
    actual = materialized(rows)
    del actual[statement["components"][2]["expected"][0]["id"]]
    c = statement["components"][3]
    c.update(
        applicability="blocked_by_resolution",
        resolution={"status": "unresolved"},
        expected=[],
    )
    report = coverage(rows, actual)
    assert report["counts"]["due_missing_components"] == 1
    assert report["counts"]["blocked_unresolved_components"] == 1
    assert (
        next(r for r in report["evidence"] if r["type"] == "sql_statement")["outcome"]
        == "partial"
    )
    audit(
        "COV-04",
        {
            "due_missing": 1,
            "blocked_unresolved": 1,
            "statement": "partial",
            "probe": "controlled omission and resolution block",
        },
        report,
    )
    correct = inventory(
        evidence(
            "CREATE TABLE B(ID NUMBER); CREATE TABLE A(X NUMBER REFERENCES B(ID));"
        )
    )
    report = coverage(correct, materialized(correct))
    key = next(
        (r["evidence_id"], c["key"])
        for r in report["evidence"]
        for c in r["components"]
        if c["key"] == "resolved_relation"
    )
    with pytest.raises(DomainError, match="attese"):
        require_complete(report, {key: "unresolved"})
    broken = copy.deepcopy(report)
    for row in broken["evidence"]:
        for c in row["components"]:
            if (row["evidence_id"], c["key"]) == key:
                c["resolution"]["status"] = "unresolved"
    with pytest.raises(DomainError, match="attese"):
        require_complete(broken, {key: "resolved"})
    audit(
        "COV-05",
        {"positive_resolution": "resolved", "unexpected_unresolved_rejected": True},
        {"positive": report, "controlled_defect": broken},
    )

    def bug(*args, **kwargs):
        raise RuntimeError("controlled programming error")

    monkeypatch.setattr(Resolver, "foreign_key", bug)
    with pytest.raises(RuntimeError, match="programming"):
        inventory(evidence("CREATE TABLE A(X NUMBER REFERENCES B(ID));"))


def test_cov_06_dependency_lifecycle_cache_and_history(tmp_path):
    app, k = prepared(tmp_path, "CREATE TABLE A(X NUMBER REFERENCES B(ID));")
    assert app.coverage()["counts"]["blocked_unresolved_components"] == 1
    stages = [{"stage": "absent", "coverage": app.coverage()}]
    app.ingest("target.sql", b"CREATE TABLE B(ID NUMBER PRIMARY KEY);")
    app.parse_all()
    result = k.derive()
    app.store.configure({"automatic_policies": list(POLICIES.values())})
    k.auto_review()
    k.merge()
    relation = next(
        c for c in k.candidates() if c["payload"].get("relation_type") == "foreign_key"
    )
    old_reviews = app.store.rows("SELECT * FROM reviews")
    assert any(o["payload"].get("relation_type") == "foreign_key" for o in k.objects())
    stages.append({"stage": "added", "coverage": app.coverage(), "relation": relation})
    app.ingest("target.sql", b"CREATE TABLE B(OTHER NUMBER PRIMARY KEY);")
    assert not any(
        o["payload"].get("relation_type") == "foreign_key" for o in k.objects()
    )
    app.parse_all()
    k.derive()
    assert app.coverage()["counts"]["blocked_unresolved_components"] == 1
    stages.append({"stage": "modified", "coverage": app.coverage()})
    (app.root / "corpus/target.sql").unlink()
    app.scan()
    k.derive()
    assert app.coverage()["counts"]["blocked_unresolved_components"] == 1
    stages.append({"stage": "removed", "coverage": app.coverage()})
    app.ingest("target.sql", b"CREATE TABLE B(ID NUMBER PRIMARY KEY);")
    parsed = app.parse_all()
    again = k.derive()
    assert all(r["cached"] for r in parsed["results"])
    assert set(again["candidate_ids"]) == set(result["candidate_ids"])
    assert (
        next(c for c in k.candidates() if c["id"] == relation["id"])["state"]
        == "confirmed"
    )
    assert all(r in app.store.rows("SELECT * FROM reviews") for r in old_reviews)
    assert any(o["payload"].get("relation_type") == "foreign_key" for o in k.objects())
    stages.append(
        {
            "stage": "restored",
            "coverage": app.coverage(),
            "parse": parsed,
            "review_history": app.store.rows("SELECT * FROM reviews"),
        }
    )
    audit(
        "COV-06",
        {
            "resolution_sequence": [
                "unresolved",
                "resolved",
                "unresolved",
                "unresolved",
                "resolved",
            ],
            "history_retained": True,
            "cache_reused": True,
        },
        stages,
    )


def test_cov_07_governance_and_cov_08_unknown_irrelevant(tmp_path):
    app, k = prepared(tmp_path, "CREATE TABLE T(X NUMBER); UPDATE T SET X=2;")
    before = k.derive()["candidate_ids"]
    for state in ["pending", "confirmed", "rejected"]:
        k.review_many(before, state, reason="COV-07")
        report = app.coverage(check=True)
        assert report["counts"]["due_missing_components"] == 0
        selected = AI(app).select("technical_extraction")
        assert not any(
            i["type"] == "sql_statement" and i["outcome"] == "included"
            for i in selected["items"]
        )
        if state != "confirmed":
            assert k.merge()["created"] == 0
        audit(
            "COV-07-" + state,
            {"governance": state, "due_missing": 0, "technical_update_excluded": True},
            {"coverage": report, "selection": selected},
        )
    app.ingest("irrelevant.txt", b"Free text.")
    app.parse_all()
    assert set(k.derive()["candidate_ids"]) == set(before)
    synthetic = {**app.evidence()[0], "type": "new_unknown", "id": "unknown"}
    report = coverage(inventory([synthetic]), {})
    assert report["counts"]["unclassified_evidence_count"] == 1
    with pytest.raises(DomainError):
        require_complete(report)
    audit(
        "COV-08",
        {
            "unclassified": 1,
            "gate_rejects": True,
            "irrelevant_preserves_candidates": True,
        },
        report,
    )
    rows = inventory(evidence("ALTER TABLE T DROP COLUMN X;"))
    assert coverage(rows, {})["counts"]["unsupported_components"] == 1


def assert_business(k, allowed=None, boundary="0", not_null=True):
    expected = json.loads((FIXTURES / "expected_business.json").read_text())
    constraints = [
        f
        for f in facts(k, "constraint")
        if f["property_value"]["constraint_type"] == "check"
    ]
    assert {f["entity_name"] for f in constraints} == set(expected["constraints"])
    enum = next(
        f["property_value"]["expression_ast"]
        for f in constraints
        if f["entity_name"].endswith("_STATO")
    )
    assert enum["node"] == "in"
    assert enum["args"]["this"] == {"node": "column", "name": "STATO"}
    assert enum["args"]["expressions"] == [
        {"node": "literal", "type": "string", "value": v}
        for v in (allowed or expected["allowed_values"])
    ]
    number = next(
        f["property_value"]["expression_ast"]
        for f in constraints
        if f["entity_name"].endswith("_TOTALE")
    )
    assert number["node"] == expected["total_operator"]
    assert number["args"]["expression"] == {
        **expected["total_boundary"],
        "value": boundary,
    }
    cols = {
        f["entity_name"].split(".")[-1]: f["attributes"] for f in facts(k, "data_type")
    }
    assert cols["TOTALE"]["datatype"] == "NUMBER(12, 2)"
    for col in expected["explicit_not_null"]:
        assert cols[col]["nullable"] == (not not_null)
        assert cols[col]["nullability_declaration"] == (
            "not_null" if not_null else "unspecified"
        )
    return constraints


def test_biz_01_02_05_06_08_business_cycle(tmp_path):
    source = (FIXTURES / "business.sql").read_text()
    app, k = prepared(tmp_path, source)
    assert_business(k)
    assert {c["state"] for c in k.candidates()} == {"pending"}
    assert k.merge()["created"] == 0
    assert not app.store.rows("SELECT * FROM batches WHERE origin LIKE 'ai%'")
    k.review_many(
        [c["id"] for c in k.candidates()], "confirmed", reason="BIZ-08 source checked"
    )
    k.merge()
    before = Exports(app).snapshot()
    reopened = Application(tmp_path)
    assert_business(Knowledge(reopened))
    for fmt in ["json", "yaml", "md"]:
        output = app.root / "artifacts" / before["id"] / ("dsl." + fmt)
        assert output.exists() and "BOZZA" in output.read_text(encoding="utf-8")
    for supports in before["content"]["traceability"]["facts"].values():
        for support in supports:
            assert support["evidence_text"] in source
            assert support["evidence_locator"]["line_start"] >= 1
    changed = (
        source.replace("'ANNULLATO'", "'ANNULLATO', 'SOSPESO'")
        .replace("TOTALE >= 0", "TOTALE >= 10")
        .replace(" NOT NULL", "")
    )
    app.ingest("test.sql", changed.encode())
    app.parse_all()
    k.derive()
    assert_business(k, ["BOZZA", "CONFERMATO", "ANNULLATO", "SOSPESO"], "10", False)
    assert not k.objects()
    k.review_many(
        [c["id"] for c in k.candidates() if c["current_revision"]],
        "confirmed",
        reason="BIZ-05",
    )
    k.merge()
    after = Exports(app).snapshot()
    assert Exports(app).diff(before["id"], after["id"])["changes"]
    assert any(c["current_revision"] == 0 for c in k.candidates())
    audit(
        "BIZ-01-02-05-06-08",
        {
            "allowed_values_after_change": [
                "BOZZA",
                "CONFERMATO",
                "ANNULLATO",
                "SOSPESO",
            ],
            "boundary_after_change": "10",
            "explicit_not_null_removed": True,
            "ai_imports": 0,
        },
        {
            "before_snapshot": before,
            "after_snapshot": after,
            "coverage": app.coverage(),
            "candidates": k.candidates(),
            "diff": Exports(app).diff(before["id"], after["id"]),
        },
    )


def test_biz_03_04_07_decrement_and_names(tmp_path):
    source = (FIXTURES / "decrement.sql").read_text()
    app, k = prepared(tmp_path / "named", source)
    rhs = facts(k, "assignment_expression")
    assert len(rhs) == 1 and rhs[0]["entity_name"] == "ARTICOLO_PROVA.QTA_DISPONIBILE"
    assert rhs[0]["property_value"] == "QTA_DISPONIBILE - 1"
    assert ":P_ID_ARTICOLO" in facts(k, "row_selection_expression")[0]["property_value"]
    assert not any(
        "P_ID_ARTICOLO" in c["payload"].get("target_entity", "") for c in k.candidates()
    )
    assert not any(f["fact_type"] in {"domain", "business_rule"} for f in facts(k))
    assert {f["property_name"] for f in facts(k)} == {
        "object_type",
        "data_type",
        "constraint",
        "statement_structure",
        "assignment_expression",
        "row_selection_expression",
    }
    assert any(
        i["type"] == "sql_statement" and i["outcome"] == "included"
        for i in AI(app).select("domain_interpretation")["items"]
    )
    assert all(
        i["outcome"] == "excluded"
        for i in AI(app).select("technical_extraction")["items"]
        if i["type"] == "sql_statement"
    )
    mapping = {"ARTICOLO_PROVA": "T", "QTA_DISPONIBILE": "X", "ID_ARTICOLO": "I"}
    renamed = source
    for old, new in mapping.items():
        renamed = renamed.replace(old, new)
    _, k2 = prepared(tmp_path / "renamed", renamed)
    assert facts(k2, "assignment_expression")[0]["property_value"] == "X - 1"
    assert {f["property_name"] for f in facts(k2)} == {
        f["property_name"] for f in facts(k)
    }
    assert not any(f["fact_type"] in {"domain", "business_rule"} for f in facts(k2))
    audit(
        "BIZ-03-04-07",
        {"rhs": "QTA_DISPONIBILE - 1", "renamed_rhs": "X - 1", "domain_inferences": 0},
        {
            "facts": facts(k),
            "renamed_facts": facts(k2),
            "technical": AI(app).select("technical_extraction"),
            "domain": AI(app).select("domain_interpretation"),
        },
    )


def test_biz_04_positive_table_column_constraint_rename(tmp_path):
    source = (FIXTURES / "business.sql").read_text()
    mapping = {
        "CK_ORDINE_PROVA_STATO": "C1",
        "CK_ORDINE_PROVA_TOTALE": "C2",
        "ORDINE_PROVA": "T",
        "STATO": "X",
        "TOTALE": "Y",
        "ID": "K",
    }
    renamed = source
    for old, new in mapping.items():
        renamed = renamed.replace(old, new)
    _, k = prepared(tmp_path, renamed)
    expected = json.loads((FIXTURES / "expected_business.json").read_text())
    checks = {
        f["entity_name"]: f["property_value"]["expression_ast"]
        for f in facts(k, "constraint")
        if f["property_value"]["constraint_type"] == "check"
    }
    assert set(checks) == {"T.C1", "T.C2"}
    assert checks["T.C1"] == {
        "node": "in",
        "args": {
            "this": {"node": "column", "name": "X"},
            "expressions": [
                {"node": "literal", "type": "string", "value": value}
                for value in expected["allowed_values"]
            ],
        },
    }
    assert checks["T.C2"] == {
        "node": "gte",
        "args": {
            "this": {"node": "column", "name": "Y"},
            "expression": expected["total_boundary"],
        },
    }
    cols = {f["entity_name"]: f["attributes"] for f in facts(k, "data_type")}
    assert not cols["T.X"]["nullable"] and not cols["T.Y"]["nullable"]
    assert cols["T.Y"]["datatype"] == "NUMBER(12, 2)"
    assert {f["property_name"] for f in facts(k)} == {
        "object_type",
        "data_type",
        "constraint",
    }
    audit(
        "BIZ-04-positive",
        {"mapping": mapping, "structure": expected},
        {"facts": facts(k), "coverage": k.app.coverage()},
    )


@pytest.mark.parametrize(
    "rhs,expected",
    [
        ("NULL", {"type": "null", "value": None}),
        ("''", {"type": "null", "value": None, "source_literal": "empty_string"}),
        ("TRUE", {"type": "boolean", "value": True}),
        (
            "-123.456789012345678901",
            {"type": "number", "value": "-123.456789012345678901"},
        ),
        ("'001'", {"type": "string", "value": "001"}),
        ("('x')", {"type": "string", "value": "x"}),
    ],
)
def test_update_typed_literals(rhs, expected):
    statement = next(
        e for e in evidence(f"UPDATE T SET X={rhs};") if e["type"] == "sql_statement"
    )
    part = statement["data"]["components"][0]
    assert part["property"] == "assigned_value" and part["value"] == expected
    assert not statement["data"]["has_where"]


def test_update_expression_context_and_real_conflicts(tmp_path):
    sql = "CREATE TABLE T(ID NUMBER, X NUMBER); CREATE PROCEDURE P(ID NUMBER) AS BEGIN UPDATE T a SET a.X=ABS(-1) WHERE a.ID=ID; UPDATE T SET X=2; UPDATE T SET X=2; END; /\nCREATE PROCEDURE Q AS BEGIN UPDATE T SET X=3; END;"
    app, k = prepared(tmp_path, sql)
    assignments = facts(k, "assignment_expression") + facts(k, "assigned_value")
    assert len(assignments) == 4
    assert len({f["attributes"]["context"]["statement_id"] for f in assignments}) == 4
    app.store.configure({"automatic_policies": list(POLICIES.values())})
    k.auto_review()
    k.merge()
    assert not k.conflicts()
    c = copy.deepcopy(assignments[0])
    c.update(candidate_id="conflicting", property_value="ABS(-2)")
    imported = k.import_candidates([c], "manual:test")
    k.review_many(imported["candidate_ids"], "confirmed", reason="incompatibility test")
    k.merge()
    assert len(k.conflicts()) == 1


def test_other_sql_shapes_ddl_and_quoted_resolver():
    source = """CREATE TABLE "S"."Mixed"("Id" NUMBER PRIMARY KEY, "id" VARCHAR2(20) DEFAULT 'NULL', V NUMBER DEFAULT ABS(-1), CONSTRAINT U UNIQUE("Id", "id"), CHECK(V >= 0), CHECK(V < 100));
    CREATE UNIQUE INDEX IX ON "S"."Mixed" (V DESC, LOWER("id"));
    ALTER TABLE "S"."Mixed" ADD CONSTRAINT C CHECK (V <> 2);
    INSERT INTO "S"."Mixed"("Id", V) VALUES(1,2),(2,3);
    DELETE FROM "S"."Mixed" WHERE V > 1;
    SELECT V AS val FROM "S"."Mixed";
    MERGE INTO "S"."Mixed" a USING SRC b ON a."Id"=b.ID WHEN MATCHED THEN UPDATE SET V=4 WHEN NOT MATCHED THEN INSERT("Id", V) VALUES(b.ID, 5);"""
    ev = evidence(source)
    assert not any(e["type"] == "sql_unparsed" for e in ev)
    checks = [
        e
        for e in ev
        if e["type"] == "ddl_constraint" and e["data"]["constraint_type"] == "check"
    ]
    assert len(checks) == 3 and len({e["data"]["constraint_id"] for e in checks}) == 3
    assert Resolver(ev).resolve('"S"."Mixed"."Id"', "column")["status"] == "resolved"
    assert Resolver(ev).resolve('"S"."Mixed".ID', "column")["status"] == "unresolved"
    stmts = {
        e["data"]["statement_type"]: e["data"]
        for e in ev
        if e["type"] == "sql_statement"
    }
    assert len(stmts["insert"]["components"]) == 4
    assert stmts["delete"]["has_where"]
    assert stmts["select"]["components"][0]["value"]["node"] == "alias"
    merge = stmts["merge"]["components"]
    assert {c.get("branch") for c in merge if c["property"] == "assigned_value"} == {
        0,
        1,
    }
    index = next(e["data"] for e in ev if e["type"] == "ddl_index")
    assert index["unique"] and index["table"] == '"S"."Mixed"'


@pytest.mark.parametrize(
    "text",
    [
        "",
        " \n\n\t  ",
        "# A\n\ntext\n\n### C\nlast",
        "# A\n```sql\n# not heading\n```\n## B\nlast",
        "x" * 250,
        "\r\n# Accenti à 漢字\r\n\t",
    ],
)
def test_chunk_exact_whitespace_fences(text):
    r = ParseResult("test")
    chunks(r, text, size=17, minimum=3)
    assert "".join(e["text"] for e in r.evidence) == text
    for e in r.evidence:
        loc = e["locator"]
        assert len(e["text"]) <= 17
        assert text[loc["char_start"] : loc["char_end"]] == e["text"]
        assert "not heading" not in loc["heading_path"]
        assert loc["normalized_sha256"] == digest(text.encode())
    rerun = ParseResult("test")
    chunks(rerun, text, size=17, minimum=3)
    assert r.evidence == rerun.evidence


def test_forms_resolution_modes_and_namespace(tmp_path):
    app, k = prepared(
        tmp_path, "CREATE TABLE T(ID NUMBER); CREATE PROCEDURE P AS BEGIN NULL; END;"
    )
    app.ingest(
        "f.xml",
        b"""<f:form xmlns:f="urn:forms" name="F"><f:block name="A" table="T"><f:field name="ID" column="ID" mode="read"/><f:button name="B" operation="P"/></f:block><f:block name="B" table="T"><f:field name="ID" column="ID" mode="write"/><f:item name="BAD" column="MISSING"/><f:item name="C" column="ID" mode="write" readonly="true"/><f:item name="BUTTON" itemtype="PushButton" operation="MISSING"/></f:block></f:form>""",
    )
    app.parse_all()
    k.derive()
    payloads = [c["payload"] for c in k.candidates()]
    assert {"F.A.ID", "F.B.ID"} <= {c.get("entity_name") for c in payloads}
    relations = {
        (c.get("source_entity"), c.get("relation_type"), c.get("target_entity"))
        for c in payloads
    }
    assert ("F.A.ID", "reads_from", "T.ID") in relations
    assert ("F.B.ID", "writes_to", "T.ID") in relations
    assert ("F.A.B", "calls", "P") in relations
    assert not any(x[0] == "F.B.BAD" for x in relations)
    assert ("F.B.C", "writes_to", "T.ID") not in relations
    report = app.coverage(check=True)
    assert report["counts"]["blocked_inconsistent_components"] == 1
    assert report["counts"]["blocked_unresolved_components"] == 2
    for r in report["evidence"]:
        if r["type"].startswith("xml_"):
            assert r["locator"]["xpath"]
