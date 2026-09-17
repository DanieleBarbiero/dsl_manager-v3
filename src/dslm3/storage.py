"""A compact append-only evidence ledger, with transactional review heads."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from dslm3.common import DomainError, canonical, digest, dump_json, now

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_history(version INTEGER PRIMARY KEY, checksum TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY,path TEXT UNIQUE NOT NULL,current_revision TEXT,status TEXT NOT NULL DEFAULT 'active',first_seen TEXT NOT NULL,metadata TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS revisions(id TEXT PRIMARY KEY,source_id TEXT NOT NULL REFERENCES sources(id),sha256 TEXT NOT NULL,object_path TEXT NOT NULL,size INTEGER NOT NULL,created_at TEXT NOT NULL,UNIQUE(source_id,sha256));
CREATE TABLE IF NOT EXISTS parses(id TEXT PRIMARY KEY,revision_id TEXT NOT NULL REFERENCES revisions(id),parser_version TEXT NOT NULL,status TEXT NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS evidence(id TEXT PRIMARY KEY,revision_id TEXT NOT NULL REFERENCES revisions(id),kind TEXT NOT NULL,type TEXT NOT NULL,text TEXT NOT NULL,locator TEXT NOT NULL,data TEXT NOT NULL,parse_id TEXT NOT NULL REFERENCES parses(id));
CREATE TABLE IF NOT EXISTS parse_evidence(parse_id TEXT NOT NULL REFERENCES parses(id),evidence_id TEXT NOT NULL REFERENCES evidence(id),PRIMARY KEY(parse_id,evidence_id));
CREATE INDEX IF NOT EXISTS evidence_revision ON evidence(revision_id);
CREATE TABLE IF NOT EXISTS batches(id TEXT PRIMARY KEY,origin TEXT NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS candidates(id TEXT PRIMARY KEY,batch_id TEXT NOT NULL REFERENCES batches(id),revision_id TEXT NOT NULL REFERENCES revisions(id),record_type TEXT NOT NULL,rule TEXT,payload TEXT NOT NULL,parent_id TEXT REFERENCES candidates(id),root_id TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(parent_id));
CREATE TABLE IF NOT EXISTS reviews(id TEXT PRIMARY KEY,candidate_id TEXT NOT NULL REFERENCES candidates(id),outcome TEXT NOT NULL CHECK(outcome IN ('confirmed','rejected','superseded','pending')),actor_type TEXT NOT NULL,actor_id TEXT NOT NULL,reason TEXT NOT NULL,previous_id TEXT,request_hash TEXT NOT NULL,idempotency_key TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(actor_type,actor_id,idempotency_key));
CREATE TABLE IF NOT EXISTS heads(candidate_id TEXT PRIMARY KEY REFERENCES candidates(id),decision_id TEXT NOT NULL REFERENCES reviews(id));
CREATE TABLE IF NOT EXISTS objects(id TEXT PRIMARY KEY,kind TEXT NOT NULL,semantic_key TEXT UNIQUE NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS supports(object_id TEXT NOT NULL REFERENCES objects(id),candidate_id TEXT NOT NULL REFERENCES candidates(id),decision_id TEXT NOT NULL REFERENCES reviews(id),created_at TEXT NOT NULL,PRIMARY KEY(object_id,candidate_id));
CREATE TABLE IF NOT EXISTS reconciliation(id TEXT PRIMARY KEY,candidate_id TEXT NOT NULL REFERENCES candidates(id),opened_at TEXT NOT NULL,closed_at TEXT);
CREATE TABLE IF NOT EXISTS temporal_raw(id TEXT PRIMARY KEY,revision_id TEXT NOT NULL REFERENCES revisions(id),subject_type TEXT NOT NULL,subject_id TEXT NOT NULL,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS temporal_groups(id TEXT PRIMARY KEY,payload TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS selections(id TEXT PRIMARY KEY,state_hash TEXT NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS packages(id TEXT PRIMARY KEY,selection_id TEXT REFERENCES selections(id),payload TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS snapshots(id TEXT PRIMARY KEY,schema_version INTEGER NOT NULL,content_hash TEXT NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,operation TEXT NOT NULL,status TEXT NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE VIEW IF NOT EXISTS candidate_states AS
 SELECT c.*,COALESCE(r.outcome,'pending') AS state,h.decision_id,
 NOT EXISTS(SELECT 1 FROM candidates child WHERE child.parent_id=c.id) AS leaf,
 s.status AS source_status,s.current_revision=c.revision_id AS current_revision
 FROM candidates c LEFT JOIN heads h ON h.candidate_id=c.id LEFT JOIN reviews r ON r.id=h.decision_id
 JOIN revisions v ON v.id=c.revision_id JOIN sources s ON s.id=v.source_id;
CREATE VIEW IF NOT EXISTS effective_supports AS
 SELECT x.* FROM supports x JOIN candidate_states c ON c.id=x.candidate_id
 WHERE c.state='confirmed' AND c.leaf=1 AND c.source_status='active' AND c.current_revision=1;
CREATE VIEW IF NOT EXISTS effective_objects AS
 SELECT o.* FROM objects o WHERE EXISTS(SELECT 1 FROM effective_supports s WHERE s.object_id=o.id);
"""
MIGRATION_2 = """
CREATE TABLE IF NOT EXISTS candidate_batches(batch_id TEXT NOT NULL REFERENCES batches(id), candidate_id TEXT NOT NULL REFERENCES candidates(id), PRIMARY KEY(batch_id,candidate_id));
INSERT OR IGNORE INTO candidate_batches SELECT batch_id,id FROM candidates;
DROP VIEW IF EXISTS effective_objects;
DROP VIEW IF EXISTS effective_supports;
DROP VIEW IF EXISTS candidate_states;
CREATE VIEW candidate_states AS
 SELECT c.*,COALESCE(r.outcome,'pending') AS state,h.decision_id,
 NOT EXISTS(SELECT 1 FROM candidates child WHERE child.parent_id=c.id) AS leaf,
 s.status AS source_status,s.current_revision=c.revision_id AS current_revision,
 (c.record_type='temporal_interval' OR EXISTS (
   SELECT 1 FROM parse_evidence pe WHERE pe.evidence_id=COALESCE(json_extract(c.payload,'$.evidence_id'),json_extract(c.payload,'$.fragment_id'),json_extract(c.payload,'$.chunk_id'))
   AND pe.parse_id=(SELECT p.id FROM parses p WHERE p.revision_id=c.revision_id AND p.status IN ('success','partial') ORDER BY p.created_at DESC,p.rowid DESC LIMIT 1)
 )) AS current_parse
 FROM candidates c LEFT JOIN heads h ON h.candidate_id=c.id LEFT JOIN reviews r ON r.id=h.decision_id
 JOIN revisions v ON v.id=c.revision_id JOIN sources s ON s.id=v.source_id;
CREATE VIEW effective_supports AS
 SELECT x.* FROM supports x JOIN candidate_states c ON c.id=x.candidate_id
 WHERE c.state='confirmed' AND c.leaf=1 AND c.source_status='active' AND c.current_revision=1 AND c.current_parse=1;
CREATE VIEW effective_objects AS
 SELECT o.* FROM objects o WHERE EXISTS(SELECT 1 FROM effective_supports s WHERE s.object_id=o.id);
"""

