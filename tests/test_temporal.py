import pytest
from dslm3.service import Application
from dslm3.knowledge import Knowledge
from dslm3.temporal import Temporal, point
from dslm3.common import DomainError


@pytest.mark.parametrize(
    "raw,start,end",
    [
        ("2024", "2024-01-01", "2024-12-31"),
        ("2024-02", "2024-02-01", "2024-02-29"),
        ("2024-02-03", "2024-02-03", "2024-02-03"),
        (
            "2024-02-03T10:00:00+01:00",
            "2024-02-03T10:00:00+01:00",
            "2024-02-03T10:00:00+01:00",
        ),
    ],
)
def test_precision(raw, start, end):
    p = point(raw)
    assert p["start"] == start and p["end"] == end


def test_unknown_timezone_and_dst():
    assert point("2024-01-01T10:00:00")["timezone_status"] == "unknown"
    assert point("2024-01-01T10:00:00", "Europe/Rome")["timezone_status"] == "resolved"
    with pytest.raises(DomainError):
        point("2024-10-27T02:30:00", "Europe/Rome")


def setup(tmp_path):
    a = Application(tmp_path / "time")
    r = a.ingest("policy_2024.md", b"valid_from: 2024-01-01\nvalid_to: 2024-12-31\n")
    a.parse_all()
    return a, r["revision_id"]


def test_extract_never_auto_validates(tmp_path):
    a, r = setup(tmp_path)
    t = Temporal(a)
    x = t.extract(r)
    assert x["count"] >= 4
    records = t.raw()
    assert all(
        "mtime" not in e["payload"]["source_key"]
        and "ctime" not in e["payload"]["source_key"]
        for e in records
    )
    first = [
        e for e in records if e["payload"]["source_key"] == "sources.first_seen_at"
    ][0]
    assert first["payload"]["raw_value"] == a.sources()[0]["first_seen"]
    result = t.consolidate("source_revision", r)
    assert result["proposals"]
    assert all(c["state"] == "pending" for c in Knowledge(a).candidates())
    assert not Knowledge(a).objects()
    assert any(
        c["payload"]["normalized_start"] == "2024-01-01"
        and c["payload"]["normalized_end"] == "2024-12-31"
        for c in Knowledge(a).candidates()
    )


def test_timezone_review_gate_and_multisupport(tmp_path):
    a, r = setup(tmp_path)
    t = Temporal(a)
    k = Knowledge(a)
    ids = t.add_raw(
        r,
        "source_revision",
        r,
        [
            {
                "source_key": "explicit",
                "raw_value": "2024-01-01T10:00:00",
                "source_format": "text",
                "date_role": "valid_from",
            }
        ],
    )
    candidate = t.propose(r, "source_revision", r, ids)["candidate_ids"][0]
    with pytest.raises(DomainError, match="timezone"):
        k.review(candidate, "confirmed")
    p = t.propose(r, "source_revision", r, ids, tz="Europe/Rome")
    k.review_many(p["candidate_ids"], "confirmed")
    k.merge()
    assert len(k.objects()) == 1
    ids2 = t.add_raw(
        r,
        "source_revision",
        r,
        [
            {
                "source_key": "other",
                "raw_value": "2024-01-01T10:00:00+01:00",
                "source_format": "text",
                "date_role": "valid_from",
            }
        ],
    )
    p2 = t.propose(r, "source_revision", r, ids2)
    k.review_many(p2["candidate_ids"], "confirmed")
    k.merge()
    # Explicit/resolved timezone descriptors may produce distinct semantic intervals;
    # a duplicate interval with identical metadata must reuse one object.
    p3 = t.propose(r, "source_revision", r, ids2, policy="additional_support")
    k.review_many(p3["candidate_ids"], "confirmed")
    k.merge()
    assert any(len(o["supports"]) == 2 for o in k.objects())
    k.review(p2["candidate_ids"][0], "rejected")
    k.reconcile()
    assert k.objects()


def test_independence_correlation_conflict_and_propagation(tmp_path):
    a, r = setup(tmp_path)
    t = Temporal(a)
    k = Knowledge(a)
    r2 = a.ingest("copy.md", b"valid_from: 2024-01-01\nvalid_to: 2024-12-31\n")[
        "revision_id"
    ]
    r3 = a.ingest("independent.md", b"independent declaration 2024")["revision_id"]
    for rev in [r, r2, r3]:
        t.add_raw(
            rev,
            "source_revision",
            r,
            [
                {
                    "source_key": "e",
                    "raw_value": "2024",
                    "source_format": "text",
                    "date_role": "competence_year",
                }
            ],
        )
    result = t.consolidate("source_revision", r)
    g = result["groups"][0]
    assert g["independent_sources"] == 2 and g["assessment"] == "concordant"
    ids = result["proposals"][0]["candidate_ids"]
    k.review_many(ids, "confirmed")
    k.merge()
    propagated = t.propagate(
        ["source_revision:" + r], "source_revision", r2, "explicit_copy"
    )
    assert propagated["count"] == 1
    assert all(
        c["state"] == "pending"
        for c in k.candidates()
        if c["id"] in propagated["proposals"][0]["candidate_ids"]
    )
    t.add_raw(
        r3,
        "source_revision",
        r,
        [
            {
                "source_key": "changed",
                "raw_value": "2025",
                "source_format": "text",
                "date_role": "competence_year",
            }
        ],
    )
    assert t.consolidate("source_revision", r)["conflict_count"] > 0
