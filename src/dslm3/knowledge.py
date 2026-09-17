"""Candidate-first derivation, provenance validation and governed consolidation."""

from __future__ import annotations
import json
import re
from collections import defaultdict
from itertools import combinations

from dslm3.common import DomainError, canonical, digest, name_key, now, uid

POLICIES = {
    "ddl_table": "explicit_ddl_table_only/1",
    "ddl_column": "explicit_ddl_column_only/1",
    "ddl_constraint": "explicit_resolved_ddl_fk_only/1",
    "sql_unit": "explicit_db_code_unit_only/1",
    "sql_dependency": "observed_db_code_dependency_only/1",
    "xml_structure": "explicit_xml_form_structure_only/1",
    "xml_dependency": "explicit_xml_operation_only/1",
    "log_event": "named_explicit_log_policy_required/1",
    "excel_workbook": "explicit_excel_workbook_only/1",
    "excel_sheet": "explicit_excel_sheet_only/1",
    "excel_region": "explicit_excel_region_only/1",
    "excel_named_range": "explicit_excel_named_range_only/1",
    "excel_table": "explicit_excel_table_only/1",
}
SPECIFIC = {
    "candidate_fact": ("fact_type", "entity_name", "property_name", "property_value"),
    "candidate_relation": ("source_entity", "relation_type", "target_entity"),
    "candidate_mapping": ("domain_entity", "technical_object", "mapping_type"),
    "candidate_conflict": ("conflict_type", "subject", "left_value", "right_value"),
    "candidate_question": ("question_type", "subject", "question_text"),
    "temporal_interval": (
        "target_subject_type",
        "target_subject_id",
        "original_precision",
        "timezone_status",
        "bounds_semantics",
        "temporal_evidence_ids",
    ),
}
PLACEHOLDER = re.compile(
    r"\$\{[^}]+\}|\{\{[^}]+\}\}|\bREPLACE_[A-Z0-9_]+\b|^(?:TBD|TODO|PLACEHOLDER)$|<<[^>]+>>",
    re.I,
)


