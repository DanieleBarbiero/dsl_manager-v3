"""Oracle SQL/Java analysis with the java_analysis flag on (FUN labels of the patch).

Requires the optional extra 'java' (tree-sitter-java); skipped without it.
DSLM3_JAVA_CORPUS may name a local directory of non-distributable Oracle sources
for an extra differential check; it is skipped when unset.
"""

import os
from pathlib import Path

import pytest
from dslm3.common import DomainError, uid
from dslm3.deterministic import require_complete
from dslm3.exports import Exports
from dslm3.knowledge import Knowledge, OPT_IN_POLICIES, POLICIES, RULE_POLICIES
from dslm3.parsers import java
from dslm3.parsers.documents import decode, parse_document
from dslm3.parsers.java import has_java_units, looks_like_java, parse_java, parse_sql_java
from dslm3.parsers.sql import parse_sql
from dslm3.resolution import Resolver
from dslm3.service import Application
from dslm3.storage import DEFAULT_CONFIG
from java_sql_cases import (
    CALL_SPEC,
    ENVELOPE,
    JAVA_CASES,
    MIXED,
    PACKAGE,
    SHELL_SRC,
    SQL_CASES,
    WIDGET,
    canon,
    derived,
)

# dslm3.parsers.java imports tree-sitter lazily: the module itself always loads.
pytest.importorskip("tree_sitter_java")

JAVA_TYPES = {
    "sql_java_source",
    "sql_java_call_spec",
    "java_class",
    "java_method",
    "java_dependency",
    "java_unparsed",
}
BROKEN = (
    'CREATE OR REPLACE AND COMPILE JAVA SOURCE NAMED "Broken" AS\n'
    "public class Broken {\n  void a( { int x = ; }\n  void b() { a(); }\n}\n/\n"
    "CREATE TABLE AFTER_BROKEN(ID NUMBER);\n"
)
# Non-ASCII identifiers, comments and an astral character before declarations.
UNICODE = (
    'CREATE OR REPLACE AND COMPILE JAVA SOURCE NAMED "Città" AS\n'
    "// perché così — \U0001f600 \U0001d518\n"
    "public class Città {\n"
    '  static String s = "naïve \U0001f600";\n'
    "  static void avvio() { über(); }\n"
    "  static void über() { }\n"
    "}\n/\n"
    "CREATE OR REPLACE PROCEDURE AVVIA AS LANGUAGE JAVA NAME "
    "'Città.avvio()';\n/\n"
)


def of(result, kind):
    return [e for e in result.evidence if e["type"] == kind]


def names(result, kind):
    return [e["data"]["name"] for e in of(result, kind)]


def edges(result, kind="java_dependency"):
    return [
        (e["data"]["source"], e["data"]["target"], e["data"].get("basis"))
        for e in of(result, kind)
    ]


def reasons(result):
    return [d["reason"] for d in result.diagnostics]


def with_ids(result, revision="REV_a", path="a.sql"):
    return [
        {**e, "id": uid("EV", [revision, i, e]), "revision_id": revision, "path": path}
        for i, e in enumerate(result.evidence)
    ]


def located(text, result):
    """Every Java evidence text is the exact slice named by its character locator."""
    for e in result.evidence:
        if e["type"] in JAVA_TYPES:
            loc = e["locator"]
            assert text[loc["char_start"] : loc["char_end"]] == e["text"], e["type"]


def test_fun_01_java_source_is_isolated_and_analyzed():
    r = parse_sql_java(ENVELOPE, "oracle")
    assert r.status == "success"
    assert not of(r, "sql_unparsed")
    source = of(r, "sql_java_source")[0]["data"]
    assert source["name"] == "ShellExec" and source["storage"] == "inline"
    assert names(r, "java_class") == ["ShellExec", "ShellExec$1"]
    assert names(r, "java_method") == ["ShellExec.runShell", "ShellExec$1.run", "ShellExec.onWindows"]
    assert edges(r) == [("ShellExec.runShell", "ShellExec.onWindows", "same_class")]
    assert r.metadata["java_platform_calls"] == {
        "java.lang.System.out.println": 1,
        "java.lang.System.getProperty": 1,
    }
    assert r.metadata["java_grammar"].startswith("tree-sitter-java/")
    unresolved = [d for d in r.diagnostics if d["reason"] == "java_receiver_type_unresolved"]
    assert unresolved[0]["count"] == 2 and unresolved[0]["unit"] == "ShellExec"
    located(ENVELOPE, r)


