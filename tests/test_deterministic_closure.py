"""Closure acceptance: explicit pseudorecord and pinned derivation oracles."""

import importlib
import hashlib
import io
import json
import subprocess
import sys
import zipfile

import pytest

from dslm3.deterministic import inventory, planned
from dslm3.parsers.sql import parse_sql
from dslm3.parsers.documents import parse_workbook, EXCEL_DEFAULTS
from dslm3.common import uid
from dslm3.resolution import Resolver
from test_deterministic_core import audit, evidence, prepared
from test_deterministic_oracle import V1_ROOT, V1_SHA


def test_pinned_v1_oracle_source_inventory():
    from pathlib import Path

    root = Path(__file__).parents[1]
    manifest = json.loads(
        (root / "docs/oracle_v1_inventory.json").read_text(encoding="utf-8")
    )
    assert manifest["v1_commit"] == V1_SHA
    for entry in manifest["files"]:
        data = subprocess.run(
            ["git", "-C", str(V1_ROOT), "show", V1_SHA + ":" + entry["path"]],
            capture_output=True,
            check=True,
        ).stdout
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
        assert len(data) == entry["bytes"]
    audit("G15-oracle-inventory", "pinned original modules and slices", manifest)


def test_trigger_new_old_g05_table_binding_and_schema_diagnostics(tmp_path):
    ddl = "CREATE TABLE T(ID NUMBER, A NUMBER, B NUMBER);"
    trigger = """CREATE TRIGGER TRG BEFORE UPDATE ON T FOR EACH ROW
    BEGIN :NEW.A := :OLD.A + :NEW.B;
    IF :OLD.ID <> :NEW.ID THEN :NEW.B := 0; END IF; END; /"""
    app, k = prepared(tmp_path, ddl + trigger)
    relations = [
        c["payload"] for c in k.candidates() if c["record_type"] == "candidate_relation"
    ]
    actual = {
        (r["relation_type"], r["source_entity"], r["target_entity"]) for r in relations
    }
    expected = {
        ("trigger_on", "TRG", "T"),
        ("writes_to", "TRG", "T.A"),
        ("writes_to", "TRG", "T.B"),
        ("reads_from", "TRG", "T.A"),
        ("reads_from", "TRG", "T.B"),
        ("reads_from", "TRG", "T.ID"),
    }
    assert actual == expected
    assert all(c["state"] == "pending" for c in k.candidates())
    k.review_many(
        [c["id"] for c in k.candidates()],
        "confirmed",
        reason="G05 explicit pseudorecord structure",
    )
    k.merge()
    serialized = json.dumps(k.objects())
    assert '"NEW"' not in serialized and '"OLD"' not in serialized
    assert '"NEW.' not in serialized and '"OLD.' not in serialized
    invalid = parse_sql(
        trigger.replace(":NEW.A", ":NEW.MISSING").replace(":OLD.ID", ":OLD.ABSENT"),
        "oracle",
        {"T": ["ID", "A", "B"]},
    )
    errors = [
        d for d in invalid.diagnostics if d["reason"] == "column_absent_from_schema"
    ]
    assert {d["column"] for d in errors} == {"MISSING", "ABSENT"}
    assert all(d["table"] == "T" for d in errors)
    assert not any(
        e["data"].get("target") in {"T.MISSING", "T.ABSENT"} for e in invalid.evidence
    )
    audit(
        "G05-trigger",
        sorted(expected),
        {"relations": sorted(actual), "diagnostics": errors},
    )


@pytest.fixture
def pinned_v1(tmp_path, monkeypatch):
    """Import exact pinned sources, including dependencies, never local v1 edits."""
    archive = subprocess.run(
        ["git", "-C", str(V1_ROOT), "archive", "--format=zip", V1_SHA, "src/dsl_mngr"],
        capture_output=True,
        check=True,
    ).stdout
    destination = tmp_path / "pinned"
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        for name in bundle.namelist():
            if not name.endswith(".py"):
                continue
            path = (destination / name).resolve()
            assert path.is_relative_to(destination.resolve())
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(bundle.read(name))
    before = {k: v for k, v in sys.modules.items() if k.startswith("dsl_mngr")}
    for name in before:
        del sys.modules[name]
    monkeypatch.syspath_prepend(str(destination / "src"))
    try:
        yield lambda name: importlib.import_module("dsl_mngr.core." + name)
    finally:
        for name in list(sys.modules):
            if name.startswith("dsl_mngr"):
                del sys.modules[name]
        sys.modules.update(before)


