"""Reproducible real Docling PDF test. Models may download on the first run."""

import argparse
from pathlib import Path

from dslm3.common import dump_json, now
from dslm3.service import Application
from dslm3.temporal import Temporal

parser = argparse.ArgumentParser()
parser.add_argument("--workspace", type=Path, required=True)
parser.add_argument("--report", type=Path, default=Path("reports/pdf_result.json"))
args = parser.parse_args()
if (args.workspace / "registry.sqlite3").exists():
    parser.error("Use a fresh workspace.")
app = Application(args.workspace)
app.store.configure({"worker_timeout": 600, "worker_memory_mb": 8192})
fixture = Path(__file__).resolve().parents[1] / "tests/fixtures/pdf/manuale_vega.pdf"
rev = app.ingest("manuale_vega.pdf", fixture.read_bytes())["revision_id"]
result = app.parse(rev)
text = "\n".join(e["text"] for e in app.evidence())
passed = result["status"] == "success" and "VEGA" in text.upper()
temporal = Temporal(app)
temporal.extract(rev)
signals = temporal.raw("source_revision", rev)
validity = [r for r in signals if r["payload"]["date_role"] == "valid_from"]
passed = passed and any(r["payload"]["raw_value"] == "2026-09-01" for r in validity)
dump_json(
    args.report,
    {
        "status": "passed" if passed else "failed",
        "timestamp": now(),
        "result": result,
        "text": text,
        "fixture": fixture.name,
        "mocked": False,
        "valid_from_recognized": bool(validity),
    },
)
print(result["status"], len(text))
if not passed:
    raise SystemExit(1)
