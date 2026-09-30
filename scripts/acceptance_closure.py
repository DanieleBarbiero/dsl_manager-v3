"""Evidence-backed G18 audit; may refresh delivery/docs after an unchanged test run.

Refreshing never executes or reattributes tests. Tested HEAD and executable file
hashes are immutable inputs; a changed source/test/harness requires a new run.
"""

from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

BASELINE = "a7117e061b393123e3b7b2ec22bf171687756447"
BRANCH = "feat/deterministic-core-upgrade"
PARENT = "fix/vega-quality-backlog"
COMMANDS = {
    "pip_check",
    "lint",
    "pytest",
    "vega_deterministic",
    "vega_integrated",
    "browser",
    "build",
    "wheel_install",
    "wheel_smoke",
}
DOCS = [
    "README.md",
    "START_HERE.md",
    "docs/rapporto_core_deterministico.md",
    "docs/copertura_deterministica.md",
    "docs/matrice_parita.md",
    "docs/oracle_v1_chiusura.md",
    "docs/oracle_v1_inventory.json",
    "docs/contratto_deterministico.md",
    "docs/verifica_core_windows.md",
    "docs/obiettivi.md",
    "docs/diario_tecnico.md",
    "docs/protocollo_ripresa.md",
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, check=True
    ).stdout


def paths(root):
    return sorted(
        {
            p.decode("utf-8")
            for p in git(
                root, "ls-files", "-z", "--cached", "--others", "--exclude-standard"
            ).split(b"\0")
            if p
        }
    )


def executable_snapshot(root):
    files = {
        p: sha((root / p).read_bytes())
        for p in paths(root)
        if (root / p).is_file()
        and (
            p.startswith(("src/", "tests/", "scripts/"))
            or p in {"pyproject.toml", "MANIFEST.in", "docs/oracle_v1_inventory.json"}
        )
    }
    return {"sha256": sha(json.dumps(files, sort_keys=True).encode()), "files": files}


def delivery_paths(root):
    """The delivery is the delta from the original baseline, plus new files."""
    return sorted(
        {
            p.decode("utf-8")
            for args in [
                ("diff", "--name-only", "-z", BASELINE),
                ("ls-files", "--others", "--exclude-standard", "-z"),
            ]
            for p in git(root, *args).split(b"\0")
            if p
        }
    )


def delivery_violations(names):
    forbidden = {
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
        ".pytest_cache",
        "runtime",
        "runtime_workspaces",
        "workspace",
        "wheel_install",
        "dist",
        "build",
    }
    return [
        p
        for p in names
        if forbidden & {s.lower() for s in Path(p).parts}
        or Path(p).suffix.lower()
        in {".db", ".sqlite", ".sqlite3", ".pyc", ".pyo", ".whl"}
        or Path(p).name.lower() in {".env", ".dslm3-workspaces.json"}
    ]


def unsupported_gate_claims(record, cases):
    unsupported = []
    for gate, result in {**record["gates"], **record["precision_tests"]}.items():
        if gate == "G18":
            continue
        if result["status"] != "passed" or (gate != "G16" and not result.get("tests")):
            unsupported.append(gate)
        for case in result.get("tests", []):
            if not cases.get(case["name"]) or case["status"] != "passed":
                unsupported.append(gate + ":" + case["name"])
    return unsupported


