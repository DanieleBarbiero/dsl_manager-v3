"""Release regressions recovered from the interrupted run and independently rerun."""

import io
import json
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient
from lxml import etree

from dslm3.ai import AI
from dslm3.common import DomainError
from dslm3.exports import Exports
from dslm3.knowledge import Knowledge, POLICIES
from dslm3.parsers.documents import parse_legacy_sheet, parse_structured
from dslm3.parsers.sql import parse_sql
from dslm3.service import Application
from dslm3.temporal import Temporal, point
from dslm3.web import create_app, dispatch


def confirmed(app):
    k = Knowledge(app)
    k.derive()
    app.store.configure({"automatic_policies": list(POLICIES.values())})
    k.auto_review()
    k.merge()
    return k


def test_incremental_source_preserves_reviews_and_batch_membership(tmp_path):
    app = Application(tmp_path)
    app.ingest("a.sql", b"CREATE TABLE a(id INT);")
    app.parse_all()
    k = confirmed(app)
    before = {c["id"]: c["decision_id"] for c in k.candidates()}
    app.ingest("b.sql", b"CREATE TABLE b(id INT);")
    app.parse_all()
    derived = k.derive()
    after = {c["id"]: c["decision_id"] for c in k.candidates()}
    assert all(after[cid] == decision for cid, decision in before.items())
    assert len(after) == 4
    assert len(k.candidates("pending")) == 2
    assert len(k.candidates(batch=derived["batch_id"])) == 4
    k.auto_review()
    k.merge([derived["batch_id"]], strict=True)
    assert len(k.objects()) == 4


def test_dialect_reinterpretation_and_cached_reactivation(tmp_path):
    app = Application(tmp_path)
    app.ingest("p.sql", b"CREATE PROCEDURE p AS BEGIN UPDATE a SET id=1; END;\n/")
    app.store.configure({"sql_dialect": "oracle"})
    app.parse_all()
    k = confirmed(app)
    before = {e["id"] for e in app.evidence()}
    old = next(c for c in k.candidates() if c["rule"] == "sql_unit")
    ai = AI(app)
    pkg = ai.package(ai.select()["id"])
    app.store.configure({"sql_dialect": "postgres"})
    app.parse_all()
    assert next(c for c in k.candidates() if c["id"] == old["id"])["current_parse"] == 0
    assert not any(
        s["candidate_id"] == old["id"] for o in k.objects() for s in o["supports"]
    )
    assert next(p for p in ai.packages() if p["id"] == pkg["id"])["stale"]
    app.store.configure({"sql_dialect": "oracle"})
    result = app.parse_all()
    assert all(p.get("cached") for p in result["results"])
    assert before == {e["id"] for e in app.evidence()}
    assert next(c for c in k.candidates() if c["id"] == old["id"])["current_parse"] == 1
    assert any(
        s["candidate_id"] == old["id"] for o in k.objects() for s in o["supports"]
    )
    assert app.store.one("SELECT MAX(version) AS v FROM schema_history")["v"] == 2
    assert (
        Application(tmp_path).store.one("PRAGMA integrity_check")["integrity_check"]
        == "ok"
    )


@pytest.mark.parametrize(
    "sql,dialect,kind,target",
    [
        (
            "DECLARE n NUMBER; BEGIN SELECT id INTO n FROM a; END;\n/",
            "oracle",
            "sql_anonymous_block",
            "A.ID",
        ),
        (
            "CREATE FUNCTION f() RETURNS int AS $$ BEGIN RETURN (SELECT id FROM a); END; $$ LANGUAGE plpgsql;",
            "postgres",
            "sql_function",
            "A.ID",
        ),
        (
            "CREATE PROCEDURE p @n INT AS BEGIN SELECT id FROM a WHERE id=@n; END\nGO\nSELECT 1;",
            "tsql",
            "sql_procedure",
            "A.ID",
        ),
        (
            "DELIMITER $$\nCREATE PROCEDURE p() BEGIN SELECT id INTO n FROM a; END$$\nDELIMITER ;\nSELECT 1;",
            "mysql",
            "sql_procedure",
            "A.ID",
        ),
    ],
)
def test_procedural_units_and_variable_scope(sql, dialect, kind, target):
    r = parse_sql(sql, dialect, {"A": ["ID"]})
    assert any(e["type"] == kind for e in r.evidence)
    assert any(e["data"].get("target") == target for e in r.evidence)
    assert not any(e["data"].get("target") in {"N", "A.N"} for e in r.evidence)
    assert not any(e["type"] == "sql_unparsed" for e in r.evidence)
    if "SELECT 1;" in sql:
        assert any(
            e["type"] == "sql_statement"
            and e["data"]["owner"] is None
            and "SELECT 1" in e["text"]
            for e in r.evidence
        )