def test_fun_02_standalone_call_spec():
    r = parse_sql_java(CALL_SPEC, "oracle")
    (spec,) = of(r, "sql_java_call_spec")
    assert spec["data"] == {
        "source": '"SHELL_RUN"',
        "relation_type": "calls",
        "target": "ShellExec.runShell",
        "target_kind": "java_unit",
        "binding": "java_call_spec",
        "java_signature": "(java.lang.String)",
    }
    assert names(r, "sql_procedure") == ['"SHELL_RUN"']
    located(CALL_SPEC, r)


def test_fun_03_package_call_specs_are_attributed_to_members():
    r = parse_sql_java(PACKAGE, "oracle")
    specs = {e["data"]["source"]: e["data"] for e in of(r, "sql_java_call_spec")}
    assert specs["OS_UTIL.RUN_CMD"]["target"] == "ShellExec.runShell"
    assert specs["OS_UTIL.IS_WIN"]["target"] == "ShellExec.onWindows"
    assert specs["OS_UTIL.IS_WIN"]["java_return"] == "int"
    assert specs["OS_UTIL.IS_WIN"]["java_signature"] == "()"


def test_fun_03_type_call_specs_and_binary_names():
    r = parse_sql_java(JAVA_CASES["type_spec"], "oracle")
    specs = {e["data"]["source"]: e["data"] for e in of(r, "sql_java_call_spec")}
    assert specs["ADDR_T.FMT"]["target"] == "com.acme.Addr.format"
    make = specs["ADDR_T::BODY.MAKE"]
    assert make["target"] == "com.acme.Addr.Factory.make"
    assert make["java_binary_target"] == "com.acme.Addr$Factory.make"
    assert make["java_return"] == "com.acme.Addr"


def test_fun_04_mixed_file_keeps_legacy_evidence():
    off = parse_sql(MIXED, "oracle")
    on = parse_sql_java(MIXED, "oracle")
    (source,) = of(on, "sql_java_source")
    start, end = source["locator"]["char_start"], source["locator"]["char_end"]

    def key(e):
        return e["type"], e["text"], e["data"], e["locator"]

    expected = [
        key(e)
        for e in off.evidence
        if not (
            e["type"] == "sql_unparsed"
            and start <= e["locator"]["char_start"] < e["locator"]["char_end"] <= end + 2
        )
    ]
    assert [key(e) for e in on.evidence if e["type"] not in JAVA_TYPES] == expected
    assert len(of(off, "sql_unparsed")) == 3 and not of(on, "sql_unparsed")
    assert of(on, "sql_java_call_spec")[0]["data"]["target"] == "ShellExec.runShell"


def test_fun_05_external_units_are_declared_not_analyzed():
    r = parse_sql_java(JAVA_CASES["external"], "oracle")
    (unit,) = of(r, "sql_java_source")
    assert unit["data"]["name"] is None and unit["data"]["storage"] == "external"
    assert unit["data"]["unit_type"] == "java_class"
    assert reasons(r) == ["java_binary_not_analyzed"]
    r = parse_sql_java(JAVA_CASES["external_named"], "oracle")
    resource, source = (e["data"] for e in of(r, "sql_java_source"))
    assert resource["name"] == "cfg/app.properties" and resource["unit_type"] == "java_resource"
    assert source["name"] == "ext.Lib" and source["declared_name"] == "ext/Lib"
    assert source["schema"] == "SCOTT"
    assert reasons(r) == ["java_binary_not_analyzed"] * 2


def test_fun_06_malformed_java_is_partial_without_exception():
    r = parse_sql_java(BROKEN, "oracle")
    assert r.status == "partial"
    assert "java_syntax_error" in reasons(r)
    assert of(r, "java_unparsed")
    assert names(r, "ddl_table") == ["AFTER_BROKEN"]
    located(BROKEN, r)


def test_fun_07_offsets_with_non_ascii_text():
    r = parse_sql_java(UNICODE, "oracle")
    assert names(r, "java_class") == ["Città"]
    assert edges(r) == [("Città.avvio", "Città.über", "same_class")]
    assert of(r, "sql_java_call_spec")[0]["data"]["target"] == "Città.avvio"
    located(UNICODE, r)
    for case in ("crlf_envelope", "widget_envelope", "create_in_text", "slash_names"):
        located(JAVA_CASES[case], parse_sql_java(JAVA_CASES[case], "oracle"))