IMMUTABLE = (
    "candidate_batches",
    "revisions",
    "parses",
    "evidence",
    "parse_evidence",
    "batches",
    "candidates",
    "reviews",
    "objects",
    "supports",
    "temporal_raw",
    "temporal_groups",
    "selections",
    "packages",
    "snapshots",
)
DEFAULT_CONFIG = {
    "schema_version": 1,
    "actor_id": "local-user",
    "automatic_policies": [],
    "sql_dialect": "auto",
    "exclude": [],
    "max_file_bytes": 67108864,
    "worker_timeout": 300,
    "worker_memory_mb": 4096,
    "max_output_bytes": 268435456,
    "chunk_chars": 5000,
    "max_evidence": 100000,
    "max_intervals": 1000,
    "ai_max_evidence": 10000,
    "ai_max_chars": 10000000,
    "graph_max_elements": 1000000,
}


class Store:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        for name in ("corpus", "objects", "artifacts", "ai/inbox", "ai/outbox", "logs"):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        self.db = self.root / "registry.sqlite3"
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            stored = conn.execute(
                "SELECT checksum FROM schema_history WHERE version=1"
            ).fetchone()
            if stored and stored[0] != digest(SCHEMA):
                raise DomainError(
                    "schema_checksum_mismatch", "Schema modificato senza migrazione."
                )
            conn.execute(
                "INSERT OR IGNORE INTO schema_history VALUES(1,?)", (digest(SCHEMA),)
            )
            migration = conn.execute(
                "SELECT checksum FROM schema_history WHERE version=2"
            ).fetchone()
            if migration and migration[0] != digest(MIGRATION_2):
                raise DomainError(
                    "schema_checksum_mismatch", "Migrazione modificata senza versione."
                )
            if not migration:
                conn.executescript("BEGIN IMMEDIATE;\n" + MIGRATION_2)
                conn.execute(
                    "INSERT INTO schema_history VALUES(2,?)", (digest(MIGRATION_2),)
                )
                conn.commit()
            for table in IMMUTABLE:
                for op in ("UPDATE", "DELETE"):
                    conn.execute(
                        f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{op} BEFORE {op} ON {table} BEGIN SELECT RAISE(ABORT,'append_only'); END"
                    )
        if not (self.root / "project.json").exists():
            dump_json(self.root / "project.json", DEFAULT_CONFIG)

    @contextmanager
    def connect(self, write: bool = False):
        conn = sqlite3.connect(self.db, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            if write:
                conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def config(self) -> dict:
        value = json.loads((self.root / "project.json").read_text(encoding="utf-8"))
        return {**DEFAULT_CONFIG, **value}

    def configure(self, values: dict, expected_hash: str | None = None) -> dict:
        current = self.config()
        if expected_hash is not None and digest(current) != expected_hash:
            raise DomainError(
                "config_conflict", "La configurazione è cambiata: ricaricare.", 409
            )
        unknown = set(values) - set(DEFAULT_CONFIG)
        if unknown:
            raise DomainError(
                "invalid_config", f"Chiavi sconosciute: {sorted(unknown)}"
            )
        merged = {**current, **values}
        from dslm3.parsers.sql import identify

        if not isinstance(merged["sql_dialect"], str):
            raise DomainError("invalid_config", "sql_dialect deve essere testo.")
        identify("", merged["sql_dialect"])
        if merged["schema_version"] != 1:
            raise DomainError(
                "invalid_config", "schema_version della configurazione deve essere 1."
            )
        for key in (
            "max_file_bytes",
            "worker_timeout",
            "worker_memory_mb",
            "max_output_bytes",
            "chunk_chars",
            "max_evidence",
            "max_intervals",
            "ai_max_evidence",
            "ai_max_chars",
            "graph_max_elements",
        ):
            if type(merged[key]) is not int or merged[key] <= 0:
                raise DomainError(
                    "invalid_config", f"{key} deve essere un intero positivo."
                )
        limits = {
            "max_file_bytes": 268435456,
            "worker_timeout": 600,
            "worker_memory_mb": 8192,
            "max_output_bytes": 1073741824,
            "max_evidence": 1000000,
            "max_intervals": 10000,
            "graph_max_elements": 5000000,
        }
        if any(merged[k] > maximum for k, maximum in limits.items()):
            raise DomainError(
                "invalid_config", "Un limite supera il massimo consentito."
            )
        if not isinstance(merged["actor_id"], str) or not merged["actor_id"].strip():
            raise DomainError(
                "invalid_config", "actor_id deve essere stabile e non vuoto."
            )
        for key in ("automatic_policies", "exclude"):
            if not isinstance(merged[key], list) or not all(
                isinstance(x, str) for x in merged[key]
            ):
                raise DomainError(
                    "invalid_config", f"{key} deve essere una lista di stringhe."
                )
        dump_json(self.root / "project.json", merged)
        return {"config": merged, "hash": digest(merged)}

    def rows(self, query: str, args: tuple = ()) -> list[dict]:
        with self.connect() as conn:
            return [dict(x) for x in conn.execute(query, args)]

    def one(self, query: str, args: tuple = ()) -> dict | None:
        rows = self.rows(query, args)
        return rows[0] if rows else None

    def log(self, event: str, **data):
        with (self.root / "logs/events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(canonical({"timestamp": now(), "event": event, **data}) + "\n")
