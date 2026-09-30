"""Export local changes through isolated Git indexes; never stage the real index."""

from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

BASELINE = "a7117e061b393123e3b7b2ec22bf171687756447"
ROOT = Path(__file__).resolve().parents[1]


def git(*args, env=None):
    return subprocess.run(
        ["git", *args], cwd=ROOT, env=env, capture_output=True, check=True
    ).stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-dir", type=Path, required=True)
    args = parser.parse_args()
    reports = args.report_dir.resolve()
    patch_path = reports / "change.patch"
    delivery = reports / "delivery.json"
    # Existing patch files are historical transport containers, not source files.
    # Exclude them to avoid recursively embedding prior delivery patches.
    excluded = {
        p.relative_to(ROOT).as_posix()
        for p in (ROOT / "reports/deterministic_core").rglob("change.patch")
    }
    excluded |= {
        patch_path.relative_to(ROOT).as_posix(),
        delivery.relative_to(ROOT).as_posix(),
    }
    acceptance = json.loads((reports / "acceptance.json").read_text(encoding="utf-8"))
    if acceptance.get("status") != "passed":
        raise RuntimeError("Final acceptance must pass before delivery export")
    from dslm3.provenance import code_provenance

    if (
        code_provenance()["source_snapshot_sha256"]
        != acceptance["code_provenance"]["source_snapshot_sha256"]
    ):
        raise RuntimeError("Current application sources differ from tested snapshot")
    head = git("rev-parse", "HEAD").decode().strip()
    if head != acceptance["code_provenance"]["head"]:
        raise RuntimeError("HEAD differs from the tested starting commit")
    git("merge-base", "--is-ancestor", BASELINE, head)
    from acceptance_closure import (
        executable_snapshot,
        delivery_violations,
        delivery_paths,
    )

    if executable_snapshot(ROOT) != acceptance["executable_snapshot"]:
        raise RuntimeError("Tests/harness/application differ from tested snapshot")
    branch = git("branch", "--show-current").decode().strip()
    if branch != "feat/deterministic-core-upgrade":
        raise RuntimeError("Unexpected branch")
    git(
        "diff",
        "--exit-code",
        BASELINE,
        "--",
        "src/dslm3/resources/vega",
        "src/dslm3/vendor",
    )
    original_index = git("diff", "--cached", "--binary", "HEAD")
    paths = set(delivery_paths(ROOT))
    paths -= excluded
    paths = sorted(paths)
    if delivery_violations(paths):
        raise RuntimeError(
            "Runtime files in delivery: " + str(delivery_violations(paths))
        )
    for path in paths:
        if path not in {
            ".gitignore",
            "README.md",
            "START_HERE.md",
            "release_manifest.json",
        } and not path.startswith(
            ("src/", "tests/", "docs/", "scripts/", "reports/deterministic_core/")
        ):
            raise RuntimeError("Review unexpected path before exporting: " + path)
        if Path(path).suffix in {".sqlite3", ".db", ".pyc", ".whl"}:
            raise RuntimeError("Runtime/build artifact is not a deliverable: " + path)
    # These tiny indexes stay in the OS temporary directory as verification
    # evidence. No recursive deletion or checkout modification is performed.
    scratch = Path(tempfile.mkdtemp(prefix="dslm3_patch_indexes_")).resolve()
    changed_env = {**os.environ, "GIT_INDEX_FILE": str(scratch / "changed.index")}
    clean_env = {**os.environ, "GIT_INDEX_FILE": str(scratch / "baseline.index")}
    git("read-tree", BASELINE, env=changed_env)
    for start in range(0, len(paths), 40):
        git("add", "--", *paths[start : start + 40], env=changed_env)
    patch = git(
        "diff", "--cached", "--binary", "--full-index", BASELINE, env=changed_env
    )
    patch_path.write_bytes(patch)
    git("apply", "--cached", "--reverse", "--check", str(patch_path), env=changed_env)
    git("read-tree", BASELINE, env=clean_env)
    git("apply", "--cached", "--check", str(patch_path), env=clean_env)
    if git("diff", "--cached", "--binary", "HEAD") != original_index:
        raise RuntimeError("Real index changed unexpectedly")
    if git("branch", "--show-current").decode().strip() != branch:
        raise RuntimeError("Branch changed unexpectedly")
    inventory = []
    for path in paths:
        p = ROOT / path
        inventory.append(
            {
                "path": path,
                "size": p.stat().st_size if p.exists() else None,
                "working_file_sha256": hashlib.sha256(p.read_bytes()).hexdigest()
                if p.exists()
                else None,
                "operation": "present" if p.exists() else "deleted",
            }
        )
    result = {
        "status": "passed",
        "baseline": BASELINE,
        "tested_starting_head": head,
        "branch": branch,
        "patch": patch_path.relative_to(ROOT).as_posix(),
        "patch_bytes": len(patch),
        "patch_sha256": hashlib.sha256(patch).hexdigest(),
        "patch_file_count": len(paths),
        "files": inventory,
        "checks": {
            "baseline_forward_apply": "passed",
            "changed_reverse_apply": "passed",
            "real_index_unchanged": True,
            "branch_unchanged": True,
            "vega_and_vendor_unchanged": True,
        },
        "acceptance_source_snapshot": acceptance["code_provenance"][
            "source_snapshot_sha256"
        ],
        "excluded_transport_and_self_references": sorted(excluded),
        "temporary_indexes": str(scratch),
        "encoding": "Native Git binary output, no PowerShell text redirection; Git normalizes tracked text according to repository settings",
    }
    delivery.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {k: v for k, v in result.items() if k != "files"},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