def test_fun_08_headless_source_recognition():
    assert looks_like_java(SHELL_SRC) and looks_like_java(WIDGET)
    assert looks_like_java("﻿// header\n/* x */\npackage a.b;\nclass C { }\n")
    for text in (ENVELOPE, CALL_SPEC, PACKAGE, MIXED, *SQL_CASES.values()):
        assert not looks_like_java(text)
    # The lexical gate is case-sensitive and grammar-confirmed.
    assert not looks_like_java("CLASS X;\nSELECT 1 FROM DUAL;\n")
    assert not looks_like_java("import java.util.List;\nSELECT 1 FROM DUAL;\n")
    r = parse_sql_java(SHELL_SRC, "oracle")
    assert r.parser == java.PARSER
    assert "java_headless_source_detected" in reasons(r)
    assert names(r, "java_class") == ["ShellExec", "ShellExec$1"]
    assert all(e["data"].get("container") is None for e in of(r, "java_method"))


def test_fun_09_cross_file_resolution_is_case_sensitive():
    ev = with_ids(parse_sql_java(ENVELOPE, "oracle"), "REV_a", "shellexec.sql")
    ev += with_ids(parse_sql_java(CALL_SPEC, "oracle"), "REV_b", "spec.sql")
    resolver = Resolver(ev)
    assert resolver.resolve("ShellExec.runShell", "java_unit")["status"] == "resolved"
    assert resolver.resolve("shellexec.runshell", "java_unit")["status"] == "unresolved"
    assert resolver.resolve("SHELLEXEC.RUNSHELL", "java_unit")["status"] == "unresolved"
    # Java targets are complete names: no suffix match on a method name.
    assert resolver.resolve("runShell", "java_unit")["status"] == "unresolved"
    # The same source loaded twice is one declaration, not an ambiguity.
    ev += with_ids(parse_sql_java(ENVELOPE, "oracle"), "REV_c", "copy.sql")
    assert Resolver(ev).resolve("ShellExec.onWindows", "java_unit")["status"] == "resolved"


def test_fun_09_overloads_stay_ambiguous():
    ev = with_ids(parse_sql_java(JAVA_CASES["widget_envelope"], "oracle"))
    resolver = Resolver(ev)
    size = resolver.resolve("com.acme.tools.Widget.size", "java_unit")
    assert size["status"] == "ambiguous" and size["reason_code"] == "multiple_targets"
    rows, report = derived(parse_sql_java(JAVA_CASES["widget_envelope"], "oracle").evidence)
    require_complete(report)
    blocked = sorted(
        (c["resolution"]["raw_target"], c["reason_code"])
        for r in rows
        for c in r["components"]
        if c["applicability"] == "blocked_by_resolution"
    )
    # Overloads are never picked by arity; imported classes outside the
    # workspace stay unresolved instead of being invented.
    assert blocked == [
        ("com.acme.text.Formatter.format", "target_absent"),
        ("com.acme.tools.Widget.size", "multiple_targets"),
        ("com.acme.util.Checks.require", "target_absent"),
        ("com.acme.util.Checks.require", "target_absent"),
    ]


def test_fun_09_widget_names_and_bases():
    r = parse_sql_java(JAVA_CASES["widget_envelope"], "oracle")
    classes = names(r, "java_class")
    assert classes == [
        "com.acme.tools.Widget",
        "com.acme.tools.Widget$1",
        "com.acme.tools.Widget$1Helper",
        "com.acme.tools.Widget.Inner",
        "com.acme.tools.Widget.Shape",
        "com.acme.tools.Widget.Mode",
        "com.acme.tools.Widget.Point",
    ]
    signatures = {
        (e["data"]["name"], e["data"]["signature"]) for e in of(r, "java_method")
    }
    assert ("com.acme.tools.Widget.size", "()") in signatures
    assert ("com.acme.tools.Widget.size", "(int)") in signatures
    assert ("com.acme.tools.Widget.Point.Point", "(int,int)") in signatures
    found = set(edges(r))
    w = "com.acme.tools.Widget"
    assert (f"{w}.render", "com.acme.text.Formatter.format", "single_type_import") in found
    assert (f"{w}.render", "com.acme.util.Checks.require", "static_import") in found
    assert (f"{w}$1Helper.go", f"{w}.init", "enclosing_class") in found
    # Calls inside the anonymous class may hit inherited members: not promoted.
    assert not [e for e in found if e[0].startswith("com.acme.tools.Widget$1.")]
    assert r.metadata["java_platform_calls"] == {
        "java.util.logging.Logger.getLogger": 1,
        "java.lang.Math.max": 1,
        "java.lang.Object.toString": 1,
    }
    unresolved = [d for d in r.diagnostics if d["reason"] == "java_receiver_type_unresolved"]
    assert unresolved[0]["count"] == 7


