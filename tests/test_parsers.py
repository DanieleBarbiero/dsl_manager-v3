from pathlib import Path
from dataclasses import replace
import io, json, hashlib
import pytest
from dslm3.parsers.sql import parse_sql, identify, catalog
from dslm3.parsers.documents import parse_xml, parse_log, EXCEL_DEFAULTS
from dslm3.vendor.ooxml_preflight import (
    ExcelLimits,
    preflight_ooxml,
    build_workbook_manifest,
    OoxmlPreflightError,
)

VEGA = Path(__file__).parents[1] / "src/dslm3/resources/vega"


def test_vega_sql_scope_regression():
    ddl = parse_sql((VEGA / "database/schema_vega.sql").read_text())
    columns = [e["data"] for e in ddl.evidence if e["type"] == "ddl_column"]
    assert len(columns) == 9
    schema = {}
    for c in columns:
        schema.setdefault(c["table"], []).append(c["column"])
    r = parse_sql((VEGA / "plsql/logica_vega.sql").read_text(), schema=schema)
    targets = {e["data"]["target"] for e in r.evidence if e["type"] == "sql_dependency"}
    assert "ARTICOLO.ID_RICHIESTA" not in targets
    assert "ARTICOLO.RICHIESTA_RICAMBIO" not in targets
    assert {"RICHIESTA_RICAMBIO.ID_RICHIESTA", "ARTICOLO.QTA_DISPONIBILE"} <= targets
    assert {e["type"] for e in r.evidence} >= {"sql_procedure", "sql_trigger"}
    assert not r.diagnostics


def test_forms_item_field_and_operation():
    r = parse_xml((VEGA / "forms/frm_richiesta.xml").read_text())
    assert len([e for e in r.evidence if e["type"] == "xml_field"]) == 4
    assert any(
        e["data"]
        == {
            "source": "FRM_RICHIESTA.BTN_PRENOTA",
            "relation_type": "calls",
            "target": "PRC_PRENOTA_ARTICOLO",
        }
        for e in r.evidence
    )
    assert all(e["locator"]["xpath"] for e in r.evidence)


def test_log_occurrences():
    r = parse_log((VEGA / "logs/vega_2026.log").read_text())
    assert len(r.evidence) == 5
    assert len({e["data"]["occurrence_line"] for e in r.evidence}) == 5


def test_xml_entities_rejected():
    with pytest.raises(ValueError):
        parse_xml(
            '<!DOCTYPE x [<!ENTITY bad SYSTEM "file:///etc/passwd">]><x>&bad;</x>'
        )


@pytest.mark.parametrize(
    "dialect,sql",
    [
        ("oracle", "CREATE TABLE a(id NUMBER, name VARCHAR2(30));"),
        ("postgres", "CREATE TABLE a(id SERIAL, value JSONB);"),
        ("mysql", "CREATE TABLE a(id INT AUTO_INCREMENT PRIMARY KEY);"),
        ("tsql", "CREATE TABLE dbo.a(id INT IDENTITY(1,1), name NVARCHAR(30));"),
        ("sqlite", "CREATE TABLE a(id INTEGER PRIMARY KEY AUTOINCREMENT);"),
        ("bigquery", "CREATE TABLE a(id INT64, name STRING);"),
        ("snowflake", "CREATE TABLE a(id NUMBER, data VARIANT);"),
        ("duckdb", "CREATE TABLE a(id INTEGER, name VARCHAR);"),
        ("spark", "CREATE TABLE a(id INT, name STRING);"),
        ("teradata", "CREATE TABLE a(id INTEGER);"),
    ],
)
def test_dialect_ast(dialect, sql):
    r = parse_sql(sql, dialect)
    assert any(e["type"] == "ddl_table" for e in r.evidence)
    assert not any(e["type"] == "sql_unparsed" for e in r.evidence)


def test_legacy_and_unknown_version_honesty():
    i = identify("-- database: oracle 8i\nSELECT * FROM x,y WHERE x.id=y.id(+);")
    assert i["declared_version"] == "8i"
    assert "oracle_outer_join_plus" in i["legacy_features"]
    assert identify("SELECT 1")["basis"] == "ambiguous"
    assert len(catalog()["ast_dialects"]) >= 30


def test_sql_literals_and_unrecognized_preserved():
    r = parse_sql(
        "CREATE PROCEDURE p AS BEGIN EXECUTE IMMEDIATE 'DELETE FROM SECRET'; END;\n/",
        "oracle",
    )
    assert not any(e["data"].get("target") == "SECRET" for e in r.evidence)
    assert any(d["reason"] == "dynamic_sql_unresolved" for d in r.diagnostics)
    r = parse_sql("THIS IS GARBAGE SQL", "oracle")
    assert any(e["type"] == "sql_unparsed" for e in r.evidence)


