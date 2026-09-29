"""Identify the code actually executed, including uncommitted source changes."""

from pathlib import Path
import subprocess
from dslm3.common import digest


def code_provenance():
    package = Path(__file__).resolve().parent
    root = package.parents[1]
    files = sorted(
        p
        for p in package.rglob("*")
        if p.is_file()
        and "__pycache__" not in p.parts
        and p.suffix not in {".pyc", ".pyo"}
    )
    snapshot = digest(
        [
            ["dslm3/" + p.relative_to(package).as_posix(), digest(p.read_bytes())]
            for p in files
        ]
    )
    result = {"source_snapshot_sha256": snapshot, "source_file_count": len(files)}
    if root / "src/dslm3" != package:
        return {**result, "head": None, "branch": None, "dirty": None}
    try:

        def git(*args):
            return (
                subprocess.run(
                    ["git", "-C", str(root), *args], capture_output=True, check=True
                )
                .stdout.decode("utf-8")
                .strip()
            )

        result.update(
            head=git("rev-parse", "HEAD"),
            branch=git("branch", "--show-current"),
            dirty=bool(git("status", "--porcelain")),
        )
    except (OSError, subprocess.CalledProcessError):
        result.update(head=None, branch=None, dirty=None)
    return result