def test_fun_10_java_files_end_to_end(tmp_path):
    config = {**DEFAULT_CONFIG, "java_analysis": "on"}
    path = tmp_path / "Widget.java"
    path.write_bytes(WIDGET.encode("utf-8"))
    r = parse_document(path, "REV", config, {})
    assert r.parser == java.PARSER and r.metadata["encoding"].startswith("utf-8")
    assert names(r, "java_class")[0] == "com.acme.tools.Widget"

    app = Application(tmp_path / "ws")
    app.store.configure(
        {
            "sql_dialect": "oracle",
            "java_analysis": "on",
            "automatic_policies": list(POLICIES.values()),
        }
    )
    app.ingest("ShellExec.java", SHELL_SRC.encode("utf-8"))
    app.ingest("spec.sql", (CALL_SPEC + PACKAGE).encode("utf-8"))
    app.ingest("Widget.java", WIDGET.encode("utf-8"))
    result = app.parse_all()
    assert result["errors"] == result["partial"] == 0, result
    k = Knowledge(app)
    assert k.derive()["coverage"]["complete"]
    current = [c for c in k.candidates() if c["current_derivation"] and c["leaf"]]
    rules = {c["rule"] for c in current}
    assert set(OPT_IN_POLICIES) <= rules
    relations = {
        (c["payload"]["source_entity"], c["payload"]["target_entity"])
        for c in current
        if c["rule"] == "sql_java_call_spec"
    }
    assert ('"SHELL_RUN"', "ShellExec.runShell") in relations
    assert ("OS_UTIL.IS_WIN", "ShellExec.onWindows") in relations

    # Conservative policies never accept Java candidates.
    k.auto_review()
    java_states = {
        c["state"] for c in k.candidates() if c["rule"] in OPT_IN_POLICIES and c["leaf"]
    }
    assert java_states == {"pending"}
    app.store.configure({"automatic_policies": list(RULE_POLICIES.values())})
    assert k.auto_review()["count"]
    confirmed = {c["rule"] for c in k.candidates("confirmed")}
    assert set(OPT_IN_POLICIES) <= confirmed
    k.merge()
    k.reconcile()
    content = Exports(app).snapshot()["content"]
    assert "java_code_unit" in str(content)


def test_fun_11_multiple_sources_without_slash_and_slash_names():
    r = parse_sql_java(JAVA_CASES["multi_no_slash"], "oracle")
    assert names(r, "sql_java_source") == ["A", "B"]
    assert edges(r) == [("A.one", "B.two", "static_qualifier")]
    assert names(r, "ddl_table") == ["AFTER_JAVA"]
    r = parse_sql_java(JAVA_CASES["slash_names"], "oracle")
    (source,) = of(r, "sql_java_source")
    assert source["data"]["name"] == "com.acme.Util"
    assert source["data"]["declared_name"] == "com/acme/Util"
    (spec,) = of(r, "sql_java_call_spec")
    assert spec["data"]["target"] == "com.acme.Util.up"
    assert spec["data"]["java_binary_target"] == "com/acme/Util.up"
    ev = with_ids(r)
    assert Resolver(ev).resolve(spec["data"]["target"], "java_unit")["status"] == "resolved"


def test_fun_11_parser_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(java, "_LANGUAGE", [None])
    assert not java.available() and java.grammar_version() is None
    r = parse_sql_java(ENVELOPE, "oracle")
    off = parse_sql(ENVELOPE, "oracle")
    assert r.evidence == off.evidence
    assert reasons(r) == reasons(off) + ["java_parser_unavailable"]
    assert "java_parser_unavailable" in reasons(parse_sql_java(SHELL_SRC, "oracle"))
    for text in SQL_CASES.values():
        if text is not SQL_CASES["tsql_go"]:
            assert canon(parse_sql_java(text, "oracle")) == canon(parse_sql(text, "oracle"))
    with pytest.raises(DomainError) as error:
        parse_java(SHELL_SRC)
    assert error.value.reason == "java_parser_unavailable"
    path = tmp_path / "ShellExec.java"
    path.write_bytes(SHELL_SRC.encode("utf-8"))
    with pytest.raises(DomainError):
        parse_document(path, "REV", {**DEFAULT_CONFIG, "java_analysis": "on"}, {})


def test_edge_slash_alone_in_java_comment_ends_the_unit():
    # Same as SQL*Plus: a line holding only "/" terminates the statement.
    r = parse_sql_java(JAVA_CASES["slash_in_comment"], "oracle")
    assert r.status == "partial"
    assert "java_syntax_error" in reasons(r)
    assert of(r, "java_unparsed") and of(r, "sql_unparsed")


