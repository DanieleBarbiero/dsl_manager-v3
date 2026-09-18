"""Loopback-only web application, one job queue and the same application service."""

from __future__ import annotations
import json
import secrets
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from dslm3 import __version__
from dslm3.common import DomainError, safe_relative, within, now
from dslm3.service import Application
from dslm3.knowledge import Knowledge, POLICIES
from dslm3.temporal import Temporal
from dslm3.ai import AI
from dslm3.exports import Exports
from dslm3.parsers.sql import catalog


def dispatch(app: Application, operation: str, args: dict):
    k = Knowledge(app)
    ai = AI(app)
    temporal = Temporal(app)
    exports = Exports(app)
    if operation == "vega":
        return app.load_vega()
    if operation == "scan":
        return app.scan(args.get("directory"))
    if operation == "parse":
        return (
            app.parse(args["revision"], app.schema(), args.get("retry", False))
            if args.get("revision")
            else app.parse_all(args.get("retry", False))
        )
    if operation == "derive":
        return k.derive()
    if operation == "auto_review":
        return k.auto_review()
    if operation == "merge":
        return k.merge(args.get("batches"), args.get("strict", False))
    if operation == "reconcile":
        return k.reconcile()
    if operation == "pipeline":
        parse = app.parse_all()
        derived = k.derive()
        review = k.auto_review()
        merge = k.merge()
        reconcile = k.reconcile()
        return {
            "parse": parse,
            "derive": derived,
            "review": review,
            "merge": merge,
            "reconcile": reconcile,
            "errors": parse["errors"],
            "partial": parse["partial"],
        }
    if operation == "review":
        if args.get("ids") is not None:
            return k.review_many(
                args["ids"],
                args["outcome"],
                args.get("actor_id"),
                args.get("reason", ""),
            )
        return k.review(
            args["candidate_id"],
            args["outcome"],
            actor_id=args.get("actor_id"),
            reason=args.get("reason", ""),
            expected_head=args.get("expected_head"),
            check_head="expected_head" in args,
            idempotency_key=args.get("idempotency_key"),
        )
    if operation == "correct":
        return k.correct(
            args["candidate_id"],
            args["payload"],
            args.get("actor_id"),
            args.get("reason", "Correzione"),
            args.get("expected_head"),
        )
    if operation == "config":
        values = args.get("values", {})
        if args.get("profile") == "conservative":
            values = {**values, "automatic_policies": list(POLICIES.values())}
        if args.get("profile") == "manual":
            values = {**values, "automatic_policies": []}
        if "automatic_policies" in values and set(values["automatic_policies"]) - set(
            POLICIES.values()
        ):
            raise DomainError("unknown_policy", "Policy automatica sconosciuta.")
        return app.store.configure(values, args.get("expected_hash"))
    if operation == "temporal_extract":
        return (
            temporal.extract(args["revision"])
            if args.get("revision")
            else {
                "results": [
                    temporal.extract(s["current_revision"])
                    for s in app.sources()
                    if s["status"] == "active"
                ]
            }
        )
    if operation == "temporal_consolidate":
        return temporal.consolidate(args["subject_type"], args["subject_id"])
    if operation == "temporal_propose":
        return temporal.propose(
            args["revision"],
            args["subject_type"],
            args["subject_id"],
            args["evidence_ids"],
            args.get("start"),
            args.get("end"),
            args.get("precision"),
            args.get("timezone"),
        )
    if operation == "temporal_propagate":
        return temporal.propagate(
            args["sources"],
            args["target_type"],
            args["target_id"],
            args.get("policy", "explicit_copy"),
        )
    if operation == "select":
        return ai.select(
            args.get("route", "domain_interpretation"),
            args.get("max_chars"),
            args.get("max_evidence"),
        )
    if operation == "package":
        return ai.package(args["selection_id"])
    if operation == "package_all":
        results = []
        for route in args.get(
            "routes", ["technical_extraction", "domain_interpretation"]
        ):
            plan = ai.select(route)
            results.append(
                ai.package(plan["id"])
                if plan["selected_count"]
                else {"route": route, "status": "empty", "selection_id": plan["id"]}
            )
        return {"packages": results}
    if operation == "ai_import":
        return ai.import_response(
            args["package_id"], args["text"], args.get("allow_stale", False)
        )
    if operation == "snapshot":
        return {
            k: v
            for k, v in exports.snapshot(
                args.get("schema_version", 2), args.get("allow_incomplete", False)
            ).items()
            if k != "content"
        }
    if operation == "diff":
        return exports.diff(
            args["before"], args["after"], args.get("cross_schema", False)
        )
    if operation == "graph":
        return exports.graph(
            args["snapshot_id"],
            args.get("dynamic", False),
            args.get("mode", "strict"),
            include_sources=args.get("include_sources", True),
            include_fact_nodes=args.get("include_fact_nodes", True),
            include_conflicts=args.get("include_conflicts", True),
        )
    if operation == "diagnostics":
        # Explicit simulation; never written into source/evidence/knowledge tables.
        return {
            "status": "partial",
            "scenario": "controlled_partial_success/1",
            "production_mutations": 0,
            "message": "Diagnostica controllata: non dimostra un risultato partial di Docling su una fonte.",
        }
    raise DomainError("unknown_operation", "Operazione non riconosciuta.")


