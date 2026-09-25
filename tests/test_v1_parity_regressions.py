from dslm3.exports import Exports
from dslm3.knowledge import Knowledge, POLICIES
from dslm3.parsers.base import ParseResult, chunks
from dslm3.service import Application
from dslm3.temporal import Temporal


def _auto_merge(app):
    knowledge = Knowledge(app)
    knowledge.derive()
    app.store.configure({"automatic_policies": list(POLICIES.values())})
    knowledge.auto_review()
    knowledge.merge()
    return knowledge


def test_forms_items_keep_block_identity_and_button_operation_stays_pending(tmp_path):
    app = Application(tmp_path / "forms")
    app.ingest(
        "form.xml",
        b"""<?xml version=\"1.0\"?>
<form name=\"FORM_1\">
  <block name=\"BLOCK_A\" table=\"TABLE_A\">
    <item name=\"ID\" column=\"ID\"/>
  </block>
  <block name=\"BLOCK_B\" table=\"TABLE_B\">
    <item name=\"ID\" column=\"ID\"/>
  </block>
  <button name=\"RUN\" operation=\"DO_WORK\"/>
</form>
""",
    )
    app.parse_all()
    knowledge = Knowledge(app)
    knowledge.derive()
    app.store.configure({"automatic_policies": list(POLICIES.values())})
    knowledge.auto_review()

    candidates = knowledge.candidates()
    entity_names = {
        c["payload"].get("entity_name")
        for c in candidates
        if c["record_type"] == "candidate_fact"
    }
    assert "FORM_1.BLOCK_A.ID" in entity_names
    assert "FORM_1.BLOCK_B.ID" in entity_names

    mapping_sources = {
        c["payload"].get("source_entity")
        for c in candidates
        if c["record_type"] == "candidate_relation"
        and c["payload"].get("relation_type") == "maps_to"
    }
    assert {"FORM_1.BLOCK_A.ID", "FORM_1.BLOCK_B.ID"} <= mapping_sources

    operation = next(c for c in candidates if c["rule"] == "xml_button_operation")
    assert operation["policy"] == "explicit_xml_button_operation_pending/1"
    assert operation["state"] == "pending"


def test_deterministic_fact_types_and_relation_epistemics_survive_export(tmp_path):
    app = Application(tmp_path / "export")
    app.ingest(
        "schema.sql",
        b"CREATE TABLE A(ID NUMBER PRIMARY KEY); "
        b"CREATE TABLE B(ID NUMBER, A_ID NUMBER REFERENCES A(ID));",
    )
    app.parse_all()
    _auto_merge(app)
    snapshot = Exports(app).snapshot()["content"]

    fact_types = {
        fact["fact_type"]
        for entity in snapshot["entities"]
        for fact in entity["facts"]
    }
    assert "database_table" in fact_types
    assert "database_column" in fact_types

    relation = next(r for r in snapshot["relations"] if "foreign_key" in r["relation_type"])
    assert relation["assertion_type"] == "explicit"
    assert relation["confidence"] == "high"
    support = snapshot["traceability"]["relations"][relation["relation_id"]][0]
    assert support["assertion_type"] == "explicit"
    assert support["confidence"] == "high"


def test_structural_chunker_preserves_text_and_heading_context():
    text = (
        "# First\n\n"
        "alpha beta gamma delta epsilon\n\n"
        "## Second\n\n"
        "zeta eta theta iota kappa lambda\n"
    )
    result = ParseResult("test")
    chunks(result, text, size=36, representation="test")
    assert "".join(item["text"] for item in result.evidence) == text
    assert all(len(item["text"]) <= 36 for item in result.evidence)
    assert any(
        item["locator"].get("heading_path") == ["First", "Second"]
        for item in result.evidence
    )


def test_diff_tracks_value_correction_as_semantic_change(tmp_path):
    app = Application(tmp_path / "diff")
    app.ingest("schema.sql", b"CREATE TABLE A(ID NUMBER PRIMARY KEY);")
    app.parse_all()
    evidence = app.evidence()[0]
    knowledge = Knowledge(app)
    payload = {
        "record_type": "candidate_fact",
        "candidate_id": "business_1",
        "source_revision_id": evidence["revision_id"],
        "evidence_id": evidence["id"],
        "evidence_text": evidence["text"],
        "assertion_type": "inferred",
        "confidence": "medium",
        "fact_type": "business_rule",
        "entity_name": "P1",
        "property_name": "response_minutes",
        "property_value": 30,
    }
    imported = knowledge.import_candidates([payload], "ai:test")
    knowledge.review_many(imported["candidate_ids"], "confirmed")
    knowledge.merge()
    exports = Exports(app)
    before = exports.snapshot()

    replacement = {**payload, "candidate_id": "business_2", "property_value": 45}
    corrected = knowledge.correct(imported["candidate_ids"][0], replacement)
    knowledge.merge([corrected["batch_id"]])
    knowledge.reconcile()
    after = exports.snapshot()
    diff = exports.diff(before["id"], after["id"])

    changes = [
        change
        for change in diff["changes"]
        if change["category"] == "structure"
        and "response_minutes" in change.get("semantic_key", "")
    ]
    assert len(changes) == 1
    assert changes[0]["change"] == "changed"


def test_temporal_independence_uses_source_family_inside_same_revision(tmp_path):
    app = Application(tmp_path / "temporal")
    revision = app.ingest("source.txt", b"same source")["revision_id"]
    temporal = Temporal(app)
    temporal.add_raw(
        revision,
        "source_revision",
        revision,
        [
            {
                "source_key": "declared",
                "raw_value": "2024",
                "source_format": "text_declaration",
                "date_role": "competence_year",
                "initial_reliability": "high",
                "correlation_family": "explicit_text",
            },
            {
                "source_key": "metadata",
                "raw_value": "2024",
                "source_format": "metadata",
                "date_role": "competence_year",
                "initial_reliability": "medium",
                "correlation_family": "document_metadata",
            },
        ],
    )
    result = temporal.consolidate("source_revision", revision)
    group = next(g for g in result["groups"] if g["role"] == "competence_year")
    assert group["independent_sources"] == 2
    assert group["assessment"] == "concordant"