def build(path, limits=None):
    data = path.read_bytes()
    limits = limits or ExcelLimits.from_config(EXCEL_DEFAULTS)
    p = preflight_ooxml(
        io.BytesIO(data),
        original_name=path.name,
        source_hash=hashlib.sha256(data).hexdigest(),
        limits=limits,
    )
    return build_workbook_manifest(
        io.BytesIO(data),
        preflight=p,
        source_revision_id="REV_SLICE24_STRUCTURAL",
        fragment_id_by_sequence={},
        next_fragment_number=1,
    )


def test_excel_exact_structural_contract_offline(monkeypatch):
    monkeypatch.setattr(
        "socket.create_connection", lambda *a, **k: pytest.fail("network not allowed")
    )
    p = Path(__file__).parent / "fixtures/slice_24/structural_workbook.xlsx"
    r = build(p)
    assert r.cell_count == 21 and r.region_count == 5
    cells = {c["coordinate"]: c for s in r.manifest["sheets"] for c in s["cells"]}
    assert (
        cells["D2"]["formula"] == "B2+C2"
        and cells["D2"]["cached_value"] == "3.5"
        and cells["D2"]["value"] is None
    )
    assert cells["E2"]["cached_value"] is None
    assert [s["visibility"] for s in r.manifest["sheets"]] == [
        "visible",
        "hidden",
        "very_hidden",
    ]
    assert r.manifest["external_links"][0]["disposition"] == "not_dereferenced"
    assert r.manifest == build(p).manifest
    golden = json.loads(
        (Path(__file__).parent / "fixtures/workbook_manifest_golden.json").read_text()
    )
    # Semantic IDs are supplied by the caller; normalize only this identifier.
    golden["source_revision"]["id"] = r.manifest["source_revision"]["id"]
    assert r.manifest == golden
    with pytest.raises(OoxmlPreflightError):
        build(p, replace(ExcelLimits.from_config(EXCEL_DEFAULTS), max_cells=20))


def test_macro_never_executed():
    r = build(Path(__file__).parent / "fixtures/slice_24/macro_workbook.xlsm")
    assert r.manifest["macros"]["executed"] is False
    assert (
        r.manifest["macros"]["content_hash"]
        == "0ced1464b3677e98f5e3a8c5d80135e18dc98dca39299f1a8cfd2a00999fbf9f"
    )


def test_oracle_package_members_and_mysql_delimiter():
    package = "CREATE OR REPLACE PACKAGE p AS PROCEDURE do_it(x NUMBER); FUNCTION f RETURN NUMBER; END p;\n/\nCREATE OR REPLACE PACKAGE BODY p AS PROCEDURE do_it(x NUMBER) IS BEGIN UPDATE a SET x=x+1; END; FUNCTION f RETURN NUMBER IS BEGIN RETURN 1; END; END p;\n/"
    r = parse_sql(package, "oracle")
    names = {e["data"].get("name") for e in r.evidence}
    assert {"P", "P.DO_IT", "P.F"} <= names
    assert not any(e["type"] == "sql_unparsed" for e in r.evidence)
    sql = "DELIMITER $$\nCREATE PROCEDURE p() BEGIN UPDATE a SET x=1; SELECT x FROM a; END$$\nDELIMITER ;"
    r = parse_sql(sql, "mysql")
    assert any(e["type"] == "sql_procedure" for e in r.evidence)
    assert any(e["data"].get("target") == "A.X" for e in r.evidence)


def test_cte_alias_not_invented_as_physical_table():
    r = parse_sql(
        "CREATE VIEW v AS WITH c AS (SELECT id FROM a) SELECT c.id FROM c;",
        "oracle",
        {"A": ["ID"]},
    )
    targets = {e["data"].get("target") for e in r.evidence}
    assert "A.ID" in targets and "C.ID" not in targets and "C" not in targets


@pytest.mark.parametrize(
    "sql,kind",
    [
        ("CREATE SYNONYM s FOR t;", "ddl_synonym"),
        (
            "CREATE DATABASE LINK l CONNECT TO u IDENTIFIED BY p USING 'db';",
            "ddl_database_link",
        ),
        ("CREATE MATERIALIZED VIEW v AS SELECT * FROM t;", "ddl_materialized view"),
    ],
)
def test_additional_oracle_objects(sql, kind):
    r = parse_sql(sql, "oracle")
    assert any(e["type"] == kind for e in r.evidence)
