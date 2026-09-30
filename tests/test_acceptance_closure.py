"""Negative controls for the final gate, independent of command exit codes."""

import importlib.util
from pathlib import Path
import subprocess

import pytest

spec = importlib.util.spec_from_file_location(
    "closure_gate", Path(__file__).parents[1] / "scripts/acceptance_closure.py"
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


@pytest.mark.parametrize(
    "path",
    [
        "runtime/workspace.json",
        ".venv/Scripts/python.exe",
        "reports/workspace.sqlite",
        "tests/__pycache__/x.pyc",
        "dist/dslm3.whl",
        "src/leaked.db",
    ],
)
def test_g18_rejects_runtime_in_delivery(path):
    assert gate.delivery_violations(
        ["tests/fixtures/source.xlsx", "docs/report.md", path]
    ) == [path]


def test_g18_rejects_pass_without_matching_current_test():
    record = {
        "gates": {
            "G05": {
                "status": "passed",
                "tests": [{"name": "trigger", "status": "passed"}],
            }
        },
        "precision_tests": {},
    }
    assert gate.unsupported_gate_claims(record, {"trigger": True}) == []
    assert gate.unsupported_gate_claims(record, {}) == ["G05:trigger"]
    assert gate.unsupported_gate_claims(record, {"trigger": False}) == ["G05:trigger"]
    record["gates"]["G05"]["tests"] = []
    assert gate.unsupported_gate_claims(record, {"unrelated": True}) == ["G05"]


def test_g18_snapshot_covers_new_tests_and_harness_beyond_application(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=True)
    for path in ["src/app.py", "tests/test_app.py", "scripts/check.py"]:
        dest = tmp_path / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("# first\n", encoding="utf-8")
    original = gate.executable_snapshot(tmp_path)
    (tmp_path / "tests/test_app.py").write_text(
        "# changed expectation\n", encoding="utf-8"
    )
    changed_test = gate.executable_snapshot(tmp_path)
    assert original["sha256"] != changed_test["sha256"]
    assert original["files"]["src/app.py"] == changed_test["files"]["src/app.py"]
    (tmp_path / "scripts/check.py").write_text("# changed checker\n", encoding="utf-8")
    assert gate.executable_snapshot(tmp_path)["sha256"] != changed_test["sha256"]


def test_g18_delivery_scope_rejects_new_or_changed_runtime_but_preserves_baseline(
    monkeypatch, tmp_path
):
    changes = ["src/app.py"]
    new = ["tests/test_new.py"]

    def git_output(root, *args):
        assert root == tmp_path
        return (
            b"\0".join(p.encode() for p in (changes if args[0] == "diff" else new))
            + b"\0"
        )

    monkeypatch.setattr(gate, "git", git_output)
    assert gate.delivery_paths(tmp_path) == ["src/app.py", "tests/test_new.py"]
    assert not gate.delivery_violations(gate.delivery_paths(tmp_path))
    # A tracked baseline database is outside the delta only while unchanged.
    changes.append("workspace/registry.sqlite3")
    assert gate.delivery_violations(gate.delivery_paths(tmp_path)) == [
        "workspace/registry.sqlite3"
    ]
    changes.pop()
    new.append("workspace/registry.sqlite3-wal")
    assert gate.delivery_violations(gate.delivery_paths(tmp_path)) == [
        "workspace/registry.sqlite3-wal"
    ]
