import codecs
import copy
import json
from pathlib import Path
import subprocess
import sys
import types

import pytest
from dslm3.ai import AI
from dslm3.common import DomainError, digest
from dslm3.knowledge import Knowledge
from dslm3.parsers.documents import decode, parse_document
from dslm3.parsers.sql import parse_sql
from dslm3.service import Application
from test_deterministic_core import prepared, facts, evidence
from dslm3.resolution import Resolver


@pytest.mark.parametrize(
    "encoding,newline",
    [
        ("utf-8", "\n"),
        ("utf-8", "\r\n"),
        ("utf-8-sig", "\r\n"),
        ("utf-16", "\n"),
        ("utf-16-be", "\r\n"),
    ],
)
def test_windows_bytes_bom_paths_and_locations(tmp_path, encoding, newline):
    text = '-- città 日本\nCREATE TABLE "Tà" ("X" VARCHAR2(40));\nUPDATE "Tà" SET "X"=\'caffè 日本\';'.replace(
        "\n", newline
    )
    data = text.encode(encoding)
    if encoding == "utf-16-be":
        data = codecs.BOM_UTF16_BE + data
    app = Application(tmp_path / "spazi e città")
    app.store.configure({"sql_dialect": "oracle"})
    rev = app.ingest("cartella con spazi/città.sql", data)
    parsed = app.parse_all()
    assert parsed["errors"] == 0, parsed
    decoded, _ = decode(data)
    for e in app.evidence():
        assert (
            decoded[e["locator"]["char_start"] : e["locator"]["char_end"]] == e["text"]
        )
    stored = app.store.one(
        "SELECT object_path,sha256 FROM revisions WHERE id=?", (rev["revision_id"],)
    )
    assert (app.root / stored["object_path"]).read_bytes() == data
    assert stored["sha256"] == digest(data)
    k = Knowledge(app)
    k.derive()
    assert facts(k, "assigned_value")[0]["property_value"] == {
        "type": "string",
        "value": "caffè 日本",
    }
    first = k.derive()["candidate_ids"]
    assert all(x["cached"] for x in app.parse_all()["results"])
    assert k.derive()["candidate_ids"] == first
    # Native Windows would reject the rename if worker/SQLite handles leaked.
    target = app.root.parent / "rinominato città"
    app.root.rename(target)
    assert (
        Application(target).store.one("PRAGMA integrity_check")["integrity_check"]
        == "ok"
    )


def test_chunk_configuration_all_paths_and_cache(tmp_path):
    app = Application(tmp_path / "work")
    app.store.configure({"chunk_chars": 12, "chunk_min_chars": 2})
    inputs = {
        "a.txt": "  \n# H\n\n" + "abc " * 30,
        "a.xml": "<root>" + "abc " * 30 + "</root>",
        "a.json": json.dumps({"v": "abc " * 30}),
        "a.eml": "Subject: test\nContent-Type: text/plain\n\n" + "abc " * 30,
    }
    for name, text in inputs.items():
        app.ingest(name, text.encode())
    assert app.parse_all()["errors"] == 0
    before = {e["id"] for e in app.evidence()}
    assert all(len(e["text"]) <= 12 for e in app.evidence() if e["kind"] == "chunk")
    app.store.configure({"chunk_chars": 30, "chunk_strategy": "paragraph"})
    assert not any(r.get("cached") for r in app.parse_all()["results"])
    assert before != {e["id"] for e in app.evidence()}
    for values in [
        {"chunk_chars": 0},
        {"chunk_min_chars": 100},
        {"chunk_strategy": "ignored"},
        {"chunk_unknown": True},
    ]:
        with pytest.raises(DomainError):
            app.store.configure(values)
    with pytest.raises(DomainError):
        parse_document(app.root / "corpus/a.xml", "R", {"chunk_unknown": 1})