def fragment(kind, metadata, identity="F1", **extra):
    return {
        "fragment_id": identity,
        "fragment_type": kind,
        "source_revision_id": "R1",
        "path_or_selector": "/" + identity,
        "line_start": 1,
        "line_end": 1,
        "text": "explicit evidence",
        "metadata_json": metadata,
        **extra,
    }


def test_pinned_v1_schema_resolution_information(pinned_v1):
    old = pinned_v1("schema_resolution")
    index = old.StructuralIndex.from_active_fragments(
        [
            fragment("ddl_table", {"table_name": "T"}),
            fragment("ddl_column", {"table_name": "T", "column_name": "A"}),
            fragment("sql_procedure", {"procedure_name": "P"}),
        ]
    )
    resolver = Resolver(
        evidence("CREATE TABLE T(A NUMBER); CREATE PROCEDURE P AS BEGIN NULL; END; /")
    )
    for target, method, kind in [
        ("T", "resolve_table", "data_object"),
        ("MISSING", "resolve_table", "data_object"),
        ("T.A", "resolve_column", "column"),
        ("MISSING.A", "resolve_column", "column"),
        ("P", "resolve_code_unit", "code_unit"),
    ]:
        previous = getattr(index, method)(target)
        current = resolver.resolve(target, kind)
        assert current["status"] == previous.status
        if previous.status == "resolved":
            assert current["canonical_target"] == previous.canonical_target
            assert current["basis_evidence_ids"]
    assert index.resolve_column("T.B").status == "inconsistent"
    missing = resolver.resolve("T.B", "column")
    # v3 keeps the blocked-column category, but must preserve the known-parent
    # evidence and explicit incompatibility that v1 exposed as inconsistent.
    assert missing["status"] == "unresolved"
    assert missing["reason_code"] == "column_absent_from_schema"
    assert missing["prerequisites"][0]["canonical_target"] == "T"
    assert missing["basis_evidence_ids"]
    quoted = Resolver(evidence('CREATE TABLE "T.X"("A.B" NUMBER);'))
    assert (
        quoted.resolve('"T.X"."Missing.Dot"', "column")["reason_code"]
        == "column_absent_from_schema"
    )
    audit(
        "G15-schema-resolution", "v1 statuses and known-parent incompatibility", missing
    )


def test_pinned_v1_candidate_derivation_slice21(pinned_v1, tmp_path):
    old = pinned_v1("candidate_derivation")
    fragments = [
        fragment(
            "ddl_column",
            {
                "table_name": "T",
                "column_name": c,
                "data_type": "NUMBER",
                "nullable": True,
            },
            c,
        )
        for c in ["B", "A"]
    ]
    first, issues = old.derive_rule_records("ddl_column_fact/1", fragments + fragments)
    again, _ = old.derive_rule_records("ddl_column_fact/1", list(reversed(fragments)))
    assert not issues and first == again and len(first) == 2
    app, k = prepared(tmp_path / "v3", "CREATE TABLE T(A NUMBER, B NUMBER);")
    payloads = [c["payload"] for c in k.candidates()]
    for candidate in first:
        assert any(
            p.get("entity_name") == candidate["entity_name"]
            and p.get("property_name") == "data_type"
            and p["property_value"] == candidate["property_value"]
            for p in payloads
        )
    ids = {c["id"] for c in k.candidates()}
    k.derive()
    assert {c["id"] for c in k.candidates()} == ids
    assert all(c["state"] == "pending" for c in k.candidates())
    assert not k.objects()
    bad, issues = old.derive_rule_records(
        "ddl_column_fact/1", [{**fragments[0], "path_or_selector": None}]
    )
    assert not bad and issues
    fk = fragment(
        "ddl_constraint",
        {
            "constraint_kind": "foreign_key",
            "table_name": "T",
            "references_table": "P",
            "columns": ["B", "A"],
            "references_columns": ["Y", "X"],
            "constraint_name": "FK",
        },
    )
    legacy_fk, issues = old.derive_rule_records(
        "ddl_fk_relation/1", [fk], context={"ddl_tables": {"p"}}
    )
    assert not issues and len(legacy_fk) == 1
    schema = evidence(
        "CREATE TABLE P(X NUMBER,Y NUMBER,PRIMARY KEY(X,Y)); CREATE TABLE T(A NUMBER,B NUMBER,CONSTRAINT FK FOREIGN KEY(B,A) REFERENCES P(Y,X));"
    )
    relation = next(
        p["payload"]
        for p in planned(inventory(schema))
        if p["payload"].get("relation_type") == "foreign_key"
    )
    # Verified v1 defect: _text_list sorts each FK column list independently.
    # v3 must preserve source order, not reproduce this information loss.
    assert legacy_fk[0]["columns"] == ["A", "B"]
    assert legacy_fk[0]["referenced_columns"] == ["X", "Y"]
    assert relation["attributes"]["columns"] == ["B", "A"]
    assert relation["attributes"]["target_columns"] == ["Y", "X"]
    rejected, issues = old.derive_rule_records("ddl_fk_relation/1", [fk])
    assert not rejected and issues
    no_target = inventory(
        [
            e
            for e in schema
            if e["data"].get("name") != "P" and e["data"].get("table") != "P"
        ]
    )
    assert not any(
        p["payload"].get("relation_type") == "foreign_key" for p in planned(no_target)
    )
    audit(
        "G15-slice21",
        "ordered FK, idempotence, pending, missing target",
        {"legacy_fk": legacy_fk, "v3_fk": relation},
    )


