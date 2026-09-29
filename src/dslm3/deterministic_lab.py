"""Fresh Vega acceptance without AI responses, independent explicit slot oracle."""

from __future__ import annotations
import argparse
from pathlib import Path
import sqlglot

from dslm3.ai import AI
from dslm3.common import dump_json, digest
from dslm3.knowledge import Knowledge
from dslm3.provenance import code_provenance
from dslm3.service import Application
from dslm3.exports import Exports

EXPECTED = [
    (
        "RICHIESTA_RICAMBIO.STATO",
        "assigned_value",
        {"type": "string", "value": "PRENOTATA"},
    ),
    ("RICHIESTA_RICAMBIO", "row_selection_expression", "ID_RICHIESTA = P_ID_RICHIESTA"),
    ("ARTICOLO.QTA_DISPONIBILE", "assignment_expression", "QTA_DISPONIBILE - 1"),
    (
        "ARTICOLO",
        "row_selection_expression",
        "ID_ARTICOLO = (SELECT ID_ARTICOLO FROM RICHIESTA_RICAMBIO WHERE ID_RICHIESTA = P_ID_RICHIESTA)",
    ),
]


def run(workspace: Path, report: Path):
    if workspace.exists() and any(workspace.iterdir()):
        raise ValueError("Il laboratorio deterministico richiede un workspace nuovo.")
    app = Application(workspace)
    app.store.configure({"sql_dialect": "oracle"})
    app.load_vega()
    parsed = app.parse_all()
    k = Knowledge(app)
    derived = k.derive()
    coverage = app.coverage()
    actual = []
    for c in k.candidates():
        p = c["payload"]
        if p.get("property_name") in {x[1] for x in EXPECTED}:
            actual.append(
                {
                    "entity": p["entity_name"],
                    "property": p["property_name"],
                    "value": p["property_value"],
                    "candidate_id": c["id"],
                    "evidence_id": p["evidence_id"],
                    "context": p["attributes"]["context"],
                }
            )

    def equal(value, expected):
        if isinstance(expected, dict):
            return value == expected
        return isinstance(value, str) and sqlglot.parse_one(
            value, read="oracle"
        ) == sqlglot.parse_one(expected, read="oracle")

    matches = [
        any(
            r["entity"] == ent and r["property"] == prop and equal(r["value"], value)
            for r in actual
        )
        for ent, prop, value in EXPECTED
    ]
    technical = AI(app).select("technical_extraction")
    domain = AI(app).select("domain_interpretation")
    sql_ids = {
        e["id"]
        for e in app.evidence()
        if e["type"] == "sql_statement" and e["data"]["statement_type"] == "update"
    }
    checks = {
        "six_real_sources": len(app.sources()) == 6
        and parsed["success"] == 6
        and parsed["errors"] == parsed["partial"] == 0,
        "four_expected_slots": all(matches) and len(actual) == 4,
        "coverage_complete": coverage["complete"],
        "no_unexpected_resolution": not any(
            coverage["counts"]["blocked_" + s + "_components"]
            for s in ("unresolved", "ambiguous", "inconsistent")
        ),
        "pending_not_merged": k.merge()["created"] == 0 and not k.objects(),
        "technical_updates_excluded": all(
            i["outcome"] == "excluded"
            and "deterministic_components_complete" in i["reason_codes"]
            for i in technical["items"]
            if i["evidence_id"] in sql_ids
        ),
        "domain_updates_available": all(
            i["outcome"] == "included"
            for i in domain["items"]
            if i["evidence_id"] in sql_ids
        ),
        "no_ai_contribution": not app.store.rows(
            "SELECT * FROM batches WHERE origin LIKE 'ai%'"
        ),
    }
    k.review_many(
        derived["candidate_ids"],
        "confirmed",
        actor_id="deterministic-lab",
        reason="Verifica esplicita delle dichiarazioni e dei quattro slot attesi",
    )
    k.merge()
    k.reconcile()
    snapshot = Exports(app).snapshot()
    checks["no_false_conflict"] = not k.conflicts()
    checks["retry_stable"] = k.derive()["candidate_ids"] == derived["candidate_ids"]
    checks["reopen_effective"] = len(
        Knowledge(Application(workspace)).objects()
    ) == len(k.objects())
    refs = [c["payload"] for c in k.candidates()]
    checks["ontology_and_provenance"] = {
        "foreign_key",
        "maps_to",
        "calls",
        "observed_on",
    } <= {c.get("relation_type") for c in refs} and all(
        c.get("evidence_text") and c.get("evidence_id") for c in refs
    )
    content = {
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "code_provenance": code_provenance(),
        "ai_responses_imported": 0,
        "expected_slots": EXPECTED,
        "actual_slots": actual,
        "fixture_hashes": [
            {"path": s["path"], "sha256": s["sha256"]} for s in app.sources()
        ],
        "parse": parsed,
        "coverage": coverage,
        "technical_selection": technical,
        "domain_selection": domain,
        "snapshot_id": snapshot["id"],
        "semantic_keys": [o["semantic_key"] for o in k.objects()],
        "semantic_keys_hash": digest([o["semantic_key"] for o in k.objects()]),
    }
    dump_json(report, content)
    if content["status"] != "passed":
        raise AssertionError({k: v for k, v in checks.items() if not v})
    return content


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.workspace, args.report)
    print(result["status"], result["checks"])


if __name__ == "__main__":
    main()