def test_rule_only_change_obsoletes_old_outputs_without_review_loss(
    tmp_path, monkeypatch
):
    app, k = prepared(tmp_path, "CREATE TABLE T(X NUMBER);")
    original = k.derive()["candidate_ids"]
    k.review_many(original, "confirmed", reason="rule upgrade fixture")
    k.merge()
    old = copy.deepcopy(k.objects())
    monkeypatch.setattr("dslm3.deterministic.RULE_VERSION", "4.1-test")
    upgraded = k.derive()
    assert set(upgraded["candidate_ids"]).isdisjoint(original)
    assert not k.objects()
    assert all(
        c["state"] == "pending" for c in k.candidates() if c["current_derivation"]
    )
    assert all(c["state"] == "confirmed" for c in k.candidates() if c["id"] in original)
    monkeypatch.setattr("dslm3.deterministic.RULE_VERSION", "4.0")
    assert k.derive()["candidate_ids"] == original
    assert k.objects() == old


def test_schema2_upgrade_preserves_history(tmp_path, monkeypatch):
    root = Path(__file__).parents[1]
    baseline = "a7117e061b393123e3b7b2ec22bf171687756447"

    def load(name):
        source = subprocess.run(
            ["git", "-C", str(root), "show", baseline + ":src/dslm3/" + name + ".py"],
            capture_output=True,
            check=True,
        ).stdout
        module = types.ModuleType("baseline_" + name)
        monkeypatch.setitem(sys.modules, module.__name__, module)
        exec(compile(source, baseline + "/" + name, "exec"), module.__dict__)
        return module

    storage, service, knowledge = [load(n) for n in ("storage", "service", "knowledge")]
    service.Store = storage.Store
    old = service.Application(tmp_path)
    old.ingest("a.sql", b"CREATE TABLE A(ID NUMBER);")
    assert old.parse_all()["errors"] == 0
    oldk = knowledge.Knowledge(old)
    oldk.derive()
    old.store.configure({"automatic_policies": list(knowledge.POLICIES.values())})
    oldk.auto_review()
    oldk.merge()
    decisions = old.store.rows("SELECT * FROM reviews")
    old_ids = {c["id"] for c in oldk.candidates()}
    assert old.store.one("SELECT MAX(version) AS v FROM schema_history")["v"] == 2
    app = Application(tmp_path)
    k = Knowledge(app)
    assert app.store.one("SELECT MAX(version) AS v FROM schema_history")["v"] == 3
    assert app.store.rows("SELECT * FROM reviews") == decisions
    assert not k.objects()
    assert app.parse_all()["errors"] == 0
    new = k.derive()
    assert set(new["candidate_ids"]).isdisjoint(old_ids)
    assert old_ids <= {c["id"] for c in k.candidates()}
    assert len(k.objects(effective=False)) == 2
    assert app.store.one("PRAGMA integrity_check")["integrity_check"] == "ok"


