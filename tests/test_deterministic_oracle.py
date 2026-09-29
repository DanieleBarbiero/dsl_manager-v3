"""Pinned read-only legacy oracle, not golden output generated from v3."""

import os
import subprocess
import sys
import types
from pathlib import Path

from dslm3.parsers.sql import parse_sql
from dslm3.parsers.documents import parse_xml
from dslm3.parsers.base import ParseResult, chunks

V1_SHA = "8b576eb605b2509ebe84785aae6b2d1e94046b8b"
V1_ROOT = Path(
    os.environ.get("DSLM3_V1_ROOT", str(Path(__file__).parents[2] / "dsl_manager-v1"))
)


def legacy(name, monkeypatch):
    path = "src/dsl_mngr/core/" + name + ".py"
    proc = subprocess.run(
        ["git", "-C", str(V1_ROOT), "show", V1_SHA + ":" + path],
        capture_output=True,
        check=True,
    )
    module = types.ModuleType("dsl_mngr.core." + name)
    monkeypatch.setitem(sys.modules, module.__name__, module)
    exec(compile(proc.stdout, V1_SHA + "/" + path, "exec"), module.__dict__)
    return module


def test_pinned_v1_ddl_oracle_superset(monkeypatch):
    v1 = legacy("ddl_parser", monkeypatch)
    source = """CREATE TABLE P(A NUMBER, B NUMBER, PRIMARY KEY(A,B));
    CREATE TABLE T(ID NUMBER PRIMARY KEY, A NUMBER NOT NULL, B NUMBER DEFAULT 0,
      CONSTRAINT FK_T_P FOREIGN KEY(A,B) REFERENCES P(A,B), CONSTRAINT U_T UNIQUE(A,B));
    CREATE UNIQUE INDEX IX_T ON T(A,B);"""
    old = v1.parse_ddl_text(source, v1.DdlOptions())
    new = parse_sql(source, "oracle").evidence
    tables = {e["data"]["name"] for e in new if e["type"] == "ddl_table"}
    cols = {e["data"]["name"]: e["data"] for e in new if e["type"] == "ddl_column"}
    cons = [e["data"] for e in new if e["type"] == "ddl_constraint"]
    for table in old.tables:
        assert table.full_name in tables
        for col in table.columns:
            c = cols[table.full_name + "." + col.name]
            assert c["datatype"] == col.data_type
            if col.nullable is False:
                assert c["nullable"] is False
            if col.primary_key:
                assert any(
                    x["constraint_type"] == "primary_key"
                    and col.name in x["columns"]
                    and x["table"] == table.full_name
                    for x in cons
                )
            if col.default is not None:
                assert c["default"]["present"] and c["default"]["sql"] == col.default
        for c in table.constraints:
            assert any(
                x["table"] == table.full_name
                and x["constraint_type"] == c.constraint_kind
                and x["columns"] == list(c.columns)
                and (
                    c.references_table is None
                    or x["target_table"] == c.references_table
                    and x["target_columns"] == list(c.references_columns)
                )
                for x in cons
            )
    for ix in old.indexes:
        actual = next(
            e["data"]
            for e in new
            if e["type"] == "ddl_index" and e["data"]["name"] == ix.index_name
        )
        assert actual["table"] == ix.table_name and actual["unique"] == ix.unique
    assert all(
        e["text"] in source and e["locator"]["char_end"] > e["locator"]["char_start"]
        for e in new
    )


def test_pinned_v1_db_code_forms_and_chunk_oracle(monkeypatch):
    legacy("ddl_parser", monkeypatch)
    v1 = legacy("db_code_parser", monkeypatch)
    source = "CREATE PROCEDURE P(P_ID IN NUMBER) AS BEGIN UPDATE T SET A=A-1 WHERE ID=P_ID; END; /"
    old = v1.parse_db_code_text(source, v1.DbCodeOptions())
    new = parse_sql(source, "oracle", {"T": ["ID", "A"]}).evidence
    for relation, values in [
        ("reads_from", old.procedures[0].reads),
        ("writes_to", old.procedures[0].writes),
    ]:
        assert set(values) <= {
            e["data"]["target"]
            for e in new
            if e["type"] == "sql_dependency" and e["data"]["relation_type"] == relation
        }
    assert any(
        e["type"] == "sql_statement" and e["data"]["components"][0]["value"] == "A - 1"
        for e in new
    )
    xml = '<form name="F"><block name="B1" table="T"><item name="ID" column="ID"/></block><block name="B2" table="T"><item name="ID" column="ID"/></block><button name="RUN" operation="P"/></form>'
    v1xml = legacy("xml_form_parser", monkeypatch)
    oldxml = v1xml.parse_xml_form_text(xml, v1xml.XmlFormOptions())
    newxml = parse_xml(xml).evidence
    assert oldxml.field_count == 2
    assert {"F.B1.ID", "F.B2.ID"} == {
        e["data"]["name"] for e in newxml if e["type"] == "xml_field"
    }
    assert {
        e["data"]["relation_type"] for e in newxml if e["type"] == "xml_dependency"
    } == {"uses_table", "maps_to"}
    # Legacy XML parser infers edits from a field's table. v3 deliberately rejects
    # that inference; explicit modes have independent positive/negative tests.
    chunker = legacy("chunking", monkeypatch)
    text = "# Title\n\nalpha beta\n\n## Child\n\ngamma delta\n"
    oldchunks = chunker.chunk_markdown(text, chunker.ChunkingOptions(max_chars=25))
    r = ParseResult("test")
    chunks(r, text, size=25)
    # Verified legacy defect: this boundary drops one separator newline.
    assert "".join(c.text for c in oldchunks) == text.replace("beta\n\n##", "beta\n##")
    assert "".join(e["text"] for e in r.evidence) == text
    assert {tuple(c.heading_path) for c in oldchunks} <= {
        tuple(e["locator"]["heading_path"]) for e in r.evidence
    }
