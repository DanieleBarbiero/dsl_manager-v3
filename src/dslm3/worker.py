"""One isolated worker for every parser. No database writes, no arbitrary commands."""

from __future__ import annotations
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from dslm3.common import dump_json
from dslm3.parsers.documents import parse_document


def main():
    request = json.loads(Path(sys.argv[1]).read_text())
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    try:
        result = parse_document(
            Path(request["path"]),
            request["revision"],
            request["config"],
            request.get("schema"),
        )
        dump_json(Path(sys.argv[2]), asdict(result))
    except Exception as exc:
        dump_json(
            Path(sys.argv[2]),
            {
                "status": "error",
                "reason": getattr(exc, "reason", "parse_error"),
                "message": str(exc),
            },
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