class Knowledge:
    def __init__(self, app):
        self.app, self.store = app, app.store

    def validate(self, payload, conn, allowed_evidence: set | None = None):
        if not isinstance(payload, dict) or payload.get("record_type") not in SPECIFIC:
            raise DomainError(
                "candidate_schema", "Tipo candidato assente o non ammesso."
            )
        required = [
            "candidate_id",
            "source_revision_id",
            "assertion_type",
            "confidence",
            "evidence_text",
            *SPECIFIC[payload["record_type"]],
        ]
        missing = [
            k for k in required if payload.get(k) is None or payload.get(k) == ""
        ]
        if missing:
            raise DomainError("candidate_schema", f"Campi obbligatori: {missing}")
        for key in SPECIFIC[payload["record_type"]]:
            if key not in {
                "property_value",
                "left_value",
                "right_value",
                "temporal_evidence_ids",
            } and not isinstance(payload[key], str):
                raise DomainError("candidate_schema", f"{key} deve essere testo.")
        if "attributes" in payload and not isinstance(payload["attributes"], dict):
            raise DomainError(
                "candidate_schema", "attributes deve essere un oggetto JSON."
            )
        for key in [
            "candidate_id",
            "source_revision_id",
            "assertion_type",
            "confidence",
            "evidence_text",
        ]:
            if not isinstance(payload[key], str):
                raise DomainError("candidate_schema", f"{key} deve essere testo.")
        if payload["assertion_type"] not in {
            "explicit",
            "observed",
            "inferred",
            "ambiguous",
        } or payload["confidence"] not in {"low", "medium", "high"}:
            raise DomainError("candidate_schema", "Assertion/confidence non ammessi.")
        if any(
            PLACEHOLDER.search(str(payload[k]))
            for k in SPECIFIC[payload["record_type"]]
        ):
            raise DomainError("placeholder", "Il candidato contiene segnaposto.")
        if not conn.execute(
            "SELECT 1 FROM revisions WHERE id=?", (payload["source_revision_id"],)
        ).fetchone():
            raise DomainError("unknown_revision", "Revisione non presente.")
        if payload["record_type"] == "temporal_interval":
            if allowed_evidence is not None:
                raise DomainError(
                    "ai_temporal_forbidden",
                    "Gli intervalli richiedono il flusso temporale esplicito.",
                )
            from dslm3.temporal import validate_interval

            validate_interval(payload, strict=False)
            from dslm3.temporal import TARGETS

            table, object_kind = TARGETS[payload["target_subject_type"]]
            target = conn.execute(
                f"SELECT * FROM {table} WHERE id=?", (payload["target_subject_id"],)
            ).fetchone()
            if target is None or object_kind and target["kind"] != object_kind:
                raise DomainError("temporal_target", "Soggetto temporale inesistente.")
            ids = payload["temporal_evidence_ids"]
            if not isinstance(ids, list) or not ids:
                raise DomainError(
                    "temporal_evidence_missing", "Servono evidenze temporali."
                )
            for evid in ids:
                row = conn.execute(
                    "SELECT * FROM temporal_raw WHERE id=?", (evid,)
                ).fetchone()
                if row is None:
                    raise DomainError(
                        "temporal_evidence_missing",
                        f"Evidenza temporale ignota: {evid}",
                    )
            return
        refs = [
            payload[k]
            for k in ("evidence_id", "fragment_id", "chunk_id")
            if payload.get(k)
        ]
        refs = list(dict.fromkeys(refs))
        if not refs:
            raise DomainError("evidence_required", "Occorre un riferimento a evidenza.")
        quote = payload["evidence_text"]
        if not isinstance(quote, str) or not quote.strip():
            raise DomainError("evidence_required", "Citazione vuota.")
        for ref in refs:
            row = conn.execute("SELECT * FROM evidence WHERE id=?", (ref,)).fetchone()
            if row is None or row["revision_id"] != payload["source_revision_id"]:
                raise DomainError(
                    "evidence_revision_mismatch",
                    "ID evidenza e revisione non corrispondono.",
                )
            if quote not in row["text"]:
                raise DomainError(
                    "evidence_quote_mismatch",
                    "La citazione non è una sottostringa letterale dell’evidenza.",
                )
            if allowed_evidence is not None and ref not in allowed_evidence:
                raise DomainError(
                    "evidence_not_in_package",
                    "Il riferimento non appartiene al package selezionato.",
                )
        # Syntactic and provenance validation does not grant semantic approval.

    def import_candidates(
        self,
        items: list[dict],
        origin: str,
        rules: dict | None = None,
        allowed_evidence: set | None = None,
        metadata: dict | None = None,
    ):
        ids = [x.get("candidate_id") if isinstance(x, dict) else None for x in items]
        if not all(isinstance(i, str) for i in ids):
            raise DomainError("candidate_schema", "candidate_id deve essere testo.")
        if len(set(ids)) != len(ids):
            raise DomainError(
                "duplicate_candidate_id", "candidate_id duplicato nel batch."
            )
        if not items:
            raise DomainError("empty_batch", "Il batch non contiene candidati.")
        batch = uid("BATCH", [origin, items, metadata or {}])
        created = []
        with self.store.connect(True) as conn:
            for item in items:
                self.validate(item, conn, allowed_evidence)
            conn.execute(
                "INSERT OR IGNORE INTO batches VALUES(?,?,?,?)",
                (batch, origin, canonical(metadata or {}), now()),
            )
            for item in items:
                cid = (
                    uid(
                        "CAND",
                        [
                            "deterministic/3",
                            item,
                            (rules or {}).get(item["candidate_id"]),
                        ],
                    )
                    if origin == "deterministic"
                    else uid("CAND", [batch, item["candidate_id"]])
                )
                created.append(cid)
                conn.execute(
                    "INSERT OR IGNORE INTO candidates VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        cid,
                        batch,
                        item["source_revision_id"],
                        item["record_type"],
                        (rules or {}).get(item["candidate_id"]),
                        canonical(item),
                        None,
                        cid,
                        now(),
                    ),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO candidate_batches VALUES(?,?)", (batch, cid)
                )
        return {"batch_id": batch, "candidate_ids": created, "count": len(created)}

    def derive(self):
        evidence = self.app.evidence()
        schema = self.app.schema()
        payloads = []
        rules = {}
        skipped = []

        def add(e, type_, rule, **fields):
            cid = uid("DER", [e["id"], type_, fields])
            base = {
                "candidate_id": cid,
                "source_revision_id": e["revision_id"],
                "evidence_id": e["id"],
                "fragment_id": e["id"] if e["kind"] == "fragment" else None,
                "chunk_id": e["id"] if e["kind"] == "chunk" else None,
                "evidence_text": e["text"],
                "record_type": type_,
                "assertion_type": "explicit",
                "confidence": "high",
                **fields,
            }
            payloads.append(base)
            rules[cid] = rule

        def fact(e, rule, entity, prop, value, **extra):
            add(
                e,
                "candidate_fact",
                rule,
                entity_name=entity,
                property_name=prop,
                property_value=value,
                fact_type="technical",
                **extra,
            )

        for e in evidence:
            d = e["data"]
            kind = e["type"]
            if kind == "ddl_table":
                fact(e, "ddl_table", d["name"], "object_type", "table")
            elif kind == "ddl_column":
                fact(
                    e,
                    "ddl_column",
                    d["name"],
                    "definition",
                    {
                        "datatype": d["datatype"],
                        "nullable": d["nullable"],
                        "constraints": d["constraints"],
                    },
                )
            elif kind == "ddl_constraint" and d["constraint_type"] == "foreign_key":
                target = d["target_table"]
                cols = d["target_columns"]
                if target in schema and all(c in schema[target] for c in cols):
                    add(
                        e,
                        "candidate_relation",
                        "ddl_constraint",
                        source_entity=d["table"],
                        relation_type="foreign_key",
                        target_entity=target,
                        attributes={"columns": d["columns"], "target_columns": cols},
                    )
                else:
                    skipped.append(
                        {"evidence_id": e["id"], "reason": "unresolved_foreign_key"}
                    )
            elif kind.startswith("ddl_") and kind not in {
                "ddl_constraint",
                "ddl_alter",
                "ddl_drop",
                "ddl_grant",
                "ddl_revoke",
            }:
                fact(
                    e,
                    "sql_unit",
                    d["name"],
                    "object_type",
                    d.get("object_type", kind[4:]),
                )
            elif kind in {
                "sql_procedure",
                "sql_function",
                "sql_trigger",
                "sql_package",
                "sql_package_body",
                "sql_type",
                "sql_type_body",
            }:
                fact(e, "sql_unit", d["name"], "object_type", kind[4:])
            elif kind in {"sql_dependency", "xml_dependency"}:
                target = d["target"]
                if "." in target and kind == "sql_dependency":
                    table, column = target.rsplit(".", 1)
                    if table in schema and column not in schema[table]:
                        skipped.append(
                            {
                                "evidence_id": e["id"],
                                "reason": "column_absent_from_schema",
                            }
                        )
                        continue
                add(
                    e,
                    "candidate_relation",
                    kind,
                    source_entity=d["source"],
                    relation_type=d["relation_type"],
                    target_entity=target,
                    assertion_type="observed"
                    if kind == "sql_dependency"
                    else "explicit",
                )
            elif kind in {"xml_form", "xml_field", "xml_button", "xml_block"}:
                fact(
                    e,
                    "xml_structure",
                    d["name"],
                    "definition",
                    {
                        "object_type": kind[4:],
                        **{k: v for k, v in d.items() if k != "name"},
                    },
                )
            elif kind == "log_event":
                entity = "event:" + e["id"]
                fact(e, "log_event", entity, "occurrence", d, assertion_type="observed")
                add(
                    e,
                    "candidate_relation",
                    "log_event",
                    source_entity=entity,
                    relation_type="observed_on",
                    target_entity=d["component"],
                    assertion_type="observed",
                )
            elif kind in {
                "excel_workbook",
                "excel_sheet",
                "excel_region",
                "excel_named_range",
                "excel_table",
            }:
                details = {
                    k: v
                    for k, v in d.items()
                    if k
                    not in {
                        "name",
                        "cells",
                        "manifest",
                        "fragment_id",
                        "source_revision_id",
                    }
                }
                fact(e, kind, d["name"], "definition", {"object_type": kind, **details})
            elif kind == "excel_explicit_reference":
                add(
                    e,
                    "candidate_relation",
                    None,
                    source_entity=d["name"],
                    relation_type="references_external",
                    target_entity=d["target"],
                )
        if not payloads:
            return {"count": 0, "candidate_ids": [], "skipped": skipped}
        return {
            **self.import_candidates(payloads, "deterministic", rules),
            "skipped": skipped,
        }

    def candidates(self, state: str | None = None, batch: str | None = None):
        query = "SELECT * FROM candidate_states WHERE 1=1"
        args = []
        if state:
            query += " AND state=?"
            args.append(state)
        if batch:
            query += " AND id IN (SELECT candidate_id FROM candidate_batches WHERE batch_id=?)"
            args.append(batch)
        rows = self.store.rows(query + " ORDER BY created_at,id", tuple(args))
        for row in rows:
            row["payload"] = json.loads(row["payload"])
            row["policy"] = POLICIES.get(row["rule"])
            row["materialized"] = bool(
                self.store.one(
                    "SELECT 1 FROM supports WHERE candidate_id=?", (row["id"],)
                )
            )
        return rows

    def _review(
        self,
        conn,
        candidate_id,
        outcome,
        actor_id,
        actor_type,
        reason,
        expected_head,
        idempotency_key,
        check_head,
    ):
        if outcome not in {"confirmed", "rejected", "pending"}:
            raise DomainError("review_outcome", "Esito review non ammesso.")
        if not actor_id or not actor_id.strip():
            raise DomainError("actor_required", "Serve un attore stabile.")
        c = conn.execute(
            "SELECT * FROM candidate_states WHERE id=?", (candidate_id,)
        ).fetchone()
        if not c:
            raise DomainError("unknown_candidate", "Candidato inesistente.", 404)
        request = {
            "candidate_id": candidate_id,
            "outcome": outcome,
            "reason": reason,
            "actor_id": actor_id,
            "actor_type": actor_type,
        }
        request_hash = digest(request)
        key = idempotency_key or digest([request, c["decision_id"]])
        old = conn.execute(
            "SELECT * FROM reviews WHERE actor_type=? AND actor_id=? AND idempotency_key=?",
            (actor_type, actor_id, key),
        ).fetchone()
        if old:
            if old["request_hash"] != request_hash:
                raise DomainError(
                    "idempotency_payload_conflict",
                    "Chiave già usata per una decisione diversa.",
                    409,
                )
            return {
                "decision_id": old["id"],
                "candidate_id": candidate_id,
                "outcome": old["outcome"],
                "replay": True,
            }
        if check_head and c["decision_id"] != expected_head:
            raise DomainError(
                "review_head_conflict",
                "La decisione è cambiata; ricaricare il candidato.",
                409,
            )
        if not c["leaf"]:
            raise DomainError(
                "not_leaf", "Candidato sostituito da una correzione.", 409
            )
        if actor_type == "policy":
            if (
                actor_id not in self.store.config()["automatic_policies"]
                or POLICIES.get(c["rule"]) != actor_id
            ):
                raise DomainError(
                    "policy_not_allowed",
                    "Policy assente dall’allowlist o non applicabile.",
                )
        elif actor_type != "human":
            raise DomainError("actor_type", "Tipo attore non ammesso.")
        payload = json.loads(c["payload"])
        if outcome == "confirmed" and payload["record_type"] == "temporal_interval":
            from dslm3.temporal import validate_interval

            validate_interval(payload, strict=True)
        if c["state"] == outcome and c["decision_id"]:
            return {
                "decision_id": c["decision_id"],
                "candidate_id": candidate_id,
                "outcome": outcome,
                "semantic_noop": True,
            }
        did = uid("DEC", [candidate_id, request_hash, c["decision_id"], key])
        conn.execute(
            "INSERT INTO reviews VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                did,
                candidate_id,
                outcome,
                actor_type,
                actor_id,
                reason,
                c["decision_id"],
                request_hash,
                key,
                now(),
            ),
        )
        conn.execute(
            "INSERT INTO heads VALUES(?,?) ON CONFLICT(candidate_id) DO UPDATE SET decision_id=excluded.decision_id",
            (candidate_id, did),
        )
        if conn.execute(
            "SELECT 1 FROM supports WHERE candidate_id=?", (candidate_id,)
        ).fetchone():
            conn.execute(
                "INSERT OR IGNORE INTO reconciliation VALUES(?,?,?,NULL)",
                (uid("REC", [candidate_id, did]), candidate_id, now()),
            )
        return {"decision_id": did, "candidate_id": candidate_id, "outcome": outcome}

    def review(
        self,
        candidate_id,
        outcome,
        actor_id=None,
        actor_type="human",
        reason="",
        expected_head=None,
        idempotency_key=None,
        check_head=False,
    ):
        with self.store.connect(True) as conn:
            return self._review(
                conn,
                candidate_id,
                outcome,
                actor_id or self.store.config()["actor_id"],
                actor_type,
                reason,
                expected_head,
                idempotency_key,
                check_head,
            )

    def review_many(self, ids: list[str], outcome: str, actor_id=None, reason=""):
        with self.store.connect(True) as conn:
            return [
                self._review(
                    conn,
                    i,
                    outcome,
                    actor_id or self.store.config()["actor_id"],
                    "human",
                    reason,
                    None,
                    None,
                    False,
                )
                for i in ids
            ]

    def auto_review(self):
        allowed = self.store.config()["automatic_policies"]
        decisions = []
        for c in self.candidates("pending"):
            if (
                c["leaf"]
                and c["current_revision"]
                and c["current_parse"]
                and c["source_status"] == "active"
                and c["policy"] in allowed
            ):
                decisions.append(
                    self.review(
                        c["id"],
                        "confirmed",
                        c["policy"],
                        "policy",
                        reason="Derivazione tecnica consentita dalla configurazione.",
                    )
                )
        return {"count": len(decisions), "decisions": decisions}

    def correct(
        self,
        candidate_id,
        payload,
        actor_id=None,
        reason="Correzione",
        expected_head=None,
    ):
        actor_id = actor_id or self.store.config()["actor_id"]
        with self.store.connect(True) as conn:
            c = conn.execute(
                "SELECT * FROM candidate_states WHERE id=?", (candidate_id,)
            ).fetchone()
            if not c or not c["leaf"]:
                raise DomainError(
                    "not_leaf", "Candidato inesistente o già sostituito.", 409
                )
            if expected_head is not None and c["decision_id"] != expected_head:
                raise DomainError("review_head_conflict", "Review cambiata.", 409)
            self.validate(payload, conn)
            batch = uid("BATCH", ["correction", candidate_id, payload])
            cid = uid("CAND", [batch, payload["candidate_id"]])
            did = uid("DEC", [candidate_id, cid])
            conn.execute(
                "INSERT INTO reviews VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    did,
                    candidate_id,
                    "superseded",
                    "human",
                    actor_id,
                    reason,
                    c["decision_id"],
                    digest(payload),
                    did,
                    now(),
                ),
            )
            conn.execute(
                "INSERT INTO heads VALUES(?,?) ON CONFLICT(candidate_id) DO UPDATE SET decision_id=excluded.decision_id",
                (candidate_id, did),
            )
            conn.execute(
                "INSERT INTO batches VALUES(?,?,?,?)",
                (batch, "human_correction", "{}", now()),
            )
            conn.execute(
                "INSERT INTO candidates VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    cid,
                    batch,
                    payload["source_revision_id"],
                    payload["record_type"],
                    None,
                    canonical(payload),
                    candidate_id,
                    c["root_id"],
                    now(),
                ),
            )
            conn.execute("INSERT INTO candidate_batches VALUES(?,?)", (batch, cid))
            self._review(
                conn, cid, "confirmed", actor_id, "human", reason, None, None, False
            )
            if conn.execute(
                "SELECT 1 FROM supports WHERE candidate_id=?", (candidate_id,)
            ).fetchone():
                conn.execute(
                    "INSERT INTO reconciliation VALUES(?,?,?,NULL)",
                    (uid("REC", [candidate_id, did]), candidate_id, now()),
                )
        return {"candidate_id": cid, "batch_id": batch, "parent_id": candidate_id}

    def merge(self, batches: list[str] | None = None, strict: bool = False):
        created = 0
        linked = 0
        skipped = []
        with self.store.connect(True) as conn:
            query = "SELECT * FROM candidate_states"
            args = []
            if batches:
                query += (
                    " WHERE id IN (SELECT candidate_id FROM candidate_batches WHERE batch_id IN ("
                    + ",".join("?" for _ in batches)
                    + "))"
                )
                args = batches
            candidates = conn.execute(query, args).fetchall()
            ineligible = [
                c
                for c in candidates
                if c["state"] != "confirmed"
                or not c["leaf"]
                or not c["current_revision"]
                or not c["current_parse"]
                or c["source_status"] != "active"
            ]
            if strict and ineligible:
                raise DomainError(
                    "strict_review",
                    "Il batch contiene candidati non eleggibili; nessun merge eseguito.",
                    409,
                )
            for c in candidates:
                if c in ineligible:
                    skipped.append(
                        {
                            "id": c["id"],
                            "reason": c["state"] if c["leaf"] else "superseded",
                        }
                    )
                    continue
                p = json.loads(c["payload"])
                kind = p["record_type"]
                if kind == "candidate_fact":
                    semantic = {
                        "entity_name": name_key(p["entity_name"]),
                        "property_name": name_key(p["property_name"]),
                        "property_value": p["property_value"],
                    }
                    payload = {
                        k: p[k]
                        for k in (
                            "entity_name",
                            "property_name",
                            "property_value",
                            "fact_type",
                        )
                    }
                    payload["assertion_type"] = p["assertion_type"]
                    kind = "fact"
                elif kind == "candidate_relation":
                    semantic = {
                        k: name_key(p[k])
                        for k in ("source_entity", "relation_type", "target_entity")
                    }
                    semantic["attributes"] = p.get("attributes", {})
                    payload = {
                        k: p[k]
                        for k in ("source_entity", "relation_type", "target_entity")
                    }
                    payload["attributes"] = p.get("attributes", {})
                    kind = "relation"
                elif kind == "temporal_interval":
                    from dslm3.temporal import validate_interval

                    validate_interval(p, strict=True)
                    payload = {
                        k: v
                        for k, v in p.items()
                        if k
                        in {
                            "target_subject_type",
                            "target_subject_id",
                            "normalized_start",
                            "normalized_end",
                            "original_precision",
                            "timezone_status",
                            "timezone_value",
                            "bounds_semantics",
                        }
                    }
                    semantic = payload
                    kind = "interval"
                    count = conn.execute(
                        "SELECT COUNT(*) FROM objects WHERE kind='interval' AND json_extract(payload,'$.target_subject_id')=?",
                        (p["target_subject_id"],),
                    ).fetchone()[0]
                    if (
                        count >= self.store.config()["max_intervals"]
                        and not conn.execute(
                            "SELECT 1 FROM objects WHERE semantic_key=?",
                            (digest([kind, semantic]),),
                        ).fetchone()
                    ):
                        raise DomainError(
                            "interval_budget", "Limite intervalli raggiunto."
                        )
                else:
                    skipped.append(
                        {"id": c["id"], "reason": "retained_non_materialized_type"}
                    )
                    continue
                key = digest([kind, semantic])
                object_id = uid(
                    {"fact": "FACT", "relation": "REL", "interval": "INT"}[kind],
                    semantic,
                )
                created += conn.execute(
                    "INSERT OR IGNORE INTO objects VALUES(?,?,?,?,?)",
                    (object_id, kind, key, canonical(payload), now()),
                ).rowcount
                linked += conn.execute(
                    "INSERT OR IGNORE INTO supports VALUES(?,?,?,?)",
                    (object_id, c["id"], c["decision_id"], now()),
                ).rowcount
        return {"created": created, "supports_added": linked, "skipped": skipped}

    def reconcile(self):
        # Effective views already exclude revoked/non-leaf supports. The explicit
        # acknowledgment closes pending export gates without modifying history.
        with self.store.connect(True) as conn:
            count = conn.execute(
                "UPDATE reconciliation SET closed_at=? WHERE closed_at IS NULL",
                (now(),),
            ).rowcount
        return {"closed": count}

    def objects(self, effective=True):
        rows = self.store.rows(
            "SELECT * FROM "
            + ("effective_objects" if effective else "objects")
            + " ORDER BY kind,id"
        )
        for r in rows:
            r["payload"] = json.loads(r["payload"])
            r["supports"] = self.store.rows(
                "SELECT s.*,c.payload AS candidate_payload,c.rule FROM "
                + ("effective_supports" if effective else "supports")
                + " s JOIN candidates c ON c.id=s.candidate_id WHERE object_id=? ORDER BY candidate_id",
                (r["id"],),
            )
            for s in r["supports"]:
                s["candidate_payload"] = json.loads(s["candidate_payload"])
        return rows

    def conflicts(self):
        objects = self.objects()
        groups = defaultdict(list)
        intervals = defaultdict(list)
        for o in objects:
            if o["kind"] == "interval":
                intervals[o["payload"]["target_subject_id"]].append(o["payload"])
            if o["kind"] == "fact":
                p = o["payload"]
                groups[
                    (name_key(p["entity_name"]), name_key(p["property_name"]))
                ].append(o)
        conflicts = []
        for group, items in groups.items():
            for a, b in combinations(items, 2):
                if canonical(a["payload"]["property_value"]) == canonical(
                    b["payload"]["property_value"]
                ):
                    continue
                if intervals[a["id"]] and intervals[b["id"]]:
                    from dslm3.temporal import overlap

                    if not any(
                        overlap(x, y)
                        for x in intervals[a["id"]]
                        for y in intervals[b["id"]]
                    ):
                        continue
                conflicts.append(
                    {
                        "id": uid("CONFLICT", sorted([a["id"], b["id"]])),
                        "reason": "different_values_same_property",
                        "entity": a["payload"]["entity_name"],
                        "property": a["payload"]["property_name"],
                        "left": a["id"],
                        "right": b["id"],
                        "left_value": a["payload"]["property_value"],
                        "right_value": b["payload"]["property_value"],
                    }
                )
        return conflicts