def test_edge_create_inside_java_text_is_not_sql():
    r = parse_sql_java(JAVA_CASES["create_in_text"], "oracle")
    assert names(r, "ddl_table") == ["REAL_TABLE"]
    assert names(r, "java_method") == ["Sql.ddl", "Sql.q"]


def test_edge_crlf_matches_lf():
    lf = parse_sql_java(JAVA_CASES["envelope"], "oracle")
    crlf = parse_sql_java(JAVA_CASES["crlf_envelope"], "oracle")
    assert [(e["type"], e["data"]) for e in crlf.evidence] == [
        (e["type"], e["data"]) for e in lf.evidence
    ]
    assert not of(crlf, "sql_unparsed")


def test_edge_deep_expression_does_not_recurse():
    r = parse_sql_java(JAVA_CASES["deep"], "oracle")
    assert names(r, "java_method") == ["Deep.s"]


def test_edge_call_spec_without_method_is_a_diagnostic():
    text = "CREATE OR REPLACE PROCEDURE P AS LANGUAGE JAVA NAME 'run';\n/\n"
    r = parse_sql_java(text, "oracle")
    assert r.status == "success"
    assert names(r, "sql_procedure") == ["P"]
    assert not of(r, "sql_java_call_spec")
    assert reasons(r) == ["java_call_spec_unparsed"]


def test_edge_java_in_sql_literals_and_comments_is_ignored():
    for name in ("java_in_string", "java_in_comment", "java_identifiers", "language_c"):
        assert not has_java_units(SQL_CASES[name]), name
    for name in ("envelope", "call_spec", "package", "external", "type_spec"):
        assert has_java_units(JAVA_CASES[name]), name


@pytest.mark.parametrize("name", sorted(JAVA_CASES))
def test_reg_05_java_evidence_is_fully_classified(name):
    r = parse_sql_java(JAVA_CASES[name], "oracle")
    rows, report = derived(r.evidence)
    require_complete(report)
    assert report["counts"]["unclassified_components"] == 0
    assert report["counts"]["unclassified_evidence_count"] == 0
    rules = {c["rule"] for row in rows for c in row["components"] if c["rule"]}
    java_rules = {
        c["rule"]
        for row in rows
        if row["type"] in JAVA_TYPES
        for c in row["components"]
        if c["rule"]
    }
    assert java_rules <= set(OPT_IN_POLICIES)
    assert rules - java_rules <= set(POLICIES) | {None}


def test_reg_06_sql_resolution_is_unchanged_by_java_units():
    sql = with_ids(parse_sql(SQL_CASES["plsql_package"], "oracle"), "REV_sql")
    both = sql + with_ids(parse_sql_java(ENVELOPE, "oracle"), "REV_java")
    for raw, kind in (
        ("RUN", "code_unit"),
        ("PKG.RUN", "code_unit"),
        ("PKG.CALC", "code_unit"),
        ("T1", "data_object"),
        ("T1.ID", "column"),
    ):
        assert Resolver(both).resolve(raw, kind) == Resolver(sql).resolve(raw, kind), raw
    # A PL/SQL name never resolves to a Java method, nor the other way round.
    assert Resolver(both).resolve("run", "code_unit") == Resolver(sql).resolve("run", "code_unit")
    assert Resolver(both).resolve("PKG.RUN", "java_unit")["status"] == "unresolved"


CORPUS = os.environ.get("DSLM3_JAVA_CORPUS")


@pytest.mark.skipif(
    not CORPUS or not Path(CORPUS).is_dir(),
    reason="DSLM3_JAVA_CORPUS non impostato: corpus locale non distribuibile",
)
def test_corpus_differential():
    files = sorted(
        p
        for p in Path(CORPUS).rglob("*")
        if p.is_file() and p.suffix.lower() in {".sql", ".pks", ".pkb", ".java"}
    )
    assert files
    for path in files:
        text = decode(path.read_bytes())[0]
        if path.suffix.lower() == ".java":
            located(text, parse_java(text))
            continue
        on = parse_sql_java(text, "oracle")
        located(text, on)
        if not has_java_units(text) and not looks_like_java(text):
            off = parse_sql(text, "oracle")
            assert canon(on) == canon(off), path.name
        regions = [
            (e["locator"]["char_start"], e["locator"]["char_end"])
            for e in of(on, "sql_java_source")
        ]
        for e in of(on, "sql_unparsed"):
            a = e["locator"]["char_start"]
            assert not any(s <= a < z for s, z in regions), path.name
