"""Vega M3: reproducible acceptance laboratory, no external AI calls."""

from __future__ import annotations
import argparse
import json
from pathlib import Path

from dslm3.ai import AI
from dslm3.common import dump_json, now
from dslm3.exports import Exports
from dslm3.knowledge import Knowledge, POLICIES
from dslm3.service import Application
from dslm3.temporal import Temporal


def run(workspace: Path, report_path: Path):
    app = Application(workspace)
    k = Knowledge(app)
    ai = AI(app)
    export = Exports(app)
    checks = []

    def check(name, condition, details=None):
        checks.append({"name": name, "passed": bool(condition), "details": details})
        if not condition:
            dump_json(
                report_path, {"status": "failed", "checks": checks, "time": now()}
            )
            raise AssertionError(name)

    app.load_vega()
    parsed = app.parse_all()
    check(
        "sei_fonti_conversione_reale",
        parsed["success"] == 6 and parsed["errors"] == 0,
        parsed,
    )
    evidence = app.evidence()
    fields = [e for e in evidence if e["type"] == "xml_field"]
    check("forms_quattro_item", len(fields) == 4)
    check(
        "forms_operation_calls",
        any(
            e["type"] == "xml_dependency"
            and e["data"].get("target") == "PRC_PRENOTA_ARTICOLO"
            for e in evidence
        ),
    )
    check(
        "sql_nessuna_colonna_inventata",
        not any(
            e["data"].get("target")
            in {"ARTICOLO.ID_RICHIESTA", "ARTICOLO.RICHIESTA_RICAMBIO"}
            for e in evidence
        ),
    )
    check(
        "excel_manifest_e_docling",
        any(e["type"] == "excel_region" for e in evidence)
        and any(e["kind"] == "chunk" and e["path"].endswith(".xlsx") for e in evidence),
    )
    k.derive()
    check("nessun_merge_senza_review", k.merge()["created"] == 0)
    app.store.configure({"automatic_policies": list(POLICIES.values())})
    k.auto_review()
    k.merge()
    check("log_nessun_falso_conflitto", not k.conflicts())
    original = export.snapshot()
    technical = ai.select("technical_extraction")
    domain = ai.select("domain_interpretation")
    check(
        "ai_policy_distinte",
        any("already_confirmed" in i["reason_codes"] for i in technical["items"])
        and any(
            i["coverage"] == "confirmed" and i["outcome"] == "included"
            for i in domain["items"]
        ),
    )
    package_a = ai.package(domain["id"])
    package_b = ai.package(ai.select("domain_interpretation", max_evidence=2)["id"])
    manual = next(
        e for e in evidence if e["kind"] == "chunk" and e["path"].endswith(".docx")
    )
    excel = next(
        e for e in evidence if e["kind"] == "chunk" and e["path"].endswith(".xlsx")
    )
    quote_a = "Una richiesta P1 deve essere presa in carico entro 30 minuti."
    quote_b = next(line for line in excel["text"].splitlines() if "| P1 " in line)

    def proposal(e, quote, value):
        return {
            "candidate_id": "candidate_001",
            "record_type": "candidate_fact",
            "source_revision_id": e["revision_id"],
            "evidence_id": e["id"],
            "evidence_text": quote,
            "assertion_type": "inferred",
            "confidence": "medium",
            "fact_type": "business_rule",
            "entity_name": "Priorità P1",
            "property_name": "presa_in_carico_minuti",
            "property_value": value,
        }

    responses = [proposal(manual, quote_a, 30), proposal(excel, quote_b, 60)]
    response_dir = report_path.parent / "vega_ai_controllata"
    response_dir.mkdir(parents=True, exist_ok=True)
    batches = []
    ids = []
    for i, (pkg, payload) in enumerate(zip([package_a, package_b], responses), 1):
        text = json.dumps(payload, ensure_ascii=False) + "\n"
        (response_dir / f"risposta_{i:02d}.jsonl").write_text(text, encoding="utf-8")
        result = ai.import_response(pkg["id"], text)
        batches.append(result["batch_id"])
        ids.extend(result["candidate_ids"])
    check(
        "ai_simulata_importata_pending",
        all(c["state"] == "pending" for c in k.candidates() if c["id"] in ids),
        {"simulation": True, "external_model_called": False},
    )
    k.review_many(
        ids,
        "confirmed",
        actor_id="vega-m3-test",
        reason="Output controllato del laboratorio, citazioni verificate.",
    )
    check("ai_review_distinta_da_merge", export.snapshot()["hash"] == original["hash"])
    k.merge(batches)
    k.reconcile()
    after = export.snapshot()
    check(
        "ai_inclusa_nel_dsl",
        after["counts"]["facts"] == original["counts"]["facts"] + 2,
    )
    conflicts = k.conflicts()
    check(
        "conflitto_reale_p1",
        len(conflicts) == 1
        and {conflicts[0]["left_value"], conflicts[0]["right_value"]} == {30, 60},
        conflicts,
    )
    diff = export.diff(original["id"], after["id"])
    check("diff_con_provenienza", diff["count"] > 0)
    t = Temporal(app)
    raw = t.extract(manual["revision_id"])
    result = t.consolidate("source_revision", manual["revision_id"])
    check(
        "temporalita_pending",
        raw["count"] > 0
        and bool(result["proposals"])
        and all(
            c["state"] == "pending"
            for c in k.candidates()
            if c["record_type"] == "temporal_interval"
        ),
    )
    fact = next(
        o
        for o in k.objects()
        if o["kind"] == "fact" and o["payload"]["entity_name"] == "Priorità P1"
    )
    date_evidence = t.add_raw(
        manual["revision_id"],
        "fact",
        fact["id"],
        [
            {
                "source_key": "vega_validity",
                "raw_value": "2026-09",
                "date_role": "competence_year",
                "source_format": "controlled_test",
                "warnings": ["simulation_requires_review"],
            }
        ],
    )
    proposed = t.propose(manual["revision_id"], "fact", fact["id"], date_evidence)
    k.review_many(proposed["candidate_ids"], "confirmed", actor_id="vega-m3-test")
    k.merge()
    final = export.snapshot()
    graph = export.graph(final["id"], dynamic=True)
    check("gexf_dinamico_validato", bool(graph["files"]), graph)
    final_hash = final["hash"]
    reopened = Application(workspace)
    check("riavvio_persistenza", Exports(reopened).snapshot()["hash"] == final_hash)
    repeated = app.parse_all()
    check("ripresa_pipeline_cache", all(r.get("cached") for r in repeated["results"]))
    check("merge_idempotente", k.merge()["created"] == 0)
    check(
        "integrita_sqlite",
        app.store.one("PRAGMA integrity_check")["integrity_check"] == "ok",
    )
    report = {
        "status": "passed",
        "laboratory": "Vega M3",
        "timestamp": now(),
        "checks": checks,
        "summary": {
            "passed": len(checks),
            "sources": len(app.sources()),
            "evidence": len(app.evidence()),
            "counts": final["counts"],
        },
        "ai_response_mode": "controlled_simulation_not_external_model",
        "workspace": str(workspace.resolve()),
        "final_snapshot": final["id"],
        "baseline_commit": "c443b6a457b78229517a481fc5850dc8b44ecc3a",
    }
    dump_json(report_path, report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=Path("reports/vega_m3.json"))
    args = parser.parse_args()
    if (args.workspace / "registry.sqlite3").exists():
        parser.error(
            "Il laboratorio richiede un workspace nuovo per mantenere le precondizioni verificabili."
        )
    result = run(args.workspace, args.report)
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