@pytest.mark.parametrize(
    "raw,precision",
    [
        ("2026-01-01T12:34Z", "minute"),
        ("2026-01-01T12:34:56Z", "second"),
        ("2026-01-01T12:34:56.123Z", "millisecond"),
        ("2026-01-01T12:34:56.123456Z", "microsecond"),
    ],
)
def test_fine_temporal_precision(raw, precision):
    assert point(raw)["precision"] == precision
    if "." in raw:
        assert raw.split(".")[1] in point(raw)["start"]


def test_submicrosecond_not_silently_truncated():
    with pytest.raises(DomainError):
        point("2026-01-01T00:00:00.1234567Z")


def test_docling_escaped_temporal_declaration(tmp_path):
    app = Application(tmp_path)
    rev = app.ingest("converted.md", b"valid\\_from: 2026-09-01")["revision_id"]
    temporal = Temporal(app)
    temporal.extract(rev)
    assert any(
        r["payload"]["date_role"] == "valid_from"
        and r["payload"]["raw_value"] == "2026-09-01"
        for r in temporal.raw()
    )


def test_equivalent_offsets_are_concordant_and_markdown_dates_recognized(tmp_path):
    app = Application(tmp_path)
    rev = app.ingest("valid.md", b"**valid_from**: 2026-01-01\n_valid_to_: 2026-12-31")[
        "revision_id"
    ]
    app.parse_all()
    t = Temporal(app)
    t.extract(rev)
    assert {"valid_from", "valid_to"} <= {r["payload"]["date_role"] for r in t.raw()}
    for i, value in enumerate(["2026-01-01T12:00:00Z", "2026-01-01T13:00:00+01:00"]):
        t.add_raw(
            rev,
            "source_revision",
            rev,
            [
                {
                    "source_key": str(i),
                    "raw_value": value,
                    "source_format": "test",
                    "date_role": "effective_date",
                }
            ],
        )
    groups = t.consolidate("source_revision", rev)["groups"]
    equivalent = [g for g in groups if g["role"] == "effective_date"]
    assert len(equivalent) == 1 and len(equivalent[0]["evidence_ids"]) == 2
    assert equivalent[0]["assessment"] == "single_or_correlated"


def test_ai_temporal_bypass_rejected_atomically(tmp_path):
    app = Application(tmp_path)
    rev = app.ingest("policy.md", b"valid_from: 2026")["revision_id"]
    app.parse_all()
    t = Temporal(app)
    t.extract(rev)
    ids = [r["id"] for r in t.raw() if r["payload"]["date_role"] == "valid_from"]
    batch = t.propose(rev, "source_revision", rev, ids)
    k = Knowledge(app)
    payload = k.candidates(batch=batch["batch_id"])[0]["payload"]
    ai = AI(app)
    pkg = ai.package(ai.select()["id"])
    with pytest.raises(DomainError, match="flusso temporale"):
        ai.import_response(pkg["id"], json.dumps(payload))
    assert len(k.candidates()) == 1


