"""Non-regression of the optional Java analysis (REG labels of the Java patch).

Goldens come from the unpatched parser (tests/fixtures/golden_sql4). These tests
do not need tree-sitter-java: with the flag off nothing Java is loaded, and SQL
without Java units takes the same path with the flag on.
"""

import json
import subprocess
import sys
from functools import partial
from importlib.metadata import version
from pathlib import Path

import pytest
from dslm3.ai import AI, TECHNICAL
from dslm3.common import DomainError, digest
from dslm3.exports import Exports
from dslm3.knowledge import Knowledge, OPT_IN_POLICIES, POLICIES, RULE_POLICIES
from dslm3.parsers.documents import parse_document
from dslm3.parsers.java import parse_sql_java
from dslm3.parsers.sql import parse_sql
from dslm3.service import Application
from dslm3.storage import DEFAULT_CONFIG, OPTIONAL_CONFIG
from dslm3.web import dispatch
from java_sql_cases import (
    DIALECTS,
    GOLDEN,
    JAVA_CASES,
    PARSER_VERSION_FILES,
    SHELL_SRC,
    SQL_CASES,
    WIDGET,
    derived,
    fingerprint,
    repo_sql,
    value_fingerprint,
)

GOLD = json.loads(GOLDEN.read_text(encoding="utf-8"))
JAVA_ONLY_TYPES = {"sql_java_source", "java_class", "java_method"}
FILES = {f"{n}.sql": t for n, t in {**SQL_CASES, **JAVA_CASES}.items()}
FILES.update({"ShellExec.java": SHELL_SRC, "Widget.java": WIDGET})

pytestmark = pytest.mark.skipif(
    any(version(p) != v for p, v in GOLD["versions"].items()),
    reason="goldens recorded with other sqlglot/sqlparse versions: regenerate them",
)


def _groups(*names):
    groups = {"sql": SQL_CASES, "java": JAVA_CASES, "repo": repo_sql()}
    return [
        (group, name, text)
        for group in names
        for name, text in groups[group].items()
    ]


@pytest.mark.parametrize("group,name,text", _groups("sql", "repo"))
def test_reg_01_sql_without_java_matches_golden_flag_off_and_on(group, name, text):
    for dialect in DIALECTS:
        expected = GOLD["parse_sql"][f"{group}:{name}:{dialect}"]
        assert fingerprint(partial(parse_sql, text, dialect)) == expected
        assert fingerprint(partial(parse_sql, text, dialect, java=True)) == expected
        assert fingerprint(partial(parse_sql_java, text, dialect)) == expected


@pytest.mark.parametrize("group,name,text", _groups("java"))
def test_reg_02_java_inputs_flag_off_match_golden(group, name, text):
    for dialect in DIALECTS:
        expected = GOLD["parse_sql"][f"{group}:{name}:{dialect}"]
        assert fingerprint(partial(parse_sql, text, dialect)) == expected


def test_reg_02_dispatch_flag_off_matches_golden(tmp_path):
    for name, text in FILES.items():
        path = tmp_path / name
        path.write_bytes(text.encode("utf-8"))
        for config in (dict(DEFAULT_CONFIG), {**DEFAULT_CONFIG, "java_analysis": "off"}):
            got = fingerprint(partial(parse_document, path, "REV", config, {}))
            assert got == GOLD["dispatch"][name], name
    assert GOLD["dispatch"]["ShellExec.java"]["reason"] == "unsupported_format"


def test_reg_03_parser_version_and_cache_across_flag_cycle(tmp_path):
    app = Application(tmp_path / "ws")
    app.store.configure({"sql_dialect": "oracle"})
    revisions = {
        name: app.ingest(name, FILES[name].encode("utf-8"))["revision_id"]
        for name in PARSER_VERSION_FILES
    }

    def parse_round():
        out = {}
        for name, rev in revisions.items():
            summary = app.parse(rev, {})
            row = app.store.one(
                "SELECT parser_version FROM parses WHERE id=?", (summary["parse_id"],)
            )
            out[name] = (row["parser_version"], bool(summary.get("cached")))
        return out

    off = parse_round()
    assert {n: v for n, (v, _) in off.items()} == GOLD["parser_version"]
    app.store.configure({"java_analysis": "on"})
    on = parse_round()
    # SQL without Java keeps its cache key: the existing parse is reused.
    for name in ("java_identifiers.sql", "plsql_package.sql"):
        assert on[name] == (off[name][0], True), name
    for name in ("envelope.sql", "mixed.sql", "raw.sql", "ShellExec.java"):
        assert on[name][0] != off[name][0] and not on[name][1], name
    app.store.configure({"java_analysis": "off"})
    back = parse_round()
    assert {n: v for n, (v, _) in back.items()} == GOLD["parser_version"]
    # Off again: previous successful parses are reactivated without a new parse.
    for name in PARSER_VERSION_FILES:
        if name != "ShellExec.java":  # failed (unsupported_format) parses are never cached
            assert back[name][1], name


