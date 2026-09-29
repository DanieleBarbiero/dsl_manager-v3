"""Export local changes through isolated Git indexes; never stage the real index."""

from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

BASELINE = "a7117e061b393123e3b7b2ec22bf171687756447"
ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports/deterministic_core"
PATCH = REPORTS / "change.patch"
DELIVERY = REPORTS / "delivery.json"
EXCLUDED = {PATCH.relative_to(ROOT).as_posix(), DELIVERY.relative_to(ROOT).as_posix()}


def git(*args, env=None):
    return subprocess.run(
        ["git", *args], cwd=ROOT, env=env, capture_output=True, check=True
    ).stdout


def main():
    acceptance = json.loads(
        (REPORTS / "final/acceptance.json").read_text(encoding="utf-8")
    )
    if acceptance.get("status") != "passed":
        raise RuntimeError("Final acceptance must pass before delivery export")
    from dslm3.provenance import code_provenance

    if (
        code_provenance()["source_snapshot_sha256"]
        != acceptance["code_provenance"]["source_snapshot_sha256"]
    ):
        raise RuntimeError("Current application sources differ from tested snapshot")
    if git("rev-parse", "HEAD").decode().strip() != BASELINE:
        raise RuntimeError("HEAD differs from the requested baseline")
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
    paths = set()
    for argv in (
        ("diff", "--name-only", "-z", "HEAD"),
        ("ls-files", "--others", "--exclude-standard", "-z"),
    ):
        paths.update(p.decode("utf-8") for p in git(*argv).split(b"\0") if p)
    paths -= EXCLUDED
    paths = sorted(paths)
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
    PATCH.write_bytes(patch)
    git("apply", "--cached", "--reverse", "--check", str(PATCH), env=changed_env)
    git("read-tree", BASELINE, env=clean_env)
    git("apply", "--cached", "--check", str(PATCH), env=clean_env)
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
                "size": p.stat().st_size,
                "working_file_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            }
        )
    result = {
        "status": "passed",
        "baseline": BASELINE,
        "branch": branch,
        "patch": PATCH.relative_to(ROOT).as_posix(),
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
        "excluded_self_references": sorted(EXCLUDED),
        "temporary_indexes": str(scratch),
        "encoding": "Native Git binary output, no PowerShell text redirection; Git normalizes tracked text according to repository settings",
    }
    DELIVERY.write_text(
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