def test_pinned_v1_slice25_excel_candidates(pinned_v1, tmp_path, monkeypatch):
    import socket
    import urllib.request

    def no_network(*args, **kwargs):
        pytest.fail("Slice 25 oracle must not dereference external links")

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    path = "tests/fixtures/slice_25/candidate_workbook.xlsx"
    data = subprocess.run(
        ["git", "-C", str(V1_ROOT), "show", V1_SHA + ":" + path],
        capture_output=True,
        check=True,
    ).stdout
    checksums = json.loads(
        subprocess.run(
            [
                "git",
                "-C",
                str(V1_ROOT),
                "show",
                V1_SHA + ":tests/fixtures/slice_25/checksums.json",
            ],
            capture_output=True,
            check=True,
        ).stdout
    )
    assert hashlib.sha256(data).hexdigest() == checksums["candidate_workbook.xlsx"]
    source = tmp_path / "candidate_workbook.xlsx"
    source.write_bytes(data)
    preflight = pinned_v1("ooxml_preflight")
    original = preflight.preflight_ooxml(
        io.BytesIO(data),
        original_name=source.name,
        source_hash=hashlib.sha256(data).hexdigest(),
        limits=preflight.ExcelLimits.from_config(EXCEL_DEFAULTS),
    )
    built = preflight.build_workbook_manifest(
        io.BytesIO(data),
        preflight=original,
        source_revision_id="R1",
        fragment_id_by_sequence={},
        next_fragment_number=1,
    )
    current = parse_workbook(source, data, "R1", {})
    # Actual pinned v1 output, not a golden produced by the v3 parser.
    assert current.artifacts["workbook_manifest.json"] == built.manifest
    rows = [
        {**e, "id": uid("EV", [i, e]), "revision_id": "R1", "path": source.name}
        for i, e in enumerate(current.evidence)
    ]
    candidates = [p["payload"] for p in planned(inventory(rows))]
    definitions = [
        p["property_value"]
        for p in candidates
        if p.get("property_name") == "definition"
    ]
    old = pinned_v1("candidate_derivation")
    fragments = {
        f["fragment_id"]: fragment(
            "excel_region",
            {},
            f["fragment_id"],
            text=json.dumps(f),
            path_or_selector=f["locator"]["range"],
        )
        for f in built.fragments
    }
    inputs = old._excel_manifest_objects(
        built.manifest, manifest_id="M1", fragment_rows=fragments
    )
    legacy_candidates = []
    for rule in old.EXCEL_DERIVATION_RULE_CATALOG:
        kind = rule.removeprefix("excel_").split("/")[0].removesuffix("_fact")
        derived, issues = old.derive_rule_records(
            rule, [f for f in inputs if f["excel_kind"] == kind]
        )
        assert not issues
        legacy_candidates.extend(derived)
    refs = [c for c in legacy_candidates if c["record_type"] == "candidate_relation"]
    assert {r["technical_attributes"]["reference_kind"] for r in refs} == {
        "table",
        "region",
        "named_range",
    }
    regions = [d for d in definitions if d["object_type"] == "excel_region"]
    for old_candidate in legacy_candidates:
        attrs = old_candidate["technical_attributes"]
        kind = old_candidate.get("property_value", "").removeprefix("excel_")
        if kind == "region":
            assert any(
                d["cells"] == attrs["cell_attributes"]
                and d["sheet"]["name"] == attrs["sheet_name"]
                and d["start_cell"] == attrs["start_cell"]
                and d["end_cell"] == attrs["end_cell"]
                for d in regions
            )
        elif kind in {"named_range", "table"}:
            assert any(
                all(
                    (d.get("sheet_name") or d["refers_to"].split("!")[0].strip("'"))
                    == v
                    if k == "sheet_name"
                    else d.get("object_name" if k == "name" else k) == v
                    for k, v in attrs.items()
                )
                for d in definitions
                if d["object_type"] == "excel_" + kind
            )
        elif kind == "sheet":
            assert any(
                d["sheet_name"] == attrs["sheet_name"]
                and d["visibility"] == attrs["visibility"]
                and d["dimensions"] == attrs["dimensions"]
                for d in definitions
                if d["object_type"] == "excel_sheet"
            )
        elif kind == "workbook":
            retained = next(
                d["manifest"]
                for d in definitions
                if d["object_type"] == "excel_workbook"
            )
            for key in [
                "calculation_properties",
                "date_system",
                "macro_presence",
                "part_name",
            ]:
                assert retained["workbook"][key] == attrs[key]
            assert retained["source_revision"]["extension"] == attrs["source_extension"]
            assert (
                retained["source_revision"]["package_content_type"]
                == attrs["package_content_type"]
            )
        elif old_candidate["record_type"] == "candidate_relation":
            # v3 stores full formulas and scoped target declarations, not the
            # legacy regex-derived internal edges. No information is discarded.
            assert any(
                d["sheet"]["name"] == attrs["sheet_name"]
                and any(
                    c["coordinate"] == attrs["source_coordinate"]
                    and c["formula"] == attrs["formula"]
                    for c in d["cells"]
                )
                for d in regions
            )
    repeated = [
        c
        for c in candidates
        if c.get("fact_type") == "excel_named_range"
        and c["property_value"]["object_name"] == "LocalBlock"
    ]
    assert len(repeated) == len({c["entity_name"] for c in repeated}) == 2
    assert all(p["evidence_text"] and p["evidence_id"] for p in candidates)
    audit(
        "G15-slice25",
        "pinned workbook, all six derivation rules, formula/cache/scope/anchors",
        {
            "v1_commit": V1_SHA,
            "workbook_sha256": hashlib.sha256(data).hexdigest(),
            "legacy_candidates": legacy_candidates,
            "v3_candidates": candidates,
        },
    )