def test_reg_04_configuration_digest_default_and_validation(tmp_path):
    assert "java_analysis" not in DEFAULT_CONFIG
    assert OPTIONAL_CONFIG == {"java_analysis": "off"}
    assert digest(DEFAULT_CONFIG) == GOLD["default_config_digest"]
    app = Application(tmp_path)
    project = tmp_path / "project.json"

    def stored():
        return json.loads(project.read_text(encoding="utf-8"))

    assert digest(app.store.config()) == GOLD["workspace_config_digest"]
    assert "java_analysis" not in stored()
    app.store.configure({"java_analysis": "off"})
    assert "java_analysis" not in stored()
    assert digest(app.store.config()) == GOLD["workspace_config_digest"]
    for values in ({"java_analysis": "yes"}, {"java_analysis": True}, {"java": "on"}):
        with pytest.raises(DomainError) as error:
            app.store.configure(values)
        assert error.value.reason == "invalid_config"
    assert digest(app.store.config()) == GOLD["workspace_config_digest"]
    app.store.configure({"java_analysis": "on"})
    assert stored()["java_analysis"] == "on"
    assert digest(app.store.config()) != GOLD["workspace_config_digest"]
    app.store.configure({"java_analysis": "off"})
    assert "java_analysis" not in stored()
    assert digest(app.store.config()) == GOLD["workspace_config_digest"]


@pytest.mark.parametrize("group,name,text", _groups("sql", "repo", "java"))
def test_reg_05_legacy_inventory_and_coverage_match_golden(group, name, text):
    expected = GOLD["inventory"][f"{group}:{name}"]
    run = value_fingerprint(lambda: derived(parse_sql(text, "oracle").evidence))
    assert run == expected
    if group != "java":
        flag_on = value_fingerprint(
            lambda: derived(parse_sql(text, "oracle", java=True).evidence)
        )
        assert flag_on == expected


def test_reg_07_java_policies_are_opt_in():
    assert set(OPT_IN_POLICIES) == {"java_unit", "java_dependency", "sql_java_call_spec"}
    assert set(OPT_IN_POLICIES.values()).isdisjoint(POLICIES.values())
    assert set(OPT_IN_POLICIES).isdisjoint(POLICIES)
    assert RULE_POLICIES == {**POLICIES, **OPT_IN_POLICIES}


def test_reg_07_conservative_profile_and_policy_validation(tmp_path):
    app = Application(tmp_path)
    config = dispatch(app, "config", {"profile": "conservative"})["config"]
    assert config["automatic_policies"] == list(POLICIES.values())
    assert not set(config["automatic_policies"]) & set(OPT_IN_POLICIES.values())
    opt_in = sorted(OPT_IN_POLICIES.values())
    values = {"automatic_policies": opt_in}
    config = dispatch(app, "config", {"values": values})["config"]
    assert config["automatic_policies"] == opt_in
    with pytest.raises(DomainError) as error:
        dispatch(app, "config", {"values": {"automatic_policies": ["java_any/1"]}})
    assert error.value.reason == "unknown_policy"


def test_reg_09_ai_technical_selection_and_exports_unchanged(tmp_path):
    assert TECHNICAL - JAVA_ONLY_TYPES == set(GOLD["technical"])
    app = Application(tmp_path)
    app.store.configure(
        {"sql_dialect": "oracle", "automatic_policies": list(POLICIES.values())}
    )
    for name, text in repo_sql().items():
        if name.startswith("tests/"):
            app.ingest(Path(name).name, text.encode("utf-8"))

    def run():
        result = app.parse_all()
        assert result["errors"] == 0, result
        k = Knowledge(app)
        k.derive()
        k.auto_review()
        k.merge()
        k.reconcile()
        selection = AI(app).select("technical_extraction")
        items = [
            (i["evidence_id"], i["outcome"], i["reason_codes"])
            for i in selection["items"]
        ]
        return Exports(app).snapshot()["hash"], items

    before = run()
    app.store.configure({"java_analysis": "on"})
    assert run() == before


def test_reg_10_flag_off_never_loads_java_modules(tmp_path):
    probe = tmp_path / "probe.py"
    probe.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "from dslm3.parsers.documents import parse_document\n"
        "from dslm3.service import Application\n"
        "from dslm3.storage import DEFAULT_CONFIG\n"
        "root = Path(sys.argv[1])\n"
        "path = root / 'mixed.sql'\n"
        "parse_document(path, 'REV', dict(DEFAULT_CONFIG), {})\n"
        "app = Application(root / 'ws')\n"
        "rev = app.ingest('mixed.sql', path.read_bytes())['revision_id']\n"
        "app.parse(rev, {})\n"
        "loaded = sorted(m for m in sys.modules if m in "
        "{'dslm3.parsers.java', 'tree_sitter_java'})\n"
        "print(loaded)\n",
        encoding="utf-8",
    )
    (tmp_path / "mixed.sql").write_bytes(JAVA_CASES["mixed"].encode("utf-8"))
    run = subprocess.run(
        [sys.executable, str(probe), str(tmp_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert run.stdout.strip().splitlines()[-1] == "[]"
