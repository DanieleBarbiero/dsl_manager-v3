"""Application service used identically by the web interface and CLI."""

from __future__ import annotations
import fnmatch
import json
import re
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
import psutil

from dslm3.common import (
    DomainError,
    atomic_write,
    canonical,
    digest,
    dump_json,
    now,
    safe_relative,
    uid,
    within,
)
from dslm3.storage import Store

SQL_EXTENSIONS = {
    ".sql",
    ".pls",
    ".plsql",
    ".pks",
    ".pkb",
    ".prc",
    ".fnc",
    ".trg",
    ".ddl",
    ".dml",
    ".pck",
    ".tpb",
    ".tps",
}


class Application:
    def __init__(self, workspace: str | Path):
        self.store = Store(workspace)
        self.root = self.store.root

    def ingest(self, name: str, data: bytes) -> dict:
        name = safe_relative(name)
        if len(data) > self.store.config()["max_file_bytes"]:
            raise DomainError("file_budget", "File oltre il limite configurato.")
        source_id = uid("SRC", name)
        sha = digest(data)
        revision_id = uid("REV", [source_id, sha])
        object_path = f"objects/{sha}/{Path(name).name}"
        target = within(self.root, object_path)
        if not target.exists():
            atomic_write(target, data)
        elif digest(target.read_bytes()) != sha:
            raise DomainError("object_corruption", "Copia immutabile corrotta.")
        atomic_write(within(self.root / "corpus", name), data)
        with self.store.connect(True) as conn:
            previous = conn.execute(
                "SELECT current_revision FROM sources WHERE id=?", (source_id,)
            ).fetchone()
            conn.execute(
                "INSERT OR IGNORE INTO sources(id,path,first_seen) VALUES(?,?,?)",
                (source_id, name, now()),
            )
            conn.execute(
                "INSERT OR IGNORE INTO revisions VALUES(?,?,?,?,?,?)",
                (revision_id, source_id, sha, object_path, len(data), now()),
            )
            conn.execute(
                "UPDATE sources SET current_revision=?,status='active' WHERE id=?",
                (revision_id, source_id),
            )
        self.store.log(
            "ingest", source_id=source_id, revision_id=revision_id, path=name
        )
        return {
            "source_id": source_id,
            "revision_id": revision_id,
            "changed": not previous or previous[0] != revision_id,
            "sha256": sha,
            "path": name,
        }

    def scan(self, directory: str | Path | None = None) -> dict:
        source_root = Path(directory).resolve() if directory else self.root / "corpus"
        if not source_root.is_dir():
            raise DomainError("missing_directory", "Directory corpus inesistente.")
        if source_root == self.root or self.root.is_relative_to(source_root):
            raise DomainError(
                "recursive_workspace",
                "Il corpus non può includere il workspace di destinazione.",
            )
        config = self.store.config()
        results = []
        ignored = []
        seen = set()
        for path in sorted(source_root.rglob("*")):
            if path.is_symlink():
                ignored.append(str(path.relative_to(source_root)))
                continue
            if not path.is_file():
                continue
            relative = path.relative_to(source_root).as_posix()
            seen.add(relative)
            if any(
                fnmatch.fnmatch(relative, p) or fnmatch.fnmatch(path.name, p)
                for p in config["exclude"]
            ):
                ignored.append(relative)
                continue
            results.append(self.ingest(relative, path.read_bytes()))
        missing = []
        with self.store.connect(True) as conn:
            for row in conn.execute(
                "SELECT id,path FROM sources WHERE status='active'"
            ).fetchall():
                if row["path"] not in seen:
                    conn.execute(
                        "UPDATE sources SET status='missing' WHERE id=?", (row["id"],)
                    )
                    missing.append(row["path"])
        return {
            "files": results,
            "ignored": ignored,
            "missing": missing,
            "changed": sum(x["changed"] for x in results),
        }

    def sources(self):
        rows = self.store.rows(
            "SELECT s.*,r.sha256,r.size,r.created_at AS revision_created FROM sources s JOIN revisions r ON r.id=s.current_revision ORDER BY s.path"
        )
        for row in rows:
            parsed = self.store.one(
                "SELECT id,status,payload FROM parses WHERE revision_id=? ORDER BY created_at DESC LIMIT 1",
                (row["current_revision"],),
            )
            row["parse"] = json.loads(parsed["payload"]) if parsed else None
            if row["parse"]:
                row["parse"].pop("artifacts", None)
        return rows

    def evidence(self, revision: str | None = None, include_historical: bool = False):
        where = []
        args = []
        if revision:
            where.append("e.revision_id=?")
            args.append(revision)
        if not include_historical:
            where.extend(
                [
                    "s.status='active'",
                    "s.current_revision=e.revision_id",
                    "EXISTS(SELECT 1 FROM parse_evidence pe WHERE pe.evidence_id=e.id AND pe.parse_id=(SELECT p.id FROM parses p WHERE p.revision_id=e.revision_id AND p.status IN ('success','partial') ORDER BY p.created_at DESC LIMIT 1))",
                ]
            )
        rows = self.store.rows(
            "SELECT e.*,s.path FROM evidence e JOIN revisions r ON r.id=e.revision_id JOIN sources s ON s.id=r.source_id"
            + (" WHERE " + " AND ".join(where) if where else "")
            + " ORDER BY s.path,e.id",
            tuple(args),
        )
        for r in rows:
            r["locator"] = json.loads(r["locator"])
            r["data"] = json.loads(r["data"])
        return rows

    def schema(self):
        schema = {}
        for e in self.evidence():
            if e["type"] == "ddl_column":
                schema.setdefault(e["data"]["table"], []).append(e["data"]["column"])
        return {k: sorted(set(v)) for k, v in schema.items()}

    def parse(
        self, revision: str, schema: dict | None = None, retry: bool = False
    ) -> dict:
        row = self.store.one(
            "SELECT r.*,s.path FROM revisions r JOIN sources s ON s.id=r.source_id WHERE r.id=?",
            (revision,),
        )
        if not row:
            raise DomainError("unknown_revision", "Revisione inesistente.", 404)
        config = self.store.config()
        source = within(self.root, row["object_path"])
        if digest(source.read_bytes()) != row["sha256"]:
            raise DomainError(
                "source_changed", "Hash della revisione non corrispondente."
            )
        from dslm3.parsers.documents import decode

        needs_schema = source.suffix.lower() in SQL_EXTENSIONS and bool(
            re.search(
                r"\b(?:PROCEDURE|FUNCTION|TRIGGER|VIEW|SELECT|MERGE|BEGIN|DECLARE)\b",
                decode(source.read_bytes())[0],
                re.I,
            )
        )
        relevant = {
            "dialect": config["sql_dialect"],
            "chunk_chars": config["chunk_chars"],
            "schema": schema if needs_schema else None,
            "max_file_bytes": config["max_file_bytes"],
            "max_evidence": config["max_evidence"],
        }
        parser_version = "3.0.0-r2:" + digest(relevant)
        cached = self.store.one(
            "SELECT * FROM parses WHERE revision_id=? AND parser_version=? AND status IN ('success','partial') ORDER BY created_at DESC LIMIT 1",
            (revision, parser_version),
        )
        if cached and not retry:
            latest = self.store.one(
                "SELECT id FROM parses WHERE revision_id=? AND status IN ('success','partial') ORDER BY created_at DESC,rowid DESC LIMIT 1",
                (revision,),
            )
            summary = json.loads(cached["payload"])
            if latest["id"] != cached["id"]:
                activation = uid("PARSE", [revision, parser_version, now()])
                summary = {
                    **summary,
                    "parse_id": activation,
                    "cached_from": cached["id"],
                }
                with self.store.connect(True) as conn:
                    conn.execute(
                        "INSERT INTO parses VALUES(?,?,?,?,?,?)",
                        (
                            activation,
                            revision,
                            parser_version,
                            cached["status"],
                            canonical(summary),
                            now(),
                        ),
                    )
                    conn.execute(
                        "INSERT INTO parse_evidence SELECT ?,evidence_id FROM parse_evidence WHERE parse_id=?",
                        (activation, cached["id"]),
                    )
            return {**summary, "cached": True}
        parse_id = uid("PARSE", [revision, parser_version, now()])
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="dslm3_parse_") as tmp:
            request = Path(tmp) / "request.json"
            output = Path(tmp) / "result.json"
            dump_json(
                request,
                {
                    "path": str(source),
                    "revision": revision,
                    "config": config,
                    "schema": schema or {},
                },
            )
            log_path = self.root / "logs" / f"{parse_id}.log"
            with log_path.open("wb") as log:
                proc = subprocess.Popen(
                    [sys.executable, "-m", "dslm3.worker", str(request), str(output)],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
                reason = None
                while proc.poll() is None:
                    if time.monotonic() - started > config["worker_timeout"]:
                        reason = "worker_timeout"
                    try:
                        memory = psutil.Process(proc.pid).memory_info().rss
                        memory += sum(
                            p.memory_info().rss
                            for p in psutil.Process(proc.pid).children(recursive=True)
                        )
                        if memory > config["worker_memory_mb"] * 1024**2:
                            reason = "worker_memory_limit"
                    except psutil.Error:
                        pass
                    if (
                        output.exists()
                        and output.stat().st_size > config["max_output_bytes"]
                    ):
                        reason = "worker_output_limit"
                    if reason:
                        try:
                            for child in psutil.Process(proc.pid).children(
                                recursive=True
                            ):
                                child.kill()
                        except psutil.Error:
                            pass
                        proc.kill()
                        proc.wait()
                        break
                    time.sleep(0.1)
                if reason:
                    result = {
                        "status": "error",
                        "reason": reason,
                        "message": "Worker interrotto per limite risorse.",
                    }
                elif (
                    output.exists()
                    and output.stat().st_size <= config["max_output_bytes"]
                ):
                    result = json.loads(output.read_text(encoding="utf-8"))
                else:
                    result = {
                        "status": "error",
                        "reason": "worker_failed",
                        "message": f"Worker terminato con codice {proc.returncode}; vedere il log.",
                    }
        if digest(source.read_bytes()) != row["sha256"]:
            raise DomainError("source_changed", "Byte cambiati durante parsing.")
        evidence = list({canonical(e): e for e in result.pop("evidence", [])}.values())
        if len(evidence) > config["max_evidence"]:
            result = {
                "status": "error",
                "reason": "evidence_budget",
                "message": "Troppe evidenze.",
            }
            evidence = []
        if result["status"] == "error":
            evidence = []
        artifacts = result.pop("artifacts", {})
        artifact_dir = self.root / "artifacts" / parse_id
        for name, value in artifacts.items():
            target = within(artifact_dir, name)
            if isinstance(value, str):
                atomic_write(target, value)
            else:
                dump_json(target, value)
        summary = {
            **result,
            "parse_id": parse_id,
            "revision_id": revision,
            "evidence_count": len(evidence),
            "artifact_dir": str(artifact_dir.relative_to(self.root)),
            "log": str(log_path.relative_to(self.root)),
            "duration_seconds": round(time.monotonic() - started, 3),
            "resource_enforcement": "parent_monitored",
        }
        with self.store.connect(True) as conn:
            conn.execute(
                "INSERT INTO parses VALUES(?,?,?,?,?,?)",
                (
                    parse_id,
                    revision,
                    parser_version,
                    result["status"],
                    canonical(summary),
                    now(),
                ),
            )
            for item in evidence:
                ident = uid("EV", [revision, item])
                conn.execute(
                    "INSERT OR IGNORE INTO evidence VALUES(?,?,?,?,?,?,?,?)",
                    (
                        ident,
                        revision,
                        item["kind"],
                        item["type"],
                        item["text"],
                        canonical(item["locator"]),
                        canonical(item["data"]),
                        parse_id,
                    ),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO parse_evidence VALUES(?,?)",
                    (parse_id, ident),
                )
        self.store.log("parse", **summary)
        return summary

    def parse_all(self, retry: bool = False):
        sources = self.sources()
        ordered = []
        for s in sources:
            if s["status"] != "active":
                continue
            rev = self.store.one(
                "SELECT object_path FROM revisions WHERE id=?", (s["current_revision"],)
            )
            path = self.root / rev["object_path"]
            from dslm3.parsers.documents import decode

            has_ddl = path.suffix.lower() in SQL_EXTENSIONS and bool(
                re.search(r"CREATE\s+TABLE", decode(path.read_bytes())[0], re.I)
            )
            ordered.append((not has_ddl, s["path"], s["current_revision"]))
        results = []
        for _, _, revision in sorted(ordered):
            results.append(self.parse(revision, self.schema(), retry=retry))
        return {
            "results": results,
            "success": sum(x["status"] == "success" for x in results),
            "partial": sum(x["status"] == "partial" for x in results),
            "errors": sum(x["status"] == "error" for x in results),
        }

    def load_vega(self):
        resources = Path(__file__).parent / "resources/vega"
        imported = []
        for path in sorted(resources.rglob("*")):
            if path.is_file():
                imported.append(
                    self.ingest(
                        "vega/" + path.relative_to(resources).as_posix(),
                        path.read_bytes(),
                    )
                )
        return {"sources": imported}

    def status(self):
        counts = {}
        for table in (
            "sources",
            "revisions",
            "evidence",
            "candidates",
            "objects",
            "effective_objects",
            "reviews",
            "temporal_raw",
            "selections",
            "packages",
            "snapshots",
        ):
            counts[table] = self.store.one(f"SELECT COUNT(*) AS n FROM {table}")["n"]
        states = self.store.rows(
            "SELECT state,COUNT(*) AS count FROM candidate_states WHERE leaf=1 AND current_revision=1 AND source_status='active' AND current_parse=1 GROUP BY state"
        )
        counts["review_states"] = {r["state"]: r["count"] for r in states}
        counts["confirmed_unmerged"] = self.store.one(
            "SELECT COUNT(*) AS n FROM candidate_states c WHERE state='confirmed' AND leaf=1 AND current_revision=1 AND source_status='active' AND current_parse=1 AND record_type IN ('candidate_fact','candidate_relation','temporal_interval') AND NOT EXISTS(SELECT 1 FROM supports s WHERE s.candidate_id=c.id)"
        )["n"]
        counts["open_reconciliations"] = self.store.one(
            "SELECT COUNT(*) AS n FROM reconciliation WHERE closed_at IS NULL"
        )["n"]
        return {
            "workspace": str(self.root),
            "counts": counts,
            "config_hash": digest(self.store.config()),
        }

    def run(self, operation: str, action):
        run_id = "RUN_" + uuid.uuid4().hex[:16]
        with self.store.connect(True) as conn:
            conn.execute(
                "INSERT INTO runs VALUES(?,?,?,?,?,?)",
                (run_id, operation, "running", "{}", now(), now()),
            )
        try:
            result = action()
            status = (
                "partial"
                if isinstance(result, dict)
                and (
                    result.get("errors", 0)
                    or result.get("partial", 0)
                    or result.get("status") == "partial"
                )
                else "success"
            )
        except Exception as exc:
            with self.store.connect(True) as conn:
                conn.execute(
                    "UPDATE runs SET status=?,payload=?,updated_at=? WHERE id=?",
                    (
                        "error",
                        canonical(
                            {
                                "reason": getattr(exc, "reason", "error"),
                                "message": str(exc),
                            }
                        ),
                        now(),
                        run_id,
                    ),
                )
            raise
        with self.store.connect(True) as conn:
            conn.execute(
                "UPDATE runs SET status=?,payload=?,updated_at=? WHERE id=?",
                (status, canonical(result), now(), run_id),
            )
        return {"run_id": run_id, "status": status, "result": result}