def test_pinned_v1_slice32_scope_and_event_information(pinned_v1):
    old = pinned_v1("db_code_parser")
    sql = """CREATE PROCEDURE P_UPDATE(P_ID IN NUMBER) AS BEGIN
    UPDATE T_OUT o SET o.A=o.A+1 WHERE o.ID=(SELECT i.ID FROM T_IN i
    JOIN T_AUX a ON a.ID=i.AUX_ID WHERE i.REQUEST_ID=P_ID AND i.OUT_ID=o.ID);
    END; /"""
    previous = old.parse_db_code_text(sql, old.DbCodeOptions()).procedures[0]
    new = parse_sql(
        sql,
        "oracle",
        {
            "T_OUT": ["ID", "A"],
            "T_IN": ["ID", "AUX_ID", "REQUEST_ID", "OUT_ID"],
            "T_AUX": ["ID"],
        },
    )
    for relation, targets in [
        ("reads_from", previous.reads),
        ("writes_to", previous.writes),
    ]:
        actual = {
            e["data"]["target"]
            for e in new.evidence
            if e["type"] == "sql_dependency" and e["data"]["relation_type"] == relation
        }
        assert set(targets) <= actual
        assert not {"P_ID", "T_IN.T_IN", "T_IN.T_AUX"} & actual
    derivation = pinned_v1("candidate_derivation")
    fragments = [
        fragment(
            "log_event",
            {
                "component": "scanner",
                "event_kind": kind,
                "level": "INFO",
                "message": kind,
                "observed_identifiers": {},
                "timestamp": f"2026-09-01 08:00:0{i}",
            },
            f"F{i}",
        )
        for i, kind in enumerate(["start", "processed", "processed", "end"])
    ]
    events, issues = derivation.derive_rule_records(
        "log_event_observation/2", fragments
    )
    assert not issues and len({e["entity_name"] for e in events}) == 4
    rows = [
        {
            "id": f["fragment_id"],
            "revision_id": "R1",
            "type": "log_event",
            "kind": "fragment",
            "data": f["metadata_json"],
            "text": f["text"],
            "locator": {"line_start": i + 1},
        }
        for i, f in enumerate(fragments)
    ]
    current = [
        p["payload"]
        for p in planned(inventory(rows))
        if p["payload"].get("fact_type") == "log_event"
    ]
    assert len({c["entity_name"] for c in current}) == len(events)
    for previous, new in zip(events, current):
        assert new["property_value"]["event_kind"] == previous["property_value"]
        for key in ["component", "level", "message", "observed_identifiers"]:
            assert new["property_value"][key] == previous[key]
        assert new["property_value"]["timestamp"] == previous["observation_timestamp"]
    audit(
        "G15-slice32",
        "scope-aware dependencies and occurrence identities",
        {"v1_events": events, "v3_events": current},
    )