def test_partial_pipeline_and_cli_are_visible(tmp_path):
    app = Application(tmp_path / "app")
    assert (
        app.run("diagnostics", lambda: dispatch(app, "diagnostics", {}))["status"]
        == "partial"
    )
    app.parse_all = lambda: {"results": [], "success": 0, "partial": 1, "errors": 0}
    assert (
        app.run("pipeline", lambda: dispatch(app, "pipeline", {}))["status"]
        == "partial"
    )
    result = subprocess.run(
        [sys.executable, "-m", "dslm3", "-w", str(tmp_path / "cli"), "diagnostics"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 6 and json.loads(result.stdout)["status"] == "partial"


@pytest.mark.parametrize("paths", ["null", "{}", "[12]", '"wrong"'])
def test_upload_path_types_are_rejected(tmp_path, paths):
    with TestClient(create_app(tmp_path)) as client:
        token = client.get("/api/bootstrap").json()["token"]
        r = client.post(
            "/api/upload",
            headers={"X-DSLM3-Token": token},
            data={"paths": paths},
            files={"files": ("a.txt", b"data")},
        )
        assert r.status_code == 400 and r.json()["reason"] == "invalid_paths"
        assert client.get("/api/sources").json() == []


def test_yaml_dates_stay_serializable_and_ods_budget_rejects(tmp_path):
    r = parse_structured("date: 2026-01-01\ntext: città", " .yaml".strip())
    assert r.evidence[0]["data"]["value"]["date"] == "2026-01-01"
    json.dumps(r.evidence, allow_nan=False)
    from odf.opendocument import OpenDocumentSpreadsheet
    from odf.table import Table, TableRow, TableCell

    doc = OpenDocumentSpreadsheet()
    sheet = Table(name="Sheet")
    row = TableRow()
    row.addElement(TableCell(numbercolumnsrepeated=10001))
    sheet.addElement(row)
    doc.spreadsheet.addElement(sheet)
    stream = io.BytesIO()
    doc.save(stream)
    with pytest.raises(DomainError, match="colonne"):
        parse_legacy_sheet(tmp_path / "oversized.ods", stream.getvalue())


def test_graph_has_provenance_fact_source_conflict_nodes(tmp_path):
    app = Application(tmp_path)
    app.ingest("a.sql", b"CREATE TABLE a(id INT);")
    app.parse_all()
    k = confirmed(app)
    evidence = app.evidence()[0]
    for i in range(2):
        payload = {
            "record_type": "candidate_fact",
            "candidate_id": str(i),
            "source_revision_id": evidence["revision_id"],
            "evidence_id": evidence["id"],
            "evidence_text": evidence["text"],
            "assertion_type": "inferred",
            "confidence": "low",
            "fact_type": "test",
            "entity_name": "TEST",
            "property_name": "value",
            "property_value": i,
        }
        batch = k.import_candidates([payload], "test")
        k.review_many(batch["candidate_ids"], "confirmed")
    k.merge()
    exports = Exports(app)
    snapshot = exports.snapshot()
    graph = exports.graph(snapshot["id"])
    root = etree.fromstring((app.root / graph["files"][0]).read_bytes())
    ns = {"g": "http://gexf.net/1.3"}
    kinds = set(
        root.xpath('//g:node/g:attvalues/g:attvalue[@for="kind"]/@value', namespaces=ns)
    )
    assert {"entity", "fact", "source", "conflict"} <= kinds
    assert {"mentions", "derives_from", "conflicts_with"} <= set(
        root.xpath("//g:edge/@label", namespaces=ns)
    )
    assert evidence["text"] in "".join(
        root.xpath('//g:attvalue[@for="provenance"]/@value', namespaces=ns)
    )
    graph = exports.graph(
        snapshot["id"],
        include_sources=False,
        include_fact_nodes=False,
        include_conflicts=False,
    )
    text = (app.root / graph["files"][0]).read_text()
    assert 'value="source"' not in text and 'value="fact"' not in text


def test_scan_revisions_missing_exclusions_and_replay(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    (source / "a.txt").write_text("first")
    (source / "ignored.txt").write_text("ignore")
    app = Application(tmp_path / "work")
    app.store.configure({"exclude": ["ignored.txt"]})
    assert app.scan(source)["changed"] == 1
    assert app.scan(source)["changed"] == 0
    (source / "a.txt").write_text("second")
    assert app.scan(source)["changed"] == 1
    assert app.status()["counts"]["revisions"] == 2
    (source / "a.txt").unlink()
    assert app.scan(source)["missing"] == ["a.txt"]
    assert app.sources()[0]["status"] == "missing"


def test_html_metadata_has_separate_roles(tmp_path):
    app = Application(tmp_path)
    rev = app.ingest(
        "page.html",
        b'<html><meta name="datePublished" content="2026-01-02"><time datetime="2025-02-01"></time><script type="application/ld+json">{"validFrom":"2026-01-01"}</script></html>',
    )["revision_id"]
    t = Temporal(app)
    t.extract(rev)
    roles = {r["payload"]["date_role"] for r in t.raw()}
    assert {
        "valid_from",
        "document_datePublished",
        "document_time",
        "operational_time",
    } <= roles
    assert not Knowledge(app).objects()
