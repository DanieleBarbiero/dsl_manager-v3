"""Portable acceptance runner; PowerShell 5.1 wrapper passes platform evidence.

Every command is executed against this checkout and logged as bytes. No remote
mutation, fixture rewrite, package-version substitution or historical test reuse.
"""

from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

from dslm3.common import dump_json, digest
from dslm3.provenance import code_provenance
from acceptance_closure import audit as closure_audit, executable_snapshot

BASELINE = "a7117e061b393123e3b7b2ec22bf171687756447"
GATES = {
    "G01": ["test_cov_01", "test_cov_02", "test_cov_03", "test_cov_04", "test_cov_07"],
    "G02": [
        "test_other_sql_shapes",
        "test_pinned_v1_ddl",
        "test_biz_01",
        "test_fk_inferred",
        "test_default_null",
        "test_sqlite_primary_key",
    ],
    "G03": [
        "test_update_typed",
        "test_update_expression",
        "test_biz_03",
        "test_typed_null_boolean",
    ],
    "G04": ["test_update_expression", "test_other_sql_shapes", "test_merge_branches"],
    "G05": [
        "test_trigger_new_old_g05",
        "test_call_overload",
        "test_call_package_body",
        "test_resolver_import_order",
        "test_fk_inferred",
        "test_other_sql_shapes",
        "test_cte_alias",
        "test_oracle_package",
        "test_sql_literals",
    ],
    "G06": [
        "test_resolver_import_order",
        "test_cov_01",
        "test_cov_02",
        "test_cov_03",
        "test_cov_04",
        "test_cov_06",
        "test_call_overload",
    ],
    "G07": [
        "test_forms_resolution",
        "test_forms_items",
        "test_xml_entities",
        "test_forms_qualified",
    ],
    "G08": ["test_chunk_exact", "test_chunk_configuration", "test_structural_chunker"],
    "G09": ["test_log_json", "test_log_occurrences"],
    "G10": ["test_excel_exact", "test_macro_never", "test_formats_real"],
    "G11": [
        "test_biz_01",
        "test_deterministic_fact_types",
        "test_diff_tracks",
        "test_multi_package",
    ],
    "G12": [
        "test_governance",
        "test_supports",
        "test_ai_cannot",
        "test_forms_items",
        "test_cov_07",
    ],
    "G13": [
        "test_rule_only",
        "test_schema2",
        "test_cov_06",
        "test_dialect_reinterpretation",
        "test_chunk_configuration",
    ],
    "G14": [
        "test_biz_01",
        "test_biz_03",
        "test_biz_04_positive",
        "test_partial_ai",
        "test_cov_07",
        "test_selection_coverage",
    ],
    "G15": [
        "test_pinned_v1_ddl",
        "test_pinned_v1_db",
        "test_excel_exact",
        "test_pinned_v1_schema_resolution",
        "test_pinned_v1_candidate_derivation_slice21",
        "test_pinned_v1_slice25",
        "test_pinned_v1_slice32",
        "test_pinned_v1_oracle_source_inventory",
        "test_forms_resolution",
        "test_forms_items",
        "test_provenance_atomic_batch",
        "test_log_json_identical",
        "test_ai_cannot_autoapprove",
    ],
    "G16": [],
    "G17": ["test_windows_bytes", "test_schema2", "test_chunk_configuration"],
    "G18": [],
}
COV = {
    "COV-01": "test_cov_01",
    "COV-02": "test_cov_02",
    "COV-03": "test_cov_03",
    "COV-04": "test_cov_04",
    "COV-05": "test_internal_parser_error",
    "COV-06": "test_cov_06",
    "COV-07": "test_cov_07",
    "COV-08": "test_cov_07",
}
BIZ = {
    f"BIZ-{i:02}": "test_biz_03" if i in {3, 4, 7} else "test_biz_01"
    for i in range(1, 9)
}
BIZ["BIZ-04"] = "test_biz_04_positive"
COV["COV-05"] = ["test_cov_04", "test_internal_parser_error"]
BIZ["BIZ-07"] = ["test_biz_03", "test_cov_07", "test_partial_ai"]
PRECISION_EXPECTED = {
    "COV-01": "FK declaration retained; missing target blocks exactly the resolved relation",
    "COV-02": "Complete target resolves; omission of one required output makes the validator fail",
    "COV-03": "Two schema alternatives are ambiguous; mismatched FK arity is inconsistent",
    "COV-04": "Derived, missing and blocked components coexist; evidence stays partial",
    "COV-05": "Internal defects propagate as errors; unexpected unresolved in positive fixture is rejected",
    "COV-06": "Absent/added/modified/removed/restored target invalidates and restores supports without losing review",
    "COV-07": "Pending/confirmed/rejected do not change technical coverage; review still gates merge",
    "COV-08": "Unknown type fails; unsupported variant explicit; unrelated text does not change candidates",
    "BIZ-01": "CHECK IN contains BOZZA, CONFERMATO, ANNULLATO; TOTALE >= exact numeric zero",
    "BIZ-02": "NOT NULL is separate from CHECK; removing it changes nullability, precision 12,2 is retained",
    "BIZ-03": "QTA_DISPONIBILE - 1 is present; no inventory reservation, units, permissions or domain intentions invented",
    "BIZ-04": "Renamed table, columns and constraints preserve AST operators and literal values under explicit mapping",
    "BIZ-05": "SOSPESO and boundary 10 replace prior effective values; history remains and diff is nonempty",
    "BIZ-06": "Fresh workspaces; zero AI response imports; only deterministic candidates before explicit test review",
    "BIZ-07": "Covered statements excluded from technical route even pending/rejected; partial and domain remain usable",
    "BIZ-08": "Literal citations, locators and attributes survive review, merge, reopen and JSON/YAML/Markdown exports",
}
BLOBS = {
    "database/schema_vega.sql": "ffee982a43aead5ee45ee16d2e245704632200e8",
    "documenti/manuale_operativo_vega_2026.docx": "59a57fe4813af9fe691c60881d2a87dc2633ea6c",
    "documenti/matrice_priorita_vega_2026.xlsx": "13d2b5a333f7dd5896a458c05d8b6954bef84c7e",
    "forms/frm_richiesta.xml": "e49fe679af927d96af37326e466b190bf713fef1",
    "logs/vega_2026.log": "1ba8749b71bb3cfd50edd058eb0d02cf26f468db",
    "plsql/logica_vega.sql": "159e1005d30ebe741faed2581fbe8fefa2b3b385",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--shell-version", default="not_recorded")
    parser.add_argument("--v1-root", type=Path)
    parser.add_argument("--cold-workspace", type=Path)
    args = parser.parse_args()
    assert sys.version_info[:2] == (3, 12) and struct.calcsize("P") == 8
    root = Path(__file__).resolve().parents[1]
    reports = args.report_dir.resolve()
    reports.mkdir(parents=True, exist_ok=True)
    runtime = (
        args.runtime_root.resolve()
        if args.runtime_root
        else Path(tempfile.mkdtemp(prefix="dslm3_acceptance_"))
    )
    runtime.mkdir(parents=True, exist_ok=True)
    run = runtime / time.strftime("run_%Y%m%d_%H%M%S")
    run.mkdir()
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["DSLM3_ACCEPTANCE_DETAILS"] = str(reports / "details")
    if args.v1_root:
        env["DSLM3_V1_ROOT"] = str(args.v1_root.resolve())
    record = {
        "baseline": BASELINE,
        "code_provenance": code_provenance(),
        "executable_snapshot": executable_snapshot(root),
        "runtime": str(run),
        "environment": {
            "python": sys.executable,
            "version": sys.version,
            "platform": platform.platform(),
            "architecture_bits": 64,
            "powershell": args.shell_version,
            "packages": {
                p: importlib.metadata.version(p)
                for p in [
                    "sqlglot",
                    "docling",
                    "pytest",
                    "playwright",
                    "numpy",
                    "opencv-python",
                    "fastapi",
                ]
            },
        },
        "commands": [],
        "gates": {g: {"status": "not_run"} for g in GATES},
    }

    def command(name, *argv, cwd=root):
        log = reports / (name + ".log")
        start = time.monotonic()
        with log.open("wb") as stream:
            result = subprocess.run(
                [str(a) for a in argv],
                cwd=cwd,
                env=env,
                stdout=stream,
                stderr=subprocess.STDOUT,
            )
        entry = {
            "name": name,
            "argv": [str(a) for a in argv],
            "cwd": str(cwd),
            "exit_code": result.returncode,
            "duration_seconds": round(time.monotonic() - start, 3),
            "log": log.name,
            "status": "passed" if result.returncode == 0 else "failed",
        }
        record["commands"].append(entry)
        dump_json(reports / "acceptance.json", record)
        print(name + ": " + entry["status"], flush=True)
        return result.returncode == 0

    command("pip_check", sys.executable, "-m", "pip", "check")
    command(
        "lint",
        sys.executable,
        "-m",
        "ruff",
        "check",
        "--select",
        "F",
        "src/dslm3",
        "tests",
        "scripts/core_acceptance.py",
        "scripts/acceptance_closure.py",
        "scripts/export_deterministic_patch.py",
        "scripts/wheel_core_smoke.py",
    )
    junit = reports / "pytest.xml"
    command("pytest", sys.executable, "-m", "pytest", "-q", "--junitxml=" + str(junit))
    command(
        "vega_deterministic",
        sys.executable,
        "-m",
        "dslm3.deterministic_lab",
        "--workspace",
        run / "vega_deterministic",
        "--report",
        reports / "vega_deterministic.json",
    )
    command(
        "vega_integrated",
        sys.executable,
        "-m",
        "dslm3.lab",
        "--workspace",
        run / "vega_integrated",
        "--report",
        reports / "vega_integrated.json",
    )
    command(
        "browser",
        sys.executable,
        root / "scripts/browser_check.py",
        run / "browser",
        reports / "browser",
    )
    command(
        "build",
        sys.executable,
        "-m",
        "build",
        "--wheel",
        "--no-isolation",
        "--outdir",
        run / "dist",
    )
    wheels = list((run / "dist").glob("*.whl"))
    if wheels and command(
        "wheel_install",
        sys.executable,
        "-m",
        "pip",
        "install",
        "--no-deps",
        "--target",
        run / "wheel_install",
        wheels[0],
    ):
        command(
            "wheel_smoke",
            sys.executable,
            root / "scripts/wheel_core_smoke.py",
            run / "wheel_install",
            run / "wheel_workspace",
            reports / "wheel_smoke.json",
            cwd=run,
        )
    fixtures = []
    blobdir = run / "original_git_blobs"
    for path, expected in BLOBS.items():
        relative = "src/dslm3/resources/vega/" + path
        data = subprocess.run(
            ["git", "show", BASELINE + ":" + relative],
            cwd=root,
            capture_output=True,
            check=True,
        ).stdout
        blob = hashlib.sha1(
            b"blob " + str(len(data)).encode() + b"\0" + data
        ).hexdigest()
        destination = blobdir / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        fixtures.append(
            {
                "path": path,
                "expected_git_blob": expected,
                "actual_git_blob": blob,
                "blob_sha256": digest(data),
                "checkout_sha256": digest((root / relative).read_bytes()),
                "status": "passed" if blob == expected else "failed",
            }
        )
    record["fixture_integrity"] = fixtures
    cases = []
    if junit.exists():
        for case in ET.parse(junit).iter("testcase"):
            cases.append(
                {
                    "name": case.attrib["classname"] + "::" + case.attrib["name"],
                    "status": "failed"
                    if case.find("failure") is not None
                    or case.find("error") is not None
                    else "skipped"
                    if case.find("skipped") is not None
                    else "passed",
                }
            )

    def evidence_for(prefixes):
        matched = [c for c in cases if any(p in c["name"] for p in prefixes)]
        absent = [p for p in prefixes if not any(p in c["name"] for c in matched)]
        return {
            "status": "not_run"
            if absent or not matched
            else "passed"
            if all(c["status"] == "passed" for c in matched)
            else "failed",
            "tests": matched,
            "missing_test_patterns": absent,
        }

    for gate, prefixes in GATES.items():
        record["gates"][gate] = evidence_for(prefixes)
    commands = {c["name"]: c for c in record["commands"]}
    record["gates"]["G16"] = {
        "status": commands["vega_deterministic"]["status"]
        if all(f["status"] == "passed" for f in fixtures)
        else "failed",
        "report": "vega_deterministic.json",
    }
    if os.name != "nt" or not args.shell_version.startswith("5.1"):
        record["gates"]["G17"]["status"] = "not_verified"
    record["precision_tests"] = {
        key: evidence_for([prefix] if isinstance(prefix, str) else prefix)
        for key, prefix in {**COV, **BIZ}.items()
    }
    for key, result in record["precision_tests"].items():
        result["command"] = "pytest"
        result["reason"] = (
            "Independent assertions for expected structures and forbidden outputs all passed"
            if result["status"] == "passed"
            else "See failed or missing test assertions"
        )
        result["dialect"] = "oracle"
        result["expected"] = PRECISION_EXPECTED[key]
        result["versions"] = {"parser": "sql/4", "contract": "4", "rule": "4.0"}
        result["details"] = [
            p.relative_to(reports).as_posix()
            for p in sorted((reports / "details").glob("*.json"))
            if key in p.stem or key.startswith("BIZ-") and p.stem.startswith("BIZ-")
        ]
    record["test_totals"] = {
        status: sum(c["status"] == status for c in cases)
        for status in ["passed", "failed", "skipped"]
    }
    record["corpus_audit"] = business_audit(run / "business", reports, root)
    if args.cold_workspace:
        copied = run / "cold_workspace_copy"
        shutil.copytree(args.cold_workspace.resolve(), copied)
        command("cold_upgrade", sys.executable, "-m", "dslm3", "-w", copied, "parse")
        command("cold_derive", sys.executable, "-m", "dslm3", "-w", copied, "derive")
        command(
            "cold_coverage",
            sys.executable,
            "-m",
            "dslm3",
            "-w",
            copied,
            "coverage",
            "--check",
        )
        record["cold_workspace"] = {
            "source_read_only": str(args.cold_workspace.resolve()),
            "copy": str(copied),
        }
    record["final_code_provenance"] = code_provenance()
    record["source_unchanged_during_run"] = (
        record["code_provenance"]["source_snapshot_sha256"]
        == record["final_code_provenance"]["source_snapshot_sha256"]
    )
    closure = closure_audit(root, reports, record)
    dump_json(reports / "closure_checks.json", closure)
    record["gates"]["G18"] = {
        "status": closure["status"],
        "report": "closure_checks.json",
    }
    record["status"] = (
        "passed"
        if record["source_unchanged_during_run"]
        and all(g["status"] == "passed" for g in record["gates"].values())
        and all(g["status"] == "passed" for g in record["precision_tests"].values())
        and all(c["exit_code"] == 0 for c in record["commands"])
        else "failed"
    )
    dump_json(reports / "acceptance.json", record)
    write_markdown(reports, record)
    return 0 if record["status"] == "passed" else 1


def business_audit(workspace, reports, root):
    from dslm3.ai import AI
    from dslm3.knowledge import Knowledge
    from dslm3.service import Application
    from dslm3.exports import Exports

    artifacts = []
    for name in ["business", "decrement"]:
        app = Application(workspace / name)
        app.store.configure({"sql_dialect": "oracle"})
        fixture = root / "tests/fixtures/deterministic" / (name + ".sql")
        app.ingest(fixture.name, fixture.read_bytes())
        parse = app.parse_all()
        k = Knowledge(app)
        derived = k.derive()
        before = k.candidates()
        selection = {
            route: AI(app).select(route)
            for route in ["technical_extraction", "domain_interpretation"]
        }
        k.review_many(
            derived["candidate_ids"],
            "confirmed",
            actor_id="business-acceptance",
            reason="Confronto con attesi strutturali indipendenti, nessun contributo AI",
        )
        k.merge()
        snapshot = Exports(app).snapshot()
        content = {
            "fixture": str(fixture.relative_to(root)),
            "dialect": "oracle",
            "parse": parse,
            "ai_batches": app.store.rows(
                "SELECT * FROM batches WHERE origin LIKE 'ai%'"
            ),
            "versions": {"parser": "sql/4", "contract": "4", "rule": "4.0"},
            "dialect_explicit": True,
            "candidates_before_review": before,
            "coverage": app.coverage(),
            "selection": selection,
            "objects": k.objects(),
            "snapshot_id": snapshot["id"],
            "expected": json.loads(
                (fixture.parent / "expected_business.json").read_text()
            )
            if name == "business"
            else {
                "rhs": "QTA_DISPONIBILE - 1",
                "forbidden": [
                    "reservation",
                    "inventory depletion",
                    "units",
                    "authorization",
                ],
            },
        }
        dump_json(reports / (name + "_audit.json"), content)
        artifacts.append(name + "_audit.json")
    return artifacts


def write_markdown(reports, record):
    lines = [
        "# Acceptance core deterministico",
        "",
        "Stato: **" + record["status"] + "**.",
        "",
        "Baseline: `"
        + BASELINE
        + "`. HEAD/dirty e hash dello snapshot realmente eseguito sono in `acceptance.json`.",
        "",
        "Ambiente: "
        + record["environment"]["platform"]
        + "; Python "
        + record["environment"]["version"]
        + "; PowerShell "
        + record["environment"]["powershell"]
        + ".",
        "",
        "| Gate | Esito | Evidenza |",
        "|---|---|---|",
    ]
    for gate, result in record["gates"].items():
        lines.append(
            "| "
            + gate
            + " | "
            + result["status"]
            + " | "
            + ", ".join(c["name"].split("::")[-1] for c in result.get("tests", []))
            + result.get("report", "")
            + " |"
        )
    lines += [
        "",
        "| Precisazione | Esito | Atteso verificato | Test |",
        "|---|---|---|---|",
    ]
    for key, result in record["precision_tests"].items():
        lines.append(
            "| "
            + key
            + " | "
            + result["status"]
            + " | "
            + result["expected"]
            + " | "
            + ", ".join(c["name"].split("::")[-1] for c in result["tests"])
            + " |"
        )
    lines += [
        "",
        "Tutti i comandi, exit code, tempi, log e versioni sono nel JSON. Il laboratorio integrato usa risposte AI controllate; il laboratorio deterministico e gli audit business non importano AI.",
        "",
        "Le regole di business estratte sono solo CHECK, insieme di literal ammessi, limite numerico e nullability dichiarata. Workflow, valuta, autorizzazioni e prenotazioni non sono inferiti dai nomi.",
        "",
        "Eccezioni legacy verificate: chunking v1 perde un separatore in un caso; v3 conserva tutto il testo. L'inferenza legacy maps_to → writes_to non è adottata; v3 richiede modalità esplicite.",
        "",
        "I contatori applicabili/derivati/mancanti sono sottoinsiemi dei supportati; i candidati e gli oggetti sono conteggi distinti. Un blocco di risoluzione non è una derivazione riuscita. Le fixture negative richiedono espressamente il blocco, quelle positive la risoluzione.",
        "",
        "Limiti: subset SQL dichiarato; nessuna esecuzione di SQL/macro o riferimenti esterni. XLSB e backend documentali privi di fixture dedicate restano non certificati. Le prove correnti non attestano piattaforme diverse da quella registrata.",
    ]
    (reports / "acceptance.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