def test_pinned_v1_slice32_multivalue_representation(pinned_v1, tmp_path):
    from test_knowledge import payload

    old = pinned_v1("conflict_semantics")
    assert old.fact_conflict_semantics("entity_alias", "alias") == old.MULTI_VALUE
    assert old.fact_conflict_semantics("log_event", "event_kind") == old.EVENT
    assert old.fact_conflict_semantics("unknown_type", "status") == old.SINGLE_VALUE
    app, k = prepared(tmp_path, "CREATE TABLE T(ID NUMBER);")
    candidates = [
        {**payload(app, value, "state_" + value), "property_name": "status"}
        for value in ["open", "closed"]
    ]
    # v3 expresses a set of aliases as independently supported relations. It
    # does not import v1's table of property-name exceptions into conflict logic.
    for alias in ["A", "B"]:
        base = payload(app, candidate_id="alias_" + alias)
        candidates.append(
            {
                k: v
                for k, v in base.items()
                if k
                not in {"entity_name", "property_name", "property_value", "fact_type"}
            }
            | {
                "record_type": "candidate_relation",
                "source_entity": "Business",
                "relation_type": "has_alias",
                "target_entity": alias,
            }
        )
    imported = k.import_candidates(candidates, "manual:oracle-slice32")
    assert k.merge()["created"] == 0
    k.review_many(
        imported["candidate_ids"],
        "confirmed",
        reason="Explicit oracle representation mapping",
    )
    k.merge()
    assert len(k.conflicts()) == 1 and k.conflicts()[0]["property"] == "status"
    assert len([o for o in k.objects() if o["kind"] == "relation"]) == 2


def test_workbook_contract_invalidates_only_workbook_cache(tmp_path, monkeypatch):
    from dslm3.service import Application
    from pathlib import Path

    app = Application(tmp_path)
    fixture = Path(__file__).parent / "fixtures/slice_24/structural_workbook.xlsx"
    app.ingest(fixture.name, fixture.read_bytes())
    app.ingest("t.sql", b"CREATE TABLE T(ID NUMBER);")
    initial = app.parse_all()
    assert initial["errors"] == 0
    first = {e["id"] for e in app.evidence() if e["type"] == "excel_named_range"}
    assert all(r["cached"] for r in app.parse_all()["results"])
    monkeypatch.setattr("dslm3.parsers.documents.WORKBOOK_CONTRACT", 1)
    replay = app.parse_all()
    assert sum(bool(r.get("cached")) for r in replay["results"]) == 1
    assert {r["parse_id"] for r in replay["results"] if not r.get("cached")}.isdisjoint(
        {r["parse_id"] for r in initial["results"]}
    )
    # Equivalent parser output retains semantic evidence identity across a
    # version-key cache miss; administrative parse identity must change.
    assert first == {
        e["id"] for e in app.evidence() if e["type"] == "excel_named_range"
    }
