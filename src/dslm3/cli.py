from __future__ import annotations
import argparse
import json
import sys
import threading
import webbrowser
from pathlib import Path

from dslm3.common import DomainError
from dslm3.service import Application
from dslm3.web import dispatch


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="dslm3", description="DSL Manager — UI locale e fallback CLI"
    )
    parser.add_argument(
        "--workspace",
        "-w",
        default="workspace",
        help="Directory del workspace persistente",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="Avvia la UI web locale")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--no-browser", action="store_true")
    commands.add_parser("init", help="Crea workspace")
    commands.add_parser("status")
    commands.add_parser("vega", help="Carica le sei fonti Vega")
    ingest = commands.add_parser("scan")
    ingest.add_argument("directory", nargs="?")
    for name in [
        "parse",
        "derive",
        "auto-review",
        "merge",
        "reconcile",
        "pipeline",
        "temporal-extract",
        "package-all",
        "diagnostics",
    ]:
        p = commands.add_parser(name)
        if name == "parse":
            p.add_argument("--retry", action="store_true")
        if name == "merge":
            p.add_argument("--strict", action="store_true")
            p.add_argument("--batch", action="append", dest="batches")
    configure = commands.add_parser("profile")
    configure.add_argument("profile", choices=["conservative", "manual"])
    snapshot = commands.add_parser("snapshot")
    snapshot.add_argument("--schema-version", type=int, choices=[1, 2], default=2)
    snapshot.add_argument("--allow-incomplete", action="store_true")
    review = commands.add_parser("review")
    review.add_argument("ids", nargs="+")
    review.add_argument(
        "--outcome", choices=["confirmed", "rejected", "pending"], required=True
    )
    review.add_argument("--actor-id")
    review.add_argument("--reason", default="")
    select = commands.add_parser("select")
    select.add_argument(
        "--route",
        choices=["technical_extraction", "domain_interpretation"],
        default="domain_interpretation",
    )
    package = commands.add_parser("package")
    package.add_argument("selection_id")
    imp = commands.add_parser("ai-import")
    imp.add_argument("package_id")
    imp.add_argument("file")
    imp.add_argument("--allow-stale", action="store_true")
    graph = commands.add_parser("graph")
    graph.add_argument("snapshot_id")
    graph.add_argument("--dynamic", action="store_true")
    graph.add_argument(
        "--mode", choices=["strict", "omit", "separate"], default="strict"
    )
    diff = commands.add_parser("diff")
    diff.add_argument("before")
    diff.add_argument("after")
    diff.add_argument("--cross-schema", action="store_true")
    action = commands.add_parser(
        "action", help="Accesso JSON a tutte le operazioni, identiche alla UI"
    )
    action.add_argument("operation")
    action.add_argument("--args", default="{}")
    action.add_argument("--args-file")
    args = parser.parse_args(argv)
    app = Application(args.workspace)
    try:
        if args.command == "serve":
            import uvicorn
            from dslm3.web import create_app

            if not args.no_browser:
                threading.Timer(
                    1.5, lambda: webbrowser.open(f"http://127.0.0.1:{args.port}")
                ).start()
            uvicorn.run(
                create_app(args.workspace),
                host="127.0.0.1",
                port=args.port,
                log_level="info",
            )
            return 0
        if args.command in {"status", "init"}:
            result = app.status()
        else:
            operation = args.command.replace("-", "_")
            payload = vars(args).copy()
            for key in ["workspace", "command"]:
                payload.pop(key, None)
            if args.command == "profile":
                operation = "config"
            if args.command == "ai-import":
                payload["text"] = Path(payload.pop("file")).read_text(
                    encoding="utf-8-sig"
                )
            if args.command == "action":
                operation = args.operation
                payload = json.loads(
                    Path(args.args_file).read_text() if args.args_file else args.args
                )
            result = app.run(operation, lambda: dispatch(app, operation, payload))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("status") != "partial" else 6
    except (DomainError, ValueError, OSError) as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "reason": getattr(exc, "reason", "error"),
                    "message": str(exc),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