def test_partial_ai_remains_visible_and_package_preserves_coverage(tmp_path):
    app, k = prepared(tmp_path, "UPDATE T SET (A,B)=(1,2) WHERE ID=1;")
    report = app.coverage()
    stmt = next(r for r in report["evidence"] if r["type"] == "sql_statement")
    assert stmt["outcome"] == "partial"
    ai = AI(app)
    plan = ai.select("technical_extraction")
    selected = next(i for i in plan["items"] if i["evidence_id"] == stmt["evidence_id"])
    assert selected["outcome"] == "included"
    package = ai.package(plan["id"])
    manifest = json.loads(
        (app.root / package["directory"] / "source_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest[0]["deterministic_coverage"]["components"]
    c = next(
        c
        for c in k.candidates()
        if c["payload"].get("property_name") == "row_selection_expression"
    )
    k.review(c["id"], "rejected", reason="Do not bypass governance")
    # Refresh package after governance changed; attempting a duplicate is rejected.
    pkg = ai.package(ai.select("technical_extraction")["id"])
    p = {**c["payload"], "candidate_id": "duplicate", "fact_type": "technical"}
    with pytest.raises(DomainError, match="già derivata"):
        ai.import_response(pkg["id"], json.dumps(p))


def test_log_json_identical_occurrences_retry_and_no_conflict(tmp_path):
    app = Application(tmp_path)
    line = '{"time":"2026-09-29T10:00:00Z","level":"INFO","component":"C","message":"repeat"}\n'
    app.ingest("x.log", (line + line + "unknown line\n").encode())
    assert app.parse_all()["errors"] == 0
    k = Knowledge(app)
    initial = k.derive()
    events = facts(k, "occurrence")
    assert len(events) == 2 and len({e["entity_name"] for e in events}) == 2
    assert {e["property_value"]["occurrence_line"] for e in events} == {1, 2}
    k.review_many(initial["candidate_ids"], "confirmed", reason="occurrence test")
    k.merge()
    assert not k.conflicts()
    assert k.derive()["candidate_ids"] == initial["candidate_ids"]
    assert app.coverage()["counts"]["unsupported_components"] == 1


def test_call_overload_and_dialect_quoting():
    ev = evidence('CREATE PROCEDURE "p" AS BEGIN NULL; END;\n/\nCALL "p"();')
    assert Resolver(ev).resolve('"p"', "code_unit")["status"] == "resolved"
    assert Resolver(ev).resolve("P", "code_unit")["status"] == "unresolved"
    assert any(
        e["type"] == "sql_dependency" and e["data"]["relation_type"] == "calls"
        for e in ev
    )
    overload = evidence(
        "CREATE PACKAGE P AS PROCEDURE F(X NUMBER); PROCEDURE F(X VARCHAR2); END;"
    )
    assert Resolver(overload).resolve("P.F", "code_unit")["status"] == "ambiguous"
    pg = parse_sql(
        "CREATE TABLE foo(id INTEGER, \"Id\" TEXT); UPDATE foo SET id='';", "postgres"
    )
    assert next(e for e in pg.evidence if e["type"] == "sql_statement")["data"][
        "components"
    ][0]["value"] == {"type": "string", "value": ""}
    rows = [{**e, "id": str(i), "revision_id": "R"} for i, e in enumerate(pg.evidence)]
    assert Resolver(rows).resolve('"foo"."id"', "column")["status"] == "resolved"
    assert Resolver(rows).resolve('foo."ID"', "column")["status"] == "unresolved"


def test_fk_inferred_target_key_order_and_insert_select():
    ev = evidence(
        "CREATE TABLE B(X NUMBER,Y NUMBER,PRIMARY KEY(Y,X)); CREATE TABLE A(X NUMBER,Y NUMBER,FOREIGN KEY(X,Y) REFERENCES B); INSERT INTO A(X,Y) SELECT X,Y FROM B;"
    )
    fk = next(
        e["data"]
        for e in ev
        if e["type"] == "ddl_constraint"
        and e["data"]["constraint_type"] == "foreign_key"
    )
    res = Resolver(ev).foreign_key(fk)
    assert (
        res["status"] == "resolved"
        and res["columns"] == ["X", "Y"]
        and res["target_columns"] == ["Y", "X"]
    )
    stmt = next(e["data"] for e in ev if e["type"] == "sql_statement")
    assert [(c["entity"], c["property"], c["value"]) for c in stmt["components"]] == [
        ("A.X", "assignment_expression", "X"),
        ("A.Y", "assignment_expression", "Y"),
    ]


def test_code_provenance_without_git_hashes_installed_files(tmp_path, monkeypatch):
    from dslm3 import provenance

    package = tmp_path / "installed/dslm3"
    package.mkdir(parents=True)
    module = package / "provenance.py"
    module.write_bytes(b"source snapshot one")
    monkeypatch.setattr(provenance, "__file__", str(module))
    first = provenance.code_provenance()
    assert first["head"] is None and first["source_file_count"] == 1
    module.write_bytes(b"source snapshot two")
    assert (
        provenance.code_provenance()["source_snapshot_sha256"]
        != first["source_snapshot_sha256"]
    )


def test_call_package_body_only_and_spec_precedence():
    body = "CREATE PACKAGE BODY P AS PROCEDURE F IS BEGIN NULL; END F; END P;"
    ev = evidence(body)
    result = Resolver(ev).resolve("P.F", "code_unit")
    assert result["status"] == "resolved" and result["canonical_target"] == "P::BODY.F"
    assert result["reason_code"] == "package_body_declaration"
    both = evidence("CREATE PACKAGE P AS PROCEDURE F; END P;\n/\n" + body)
    result = Resolver(both).resolve("P.F", "code_unit")
    assert result["status"] == "resolved" and result["canonical_target"] == "P.F"


def test_forms_qualified_column_and_inconsistent_table(tmp_path):
    app, k = prepared(
        tmp_path, 'CREATE TABLE S.T("I.d" NUMBER); CREATE TABLE U(ID NUMBER);'
    )
    app.ingest(
        "f.xml",
        b'<form name="F"><block name="B" table="S.T"><item name="OK" column="T.&quot;I.d&quot;"/><item name="BAD" column="U.ID" mode="edit"/></block></form>',
    )
    assert app.parse_all()["errors"] == 0
    result = k.derive()
    assert result["status"] == "partial"
    relations = [
        c["payload"] for c in k.candidates() if c["record_type"] == "candidate_relation"
    ]
    assert any(
        c["source_entity"] == "F.B.OK" and c["target_entity"] == 'S.T."I.d"'
        for c in relations
    )
    assert not any(c["source_entity"] == "F.B.BAD" for c in relations)
    blocks = [
        c
        for r in result["coverage"]["evidence"]
        for c in r["components"]
        if c["reason_code"] == "column_table_mismatch"
    ]
    assert len(blocks) == 2 and all(
        c["resolution"]["status"] == "inconsistent" for c in blocks
    )


def test_merge_branches_survive_full_cycle_without_conflict(tmp_path):
    app, k = prepared(
        tmp_path,
        "CREATE TABLE T(ID NUMBER, V NUMBER); CREATE TABLE S(ID NUMBER); MERGE INTO T a USING S b ON a.ID=b.ID WHEN MATCHED THEN UPDATE SET V=4 WHEN NOT MATCHED THEN INSERT(ID,V) VALUES(b.ID,5);",
    )
    values = [f for f in facts(k, "assigned_value") if f["entity_name"] == "T.V"]
    assert {f["property_value"]["value"] for f in values} == {"4", "5"}
    assert {f["attributes"]["context"]["branch"] for f in values} == {0, 1}
    k.review_many(
        [c["id"] for c in k.candidates()], "confirmed", reason="Branch acceptance"
    )
    k.merge()
    assert not k.conflicts()
    from dslm3.exports import Exports

    snap = Exports(app).snapshot()
    reopened = Knowledge(Application(tmp_path))
    assert not reopened.conflicts()
    for suffix in ("json", "yaml", "md"):
        text = (app.root / "artifacts" / snap["id"] / ("dsl." + suffix)).read_text(
            encoding="utf-8"
        )
        assert "branch" in text and "T.V" in text
    assert not Exports(app).diff(snap["id"], Exports(app).snapshot()["id"])["changes"]


def test_resolver_import_order_and_same_named_columns(tmp_path):
    dependencies = []
    for index, sequence in enumerate((("ddl.sql", "use.sql"), ("use.sql", "ddl.sql"))):
        app = Application(tmp_path / str(index))
        app.store.configure({"sql_dialect": "oracle"})
        corpus = {
            "ddl.sql": b"CREATE TABLE T(ID NUMBER, V NUMBER);",
            "use.sql": b"UPDATE T SET V=1 WHERE ID=2;",
        }
        for name in sequence:
            app.ingest(name, corpus[name])
            assert app.parse_all()["errors"] == 0
        k = Knowledge(app)
        k.derive()
        report = app.coverage(check=True)
        assert report["counts"]["blocked_unresolved_components"] == 0
        dependencies.append(
            {
                (c["payload"]["relation_type"], c["payload"]["target_entity"])
                for c in k.candidates()
                if c["current_parse"]
                and c["current_derivation"]
                and c["record_type"] == "candidate_relation"
            }
        )
        assert all(r["cached"] for r in app.parse_all()["results"])
    assert (
        dependencies[0] == dependencies[1] and ("reads_from", "T.ID") in dependencies[0]
    )


def test_internal_parser_error_is_never_evidence_only(monkeypatch):
    from dslm3.parsers import sql

    def broken(*args, **kwargs):
        raise ValueError("controlled internal defect")

    monkeypatch.setattr(sql.sqlglot, "parse_one", broken)
    with pytest.raises(ValueError, match="controlled internal defect"):
        sql.parse_sql("UPDATE T SET X=1;", "oracle")