def create_app(workspace: str | Path) -> FastAPI:
    application = Application(workspace)
    token = secrets.token_urlsafe(32)
    jobs = {}
    lock = threading.Lock()
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dslm3")

    @asynccontextmanager
    async def lifespan(api):
        yield
        executor.shutdown(wait=True)

    api = FastAPI(
        title="DSLM3",
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    api.state.application = application
    api.state.token = token
    api.state.jobs = jobs

    @api.middleware("http")
    async def local_only(request: Request, call_next):
        host = request.url.hostname
        if host not in {"127.0.0.1", "localhost", "::1", "testserver"}:
            return JSONResponse(
                {"reason": "invalid_host", "message": "Server riservato a localhost."},
                status_code=403,
            )
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc != request.headers.get("host"):
            return JSONResponse(
                {"reason": "invalid_origin", "message": "Origine non ammessa."},
                status_code=403,
            )
        if request.method not in {
            "GET",
            "HEAD",
            "OPTIONS",
        } and not secrets.compare_digest(
            request.headers.get("x-dslm3-token", ""), token
        ):
            return JSONResponse(
                {
                    "reason": "csrf",
                    "message": "Sessione non valida: ricaricare la pagina.",
                },
                status_code=403,
            )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        )
        return response

    @api.exception_handler(DomainError)
    async def domain_error(request, exc):
        return JSONResponse(
            {"reason": exc.reason, "message": str(exc)}, status_code=exc.status
        )

    @api.get("/api/bootstrap")
    def bootstrap():
        return {
            "token": token,
            "version": __version__,
            "workspace": str(application.root),
        }

    @api.get("/api/status")
    def status():
        return application.status()

    @api.get("/api/sources")
    def sources():
        return application.sources()

    @api.get("/api/evidence")
    def evidence(revision: str | None = None):
        return application.evidence(revision)

    @api.get("/api/candidates")
    def candidates(state: str | None = None, batch: str | None = None):
        return Knowledge(application).candidates(state, batch)

    @api.get("/api/knowledge")
    def knowledge():
        return {
            "objects": Knowledge(application).objects(),
            "conflicts": Knowledge(application).conflicts(),
        }

    @api.get("/api/temporal")
    def temporal():
        return {
            "raw": Temporal(application).raw(),
            "groups": [
                {"id": r["id"], **json.loads(r["payload"])}
                for r in application.store.rows(
                    "SELECT * FROM temporal_groups ORDER BY created_at"
                )
            ],
        }

    @api.get("/api/plans")
    def plans():
        return AI(application).plans()

    @api.get("/api/packages")
    def packages():
        return AI(application).packages()

    @api.get("/api/snapshots")
    def snapshots():
        return Exports(application).snapshots()

    @api.get("/api/config")
    def config():
        return {
            "config": application.store.config(),
            "policies": list(POLICIES.values()),
            "catalog": catalog(),
        }

    @api.get("/api/runs")
    def runs():
        return application.store.rows(
            "SELECT * FROM runs ORDER BY created_at DESC LIMIT 100"
        )

    @api.get("/api/jobs")
    def list_jobs():
        with lock:
            return list(jobs.values())[-40:]

    @api.get("/api/jobs/{job_id}")
    def job(job_id: str):
        with lock:
            if job_id not in jobs:
                raise DomainError("job_missing", "Job inesistente.", 404)
            return jobs[job_id]

    @api.post("/api/action")
    async def action(request: Request):
        try:
            body = await request.json()
        except Exception:
            raise DomainError("invalid_json", "Richiesta JSON non valida.")
        if (
            not isinstance(body, dict)
            or not isinstance(body.get("operation"), str)
            or not isinstance(body.get("args", {}), dict)
        ):
            raise DomainError("invalid_action", "Serve operation e un oggetto args.")
        ident = "JOB_" + uuid.uuid4().hex[:16]
        with lock:
            jobs[ident] = {
                "id": ident,
                "operation": body["operation"],
                "status": "queued",
                "created_at": now(),
            }

        def execute():
            with lock:
                jobs[ident]["status"] = "running"
            try:
                result = application.run(
                    body["operation"],
                    lambda: dispatch(
                        application, body["operation"], body.get("args", {})
                    ),
                )
                with lock:
                    jobs[ident].update(
                        status=result["status"],
                        result=result["result"],
                        run_id=result["run_id"],
                    )
            except Exception as exc:
                with lock:
                    jobs[ident].update(
                        status="error",
                        error={
                            "reason": getattr(exc, "reason", "operation_failed"),
                            "message": str(exc),
                        },
                    )
            finally:
                with lock:
                    jobs[ident]["finished_at"] = now()

        executor.submit(execute)
        return {"job_id": ident, "status": "queued"}

    @api.post("/api/upload")
    async def upload(files: list[UploadFile] = File(...), paths: str = Form("[]")):
        try:
            names = json.loads(paths)
        except json.JSONDecodeError:
            raise DomainError("invalid_paths", "Percorsi non validi.")
        if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
            raise DomainError("invalid_paths", "Serve una lista di percorsi testuali.")
        if names and len(names) != len(files):
            raise DomainError(
                "invalid_paths", "Numero percorsi diverso dal numero file."
            )
        results = []
        for i, file in enumerate(files):
            data = await file.read(application.store.config()["max_file_bytes"] + 1)
            results.append(
                application.ingest(
                    names[i] if names else file.filename or "upload.bin", data
                )
            )
        return {"files": results}

    @api.get("/api/download")
    def download(path: str):
        path = safe_relative(path)
        if path.split("/", 1)[0] not in {"artifacts", "ai", "logs"}:
            raise DomainError("download_path", "Percorso non esportabile.")
        target = within(application.root, path)
        if not target.is_file():
            raise DomainError("file_missing", "File inesistente.", 404)
        return FileResponse(
            target, filename=target.name, media_type="application/octet-stream"
        )

    @api.get("/api/log")
    def log(path: str = "logs/events.jsonl"):
        if not path.startswith("logs/"):
            raise DomainError("log_path", "Percorso log non valido.")
        target = within(application.root, path)
        return {
            "text": target.read_text(encoding="utf-8", errors="replace")[-100000:]
            if target.is_file()
            else ""
        }

    static = Path(__file__).parent / "static"
    api.mount("/static", StaticFiles(directory=static), name="static")

    @api.get("/")
    def index():
        return FileResponse(static / "index.html")

    return api