def audit(root, reports, record):
    checks = []

    def check(name, passed, evidence, mode="automated"):
        checks.append(
            {
                "name": name,
                "mode": mode,
                "status": "passed" if passed else "failed",
                "evidence": evidence,
            }
        )

    actual = executable_snapshot(root)
    head = git(root, "rev-parse", "HEAD").decode().strip()
    branch = git(root, "branch", "--show-current").decode().strip()
    parent = git(root, "rev-parse", PARENT).decode().strip()
    ancestor = (
        subprocess.run(
            ["git", "-C", str(root), "merge-base", "--is-ancestor", BASELINE, head]
        ).returncode
        == 0
    )
    check(
        "branch_baseline_tested_snapshot",
        branch == BRANCH
        and parent == BASELINE
        and ancestor
        and record["baseline"] == BASELINE
        and record["code_provenance"]["head"] == head
        and record["code_provenance"]["branch"] == branch
        and record.get("executable_snapshot") == actual
        and record.get("source_unchanged_during_run") is True,
        {
            "branch": branch,
            "original_baseline": BASELINE,
            "parent_branch": PARENT,
            "parent_head": parent,
            "head": head,
            "head_descends_from_baseline": ancestor,
            "tested_executable_sha256": record.get("executable_snapshot", {}).get(
                "sha256"
            ),
            "current_executable_sha256": actual["sha256"],
            "application_snapshot": record["code_provenance"]["source_snapshot_sha256"],
        },
    )

    names = paths(root)
    changes = git(root, "diff", "--name-only", "-z", BASELINE).split(b"\0")
    all_diff_check = subprocess.run(
        ["git", "-C", str(root), "diff", "--check", BASELINE], capture_output=True
    )
    (reports / "diff_check_all.txt").write_bytes(all_diff_check.stdout)
    diff_check = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "diff",
            "--check",
            BASELINE,
            "--",
            "src",
            "tests",
            "scripts",
            "docs",
            "README.md",
            "START_HERE.md",
            "release_manifest.json",
            ".gitignore",
        ],
        capture_output=True,
    )
    # Keep the readable source diff apart from generated JSON, logs and images.
    diff = git(root, "diff", "--binary", BASELINE, "--", "src", "tests", "scripts")
    (reports / "source_diff.patch").write_bytes(diff)
    (reports / "diff_stat.txt").write_bytes(git(root, "diff", "--stat", BASELINE))
    check(
        "diff_against_parent_and_original_baseline",
        diff_check.returncode == 0 and bool(changes),
        {
            "diff_check_output": diff_check.stdout.decode("utf-8", errors="replace"),
            "full_diff_check_exit_code": all_diff_check.returncode,
            "full_diff_check_output": "diff_check_all.txt",
            "whitespace_scope": "Code, tests, harness and documentation must be clean. Raw historical reports and patch framing are preserved verbatim; their whitespace diagnostics are recorded separately, not corrected or hidden.",
            "source_diff": "source_diff.patch",
            "source_diff_sha256": sha(diff),
            "stat": "diff_stat.txt",
            "tracked_changed_paths": [p.decode() for p in changes if p],
            "untracked_paths": [
                p.decode()
                for p in git(
                    root, "ls-files", "--others", "--exclude-standard", "-z"
                ).split(b"\0")
                if p
            ],
            "note": "Source diff covers tracked files; executable_snapshot inventories new files by SHA-256 too.",
        },
    )
    deliverable = delivery_paths(root)
    violations = delivery_violations(deliverable)
    baseline_runtime = delivery_violations(sorted(set(names) - set(deliverable)))
    check(
        "delivery_contains_no_accidental_runtime",
        not violations,
        {
            "scope": "Delta from the original baseline plus nonignored new files, identical to patch selection. Unchanged historical runtime is preserved in the checkout and excluded from delivery.",
            "file_count": len(deliverable),
            "unchanged_baseline_runtime_excluded": [
                {
                    "path": p,
                    "baseline_blob": git(root, "rev-parse", BASELINE + ":" + p)
                    .decode()
                    .strip(),
                }
                for p in baseline_runtime
            ],
            "violations": violations,
        },
    )

    relative = reports.relative_to(root).as_posix()
    docs = {
        p: sha((root / p).read_bytes()) if (root / p).is_file() else None for p in DOCS
    }
    report_text = (root / "docs/rapporto_core_deterministico.md").read_text(
        encoding="utf-8"
    )
    required = [BASELINE, BRANCH, head, "snapshot", "storich", relative]
    check(
        "required_documentation_and_provenance",
        all(docs.values()) and all(t in report_text for t in required),
        {"document_sha256": docs, "report_required_tokens": required},
    )
    manifest = json.loads((root / "release_manifest.json").read_text(encoding="utf-8"))
    historical_manifest = json.loads(git(root, "show", head + ":release_manifest.json"))
    preserved_release_fields = [
        "files",
        "file_count",
        "tests_passed",
        "vega_checks_passed",
        "release_date",
        "version",
    ]
    check(
        "release_manifest_historical_scope",
        manifest.get("status")
        == "historical_manifest_not_rebuilt_for_deterministic_core"
        and manifest.get("current_change_acceptance") == relative + "/acceptance.json"
        and manifest.get("current_change_report")
        == "docs/rapporto_core_deterministico.md"
        and "storica" in manifest.get("manifest_scope", "")
        and all(
            manifest.get(k) == historical_manifest.get(k)
            for k in preserved_release_fields
        ),
        {
            k: manifest.get(k)
            for k in [
                "status",
                "manifest_scope",
                "current_change_acceptance",
                "current_change_report",
            ]
        },
    )

    historical = "reports/deterministic_core/final/acceptance.json"
    historical_bytes = (root / historical).read_bytes()
    old = json.loads(historical_bytes)
    historical_unchanged = (
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "diff",
                "--quiet",
                head,
                "--",
                "reports/deterministic_core/final",
            ]
        ).returncode
        == 0
    )
    check(
        "current_and_historical_evidence_separated",
        reports != (root / historical).parent
        and old["code_provenance"]["head"] == BASELINE
        and old["code_provenance"]["dirty"] is True
        and historical_bytes == git(root, "show", head + ":" + historical)
        and historical_unchanged,
        {
            "historical_report": historical,
            "historical_sha256": sha(historical_bytes),
            "historical_tested_provenance": old["code_provenance"],
            "current_report": relative + "/acceptance.json",
            "note": "The historical dirty-tree run is not attributed to the present HEAD.",
        },
    )

    commands = {c["name"]: c for c in record["commands"]}
    missing = sorted(COMMANDS - commands.keys())
    machine_reports = [
        "pytest.xml",
        "vega_deterministic.json",
        "vega_integrated.json",
        "browser/browser_result.json",
        "wheel_smoke.json",
    ]
    unavailable = [p for p in machine_reports if not (reports / p).is_file()]
    if unavailable:
        check("required_machine_reports", False, {"missing": unavailable})
        return {"status": "failed", "checks": checks, "report": "closure_checks.json"}
    logs = {
        name: sha((reports / c["log"]).read_bytes())
        if (reports / c["log"]).is_file()
        else None
        for name, c in commands.items()
    }
    cases = {
        c.attrib["classname"] + "::" + c.attrib["name"]: not any(
            c.find(tag) is not None for tag in ["failure", "error", "skipped"]
        )
        for c in ET.parse(reports / "pytest.xml").iter("testcase")
    }
    unsupported_claims = unsupported_gate_claims(record, cases)
    if set(record["gates"]) != {f"G{i:02}" for i in range(1, 19)}:
        unsupported_claims.append("incomplete_gate_matrix")
    if set(record["precision_tests"]) != {
        f"{prefix}-{i:02}" for prefix in ["COV", "BIZ"] for i in range(1, 9)
    }:
        unsupported_claims.append("incomplete_precision_matrix")
    labs = {
        p: json.loads((reports / p).read_text(encoding="utf-8"))
        for p in [
            "vega_deterministic.json",
            "vega_integrated.json",
            "browser/browser_result.json",
        ]
    }
    lab_ok = all(v["status"] == "passed" for v in labs.values())
    lab_ok = lab_ok and len(labs["vega_deterministic.json"]["checks"]) >= 12
    lab_ok = lab_ok and all(
        v is True for v in labs["vega_deterministic.json"]["checks"].values()
    )
    lab_ok = lab_ok and len(labs["vega_integrated.json"]["checks"]) >= 19
    lab_ok = lab_ok and all(
        c["passed"] is True for c in labs["vega_integrated.json"]["checks"]
    )
    lab_ok = lab_ok and not labs["browser/browser_result.json"]["js_errors"]
    lab_ok = lab_ok and set(labs["browser/browser_result.json"]["viewports"]) == {
        "1440x1080",
        "390x844",
    }
    for name in ["vega_deterministic.json", "vega_integrated.json"]:
        lab_ok = (
            lab_ok
            and labs[name]["code_provenance"]["source_snapshot_sha256"]
            == record["code_provenance"]["source_snapshot_sha256"]
        )
    totals = {"passed": sum(cases.values()), "failed": 0, "skipped": 0}
    check(
        "passed_gates_have_current_evidence",
        not missing
        and all(logs.values())
        and not unsupported_claims
        and bool(cases)
        and all(cases.values())
        and record["test_totals"] == totals
        and lab_ok
        and all(c["exit_code"] == 0 for c in commands.values()),
        {
            "missing_commands": missing,
            "command_log_sha256": logs,
            "unsupported_claims": unsupported_claims,
            "junit_sha256": sha((reports / "pytest.xml").read_bytes()),
            "test_totals": record["test_totals"],
            "lab_report_sha256": {p: sha((reports / p).read_bytes()) for p in labs},
            "lab_content_checks": lab_ok,
        },
    )

    wheel = json.loads((reports / "wheel_smoke.json").read_text(encoding="utf-8"))
    check(
        "installed_wheel_matches_tested_sources",
        wheel["status"] == "passed"
        and wheel["parsed_sources"] == 6
        and wheel["coverage_complete"] is True
        and wheel["code_provenance"]["head"] is None
        and wheel["code_provenance"]["source_snapshot_sha256"]
        == record["code_provenance"]["source_snapshot_sha256"],
        {
            "report": "wheel_smoke.json",
            "sha256": sha((reports / "wheel_smoke.json").read_bytes()),
            "installed_provenance": wheel["code_provenance"],
        },
    )

    manual_path = root / "docs/revisione_chiusura_core.json"
    manual = (
        json.loads(manual_path.read_text(encoding="utf-8"))
        if manual_path.exists()
        else {}
    )
    for name in [
        "diff_readability_and_scope",
        "oracle_mapping_and_exceptions",
        "documentation_claims",
    ]:
        entry = manual.get("checks", {}).get(name, {})
        check(
            name,
            manual.get("executable_sha256") == actual["sha256"]
            and entry.get("status") == "reviewed"
            and manual.get("document_sha256") == docs
            and bool(entry.get("evidence"))
            and bool(manual.get("reviewer")),
            {
                "record": "docs/revisione_chiusura_core.json",
                "reviewer": manual.get("reviewer"),
                **entry,
            },
            "manual",
        )
    return {
        "status": "passed"
        if all(c["status"] == "passed" for c in checks)
        else "failed",
        "checks": checks,
        "report": "closure_checks.json",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-dir", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    reports = args.report_dir.resolve()
    record = json.loads((reports / "acceptance.json").read_text(encoding="utf-8"))
    result = audit(root, reports, record)
    from dslm3.common import dump_json
    from core_acceptance import write_markdown

    dump_json(reports / "closure_checks.json", result)
    record["gates"]["G18"] = {
        "status": result["status"],
        "report": "closure_checks.json",
    }
    record["status"] = (
        "passed"
        if all(g["status"] == "passed" for g in record["gates"].values())
        else "failed"
    )
    dump_json(reports / "acceptance.json", record)
    write_markdown(reports, record)
    print(
        json.dumps(
            {
                "status": result["status"],
                "checks": {c["name"]: c["status"] for c in result["checks"]},
            },
            indent=2,
        )
    )
    return 0 if record["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
