from pathlib import Path
import pytest
from dslm3.service import Application
from dslm3.knowledge import Knowledge, POLICIES
from dslm3.common import DomainError


@pytest.fixture
def app(tmp_path):
    a = Application(tmp_path / "project")
    a.ingest(
        "schema.sql", b"CREATE TABLE ITEMS(ID NUMBER PRIMARY KEY, STATE VARCHAR2(20));"
    )
    a.parse_all()
    return a


def payload(app, value="yes", candidate_id="human_1"):
    e = app.evidence()[0]
    return {
        "record_type": "candidate_fact",
        "candidate_id": candidate_id,
        "source_revision_id": e["revision_id"],
        "fragment_id": e["id"],
        "evidence_text": e["text"],
        "assertion_type": "inferred",
        "confidence": "medium",
        "fact_type": "domain",
        "entity_name": "Business",
        "property_name": "enabled",
        "property_value": value,
    }


def test_governance_review_merge_idempotence_and_revoke(app):
    k = Knowledge(app)
    r = k.derive()
    assert r["count"] == 3
    assert k.merge()["created"] == 0
    assert not k.objects()
    app.store.configure({"automatic_policies": list(POLICIES.values())})
    assert k.auto_review()["count"] == 3
    assert k.merge()["created"] == 3
    assert k.merge()["created"] == 0
    assert k.derive()["batch_id"] == r["batch_id"]
    cid = r["candidate_ids"][0]
    head = next(c["decision_id"] for c in k.candidates() if c["id"] == cid)
    k.review(
        cid,
        "rejected",
        reason="regression",
        expected_head=head,
        check_head=True,
        idempotency_key="revoke_1",
    )
    assert k.review(cid, "rejected", reason="regression", idempotency_key="revoke_1")[
        "replay"
    ]
    with pytest.raises(DomainError, match="Chiave"):
        k.review(cid, "confirmed", idempotency_key="revoke_1")
    with pytest.raises(DomainError, match="cambiata"):
        k.review(cid, "confirmed", expected_head=head, check_head=True)
    assert len(k.objects()) == 2
    assert app.status()["counts"]["open_reconciliations"] == 1
    assert k.reconcile()["closed"] == 1


def test_provenance_atomic_batch(app):
    k = Knowledge(app)
    good = payload(app)
    bad = {**good, "candidate_id": "bad", "evidence_text": "invented quote"}
    with pytest.raises(DomainError, match="sottostringa"):
        k.import_candidates([good, bad], "ai:test")
    assert not k.candidates()
    with pytest.raises(DomainError, match="duplicato"):
        k.import_candidates([good, good], "ai:test")
    p = {**good, "property_value": "REPLACE_VALUE"}
    with pytest.raises(DomainError, match="segnaposto"):
        k.import_candidates([p], "ai:test")


def test_ai_cannot_autoapprove_and_strict_atomic(app):
    k = Knowledge(app)
    r = k.import_candidates([payload(app)], "ai:test")
    cid = r["candidate_ids"][0]
    app.store.configure({"automatic_policies": list(POLICIES.values())})
    assert k.auto_review()["count"] == 0
    with pytest.raises(DomainError):
        k.review(
            cid, "confirmed", actor_type="policy", actor_id=list(POLICIES.values())[0]
        )
    with pytest.raises(DomainError):
        k.merge(strict=True)
    assert not k.objects()
    k.review(cid, "confirmed")
    assert k.merge()["created"] == 1


def test_supports_corrections_and_conflicts(app):
    k = Knowledge(app)
    ids = []
    for n in range(2):
        ids += k.import_candidates(
            [payload(app, candidate_id="same")], f"ai:package{n}"
        )["candidate_ids"]
    k.review_many(ids, "confirmed")
    k.merge()
    assert len(k.objects()) == 1 and len(k.objects()[0]["supports"]) == 2
    k.review(ids[0], "rejected")
    k.reconcile()
    assert len(k.objects()) == 1
    p = payload(app, "no", "replacement")
    r = k.correct(ids[1], p)
    assert len(k.objects()) == 0
    k.merge([r["batch_id"]])
    k.reconcile()
    assert k.objects()[0]["payload"]["property_value"] == "no"
    with pytest.raises(DomainError):
        k.correct(ids[1], p)
    other = k.import_candidates([payload(app, "maybe", "other")], "ai:other")
    k.review_many(other["candidate_ids"], "confirmed")
    k.merge()
    assert len(k.conflicts()) == 1


def test_source_revision_and_append_only(app):
    k = Knowledge(app)
    k.derive()
    app.store.configure({"automatic_policies": list(POLICIES.values())})
    k.auto_review()
    k.merge()
    with app.store.connect(True) as c:
        with pytest.raises(Exception, match="append_only"):
            c.execute("DELETE FROM candidates")
    app.ingest(
        "schema.sql", b"CREATE TABLE ITEMS(ID NUMBER PRIMARY KEY, STATE VARCHAR2(30));"
    )
    assert not k.objects()
    app.parse_all()
    k.derive()
    k.auto_review()
    k.merge()
    assert len(k.objects()) == 3


def test_parse_retry_keeps_evidence_and_candidates_stable(app):
    first = app.evidence()
    k = Knowledge(app)
    a = k.derive()
    rev = app.sources()[0]["current_revision"]
    app.parse(rev, app.schema(), retry=True)
    assert [e["id"] for e in app.evidence()] == [e["id"] for e in first]
    assert k.derive()["batch_id"] == a["batch_id"]


def test_logs_do_not_create_false_conflicts(tmp_path):
    a = Application(tmp_path / "logs")
    p = Path(__file__).parents[1] / "src/dslm3/resources/vega/logs/vega_2026.log"
    a.ingest("runtime.log", p.read_bytes())
    a.parse_all()
    k = Knowledge(a)
    k.derive()
    a.store.configure({"automatic_policies": list(POLICIES.values())})
    k.auto_review()
    k.merge()
    assert len([o for o in k.objects() if o["kind"] == "fact"]) == 5
    assert k.conflicts() == []
