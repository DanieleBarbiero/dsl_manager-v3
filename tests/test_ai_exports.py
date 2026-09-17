import json
import pytest
from dslm3.service import Application
from dslm3.knowledge import Knowledge, POLICIES
from dslm3.ai import AI
from dslm3.exports import Exports
from dslm3.temporal import Temporal
from dslm3.common import DomainError


@pytest.fixture
def ready(tmp_path):
    a = Application(tmp_path / "app")
    a.ingest(
        "schema.sql",
        b"CREATE TABLE a(id INT PRIMARY KEY); CREATE TABLE b(id INT, a_id INT REFERENCES a(id));",
    )
    a.ingest("manual.md", b"Priority P1 must be handled within 30 minutes.\n")
    a.parse_all()
    k = Knowledge(a)
    k.derive()
    a.store.configure({"automatic_policies": list(POLICIES.values())})
    k.auto_review()
    k.merge()
    return a


def response(a, package, value="30", cid="candidate_001"):
    e = next(
        e
        for e in a.evidence()
        if e["id"] in package["evidence_ids"] and e["kind"] == "chunk"
    )
    return json.dumps(
        {
            "record_type": "candidate_fact",
            "candidate_id": cid,
            "source_revision_id": e["revision_id"],
            "evidence_id": e["id"],
            "evidence_text": e["text"],
            "assertion_type": "inferred",
            "confidence": "medium",
            "fact_type": "domain",
            "entity_name": "P1",
            "property_name": "response_minutes",
            "property_value": value,
        }
    )


def test_selection_coverage_explainability_and_budget(ready):
    ai = AI(ready)
    technical = ai.select("technical_extraction")
    domain = ai.select()
    assert any("already_confirmed" in x["reason_codes"] for x in technical["items"])
    assert any(
        x["coverage"] == "confirmed" and x["outcome"] == "included"
        for x in domain["items"]
    )
    assert ai.select(max_chars=0)["selected_count"] == 0
    assert ai.select(max_evidence=1)["selected_count"] == 1
    assert all(x["reason_codes"] for x in domain["items"])


def test_multi_package_import_review_merge_and_true_conflict(ready):
    ai = AI(ready)
    k = Knowledge(ready)
    exports = Exports(ready)
    first = ai.package(ai.select()["id"])
    second = ai.package(ai.select(max_evidence=2)["id"])
    assert first["id"] != second["id"]
    before = exports.snapshot()
    r1 = ai.import_response(first["id"], response(ready, first))
    r2 = ai.import_response(second["id"], response(ready, second, "60"))
    assert r1["candidate_ids"] != r2["candidate_ids"]
    assert all(
        c["state"] == "pending"
        for c in k.candidates()
        if c["id"] in r1["candidate_ids"] + r2["candidate_ids"]
    )
    k.review_many(r1["candidate_ids"] + r2["candidate_ids"], "confirmed")
    assert ready.status()["counts"]["confirmed_unmerged"] == 2
    assert exports.snapshot()["hash"] == before["hash"]
    k.merge([r1["batch_id"], r2["batch_id"]])
    after = exports.snapshot()
    assert after["counts"]["facts"] == before["counts"]["facts"] + 2
    assert after["counts"]["conflicts"] == 1
    assert exports.diff(before["id"], after["id"])["count"] > 0
    assert exports.snapshot()["hash"] == after["hash"]
    assert exports.graph(after["id"])["validation"] == "offline_xsd_and_semantic"
    assert exports.graph(after["id"], dynamic=True)["files"]


def test_staleness_provenance_and_integrity(ready):
    ai = AI(ready)
    plan = ai.select()
    pkg = ai.package(plan["id"])
    text = response(ready, pkg)
    corrupted = json.loads(text)
    corrupted["evidence_text"] = "not present"
    with pytest.raises(DomainError, match="sottostringa"):
        ai.import_response(pkg["id"], json.dumps(corrupted))
    ready.ingest("manual.md", b"new version")
    with pytest.raises(DomainError, match="cambiata"):
        ai.package(plan["id"])
    with pytest.raises(DomainError, match="cambiata"):
        ai.import_response(pkg["id"], text)
    stale = ai.import_response(pkg["id"], text, allow_stale=True)
    assert stale["stale"]
    assert Knowledge(ready).merge([stale["batch_id"]])["created"] == 0


def test_export_reconciliation_and_cross_schema_gate(ready):
    k = Knowledge(ready)
    exports = Exports(ready)
    exports.snapshot()
    cid = k.candidates("confirmed")[0]["id"]
    k.review(cid, "rejected")
    with pytest.raises(DomainError, match="riconciliazione"):
        exports.snapshot()
    assert exports.snapshot(allow_incomplete=True)["content"]["metadata"]["warnings"]
    with pytest.raises(DomainError):
        exports.snapshot(1, True)
    k.reconcile()
    old = exports.snapshot(1)
    new = exports.snapshot(2)
    with pytest.raises(DomainError):
        exports.diff(old["id"], new["id"])
    assert exports.diff(old["id"], new["id"], True)["cross_schema"]


def test_dynamic_intervals_xsd_and_no_network(ready, monkeypatch):
    k = Knowledge(ready)
    t = Temporal(ready)
    exports = Exports(ready)
    fact = next(o for o in k.objects() if o["kind"] == "fact")
    revision = fact["supports"][0]["candidate_payload"]["source_revision_id"]
    for year in ["2024", "2026"]:
        ids = t.add_raw(
            revision,
            "fact",
            fact["id"],
            [
                {
                    "source_key": year,
                    "raw_value": year,
                    "date_role": "competence_year",
                    "source_format": "text",
                }
            ],
        )
        p = t.propose(revision, "fact", fact["id"], ids)
        k.review_many(p["candidate_ids"], "confirmed")
    k.merge()
    snapshot = exports.snapshot()
    monkeypatch.setattr(
        "socket.create_connection", lambda *a, **k: pytest.fail("network forbidden")
    )
    graph = exports.graph(snapshot["id"], True)
    text = (ready.root / graph["files"][0]).read_text()
    from lxml import etree

    root = etree.fromstring(text.encode())
    ns = {"g": "http://gexf.net/1.3"}
    fact_nodes = root.xpath(
        '//g:node[g:attvalues/g:attvalue[@for="kind" and @value="fact"]]', namespaces=ns
    )
    assert sum(len(n.findall("g:spells/g:spell", ns)) for n in fact_nodes) == 2
    assert "2024-01-01" in text and "2026-12-31" in text
