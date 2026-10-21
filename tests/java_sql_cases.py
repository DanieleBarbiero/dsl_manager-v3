"""Synthetic SQL and Oracle Java fixtures shared by the Java analysis tests.

Data and helpers only: dslm3 is imported lazily, by functions that exist on the
unpatched tree too, so the golden generator can run before the patch.
SQL_CASES contain no Java unit and must parse identically with the flag on.
"""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests/fixtures/golden_sql4/digests.json"
DIALECTS = ("auto", "oracle")
REPO_SQL_PATHS = (
    "tests/fixtures/deterministic/business.sql",
    "tests/fixtures/deterministic/decrement.sql",
    "src/dslm3/resources/vega/database/schema_vega.sql",
    "src/dslm3/resources/vega/plsql/logica_vega.sql",
)


def canon(result) -> str:
    return json.dumps(
        [
            result.parser,
            result.status,
            result.evidence,
            result.diagnostics,
            result.metadata,
            result.artifacts,
        ],
        sort_keys=True,
        default=str,
        ensure_ascii=False,
    )


def _fingerprint(call, serialize) -> dict:
    try:
        value = call()
    except Exception as exc:  # the golden records expected failures too
        return {"error": type(exc).__name__, "reason": getattr(exc, "reason", None)}
    data = serialize(value).encode("utf-8", "surrogatepass")
    return {"sha256": hashlib.sha256(data).hexdigest()}


def fingerprint(call) -> dict:
    """Digest of a parse result, or the class/reason of the raised exception."""
    return _fingerprint(call, canon)


def value_fingerprint(call) -> dict:
    """Digest of a JSON value, or the class/reason of the raised exception."""
    return _fingerprint(
        call, lambda v: json.dumps(v, sort_keys=True, default=str, ensure_ascii=False)
    )


def derived(evidence: list) -> list:
    """Deterministic inventory rows and coverage report of parser evidence."""
    from dslm3.common import uid
    from dslm3.deterministic import coverage, inventory, planned

    rows = inventory(
        [
            {**e, "id": uid("EV", [i, e]), "revision_id": "REV_case", "path": "case.sql"}
            for i, e in enumerate(evidence)
        ]
    )
    actual = {r["id"]: {"payload": r["payload"], "state": "pending"} for r in planned(rows)}
    return [rows, coverage(rows, actual)]


def repo_sql() -> dict[str, str]:
    # Working trees may hold CRLF (core.autocrlf); goldens are computed on LF.
    return {
        p: (ROOT / p).read_bytes().decode("utf-8").replace("\r\n", "\n")
        for p in REPO_SQL_PATHS
    }


SQL_CASES = {
    "java_in_string": (
        "CREATE TABLE LOGS(MSG VARCHAR2(200));\n"
        "INSERT INTO LOGS(MSG) VALUES ('CREATE OR REPLACE JAVA SOURCE NAMED x AS class X {}');\n"
        "INSERT INTO LOGS(MSG) VALUES ('AS LANGUAGE JAVA NAME ''A.b()''');\n"
    ),
    "java_in_comment": (
        '-- CREATE OR REPLACE AND COMPILE JAVA SOURCE NAMED "ShellExec" AS\n'
        "/* CREATE OR REPLACE PROCEDURE X AS LANGUAGE JAVA NAME 'ShellExec.run()';\n"
        "   CREATE JAVA CLASS USING BFILE (D, 'X.class'); */\n"
        "CREATE TABLE T1(ID NUMBER PRIMARY KEY);\n"
    ),
    "java_identifiers": (
        "CREATE TABLE JAVA_SOURCE(NAME VARCHAR2(30), JAVA NUMBER);\n"
        "SELECT JAVA FROM JAVA_SOURCE;\n"
        "CREATE OR REPLACE PROCEDURE LANGUAGE_JAVA AS BEGIN UPDATE JAVA_SOURCE SET JAVA = 1; END;\n"
        "/\n"
    ),
    "language_c": (
        "CREATE OR REPLACE PROCEDURE C_CALL(X IN NUMBER) AS LANGUAGE C "
        'NAME "c_call" LIBRARY extlib;\n/\n'
    ),
    "force_view": (
        "CREATE TABLE T1(ID NUMBER);\n"
        "CREATE OR REPLACE FORCE VIEW V_T AS SELECT ID FROM T1;\n"
    ),
    "plsql_package": (
        "CREATE OR REPLACE PACKAGE PKG AS\n"
        "  PROCEDURE RUN(P IN NUMBER);\n"
        "  FUNCTION CALC RETURN NUMBER;\n"
        "END PKG;\n/\n"
        "CREATE OR REPLACE PACKAGE BODY PKG AS\n"
        "  PROCEDURE RUN(P IN NUMBER) IS BEGIN UPDATE T1 SET ID = P; END;\n"
        "  FUNCTION CALC RETURN NUMBER IS BEGIN RETURN 1; END;\n"
        "END PKG;\n/\n"
        "CREATE OR REPLACE TRIGGER TRG BEFORE INSERT ON T1 FOR EACH ROW\n"
        "BEGIN\n  :NEW.ID := PKG.CALC();\nEND;\n/\n"
    ),
    "sqlplus": (
        "SET SERVEROUTPUT ON\nPROMPT creating\nSPOOL out.log\n"
        "CREATE TABLE T2(A NUMBER);\nSPOOL OFF\n"
    ),
    "mysql_delimiter": (
        "DELIMITER $$\nCREATE PROCEDURE p() BEGIN SELECT 1; END$$\nDELIMITER ;\n"
    ),
    "tsql_go": (
        "CREATE TABLE [dbo].[T3]([A] NVARCHAR(10))\nGO\n"
        "SELECT TOP 1 A FROM [dbo].[T3]\nGO\n"
    ),
    "postgres_dollar": (
        "CREATE FUNCTION f() RETURNS int AS $$ BEGIN RETURN 1; END $$ LANGUAGE plpgsql;\n"
    ),
    "empty": "",
    "whitespace": "  \n\t\n",
    "slash_only": "/\n",
    "unterminated": "CREATE OR REPLACE PROCEDURE P AS BEGIN NULL;",
}

SHELL_SRC = """import java.io.*;
public class ShellExec {
  public static void runShell(String command) {
    if (onWindows()) { System.out.println("win"); }
    new Thread(new Runnable() { public void run() { int i = 3; i--; } }).start();
  }
  public static boolean onWindows() { return System.getProperty("os.name").startsWith("W"); }
};
"""
ENVELOPE = 'CREATE OR REPLACE AND COMPILE JAVA SOURCE NAMED "ShellExec" AS\n' + SHELL_SRC + "\n/\n"
CALL_SPEC = """CREATE OR REPLACE PROCEDURE "SHELL_RUN" (p_cmd IN VARCHAR2)
AS LANGUAGE JAVA NAME 'ShellExec.runShell (java.lang.String)';
/
"""
PACKAGE = """CREATE OR REPLACE PACKAGE OS_UTIL AS
  PROCEDURE RUN_CMD(p IN VARCHAR2) AS LANGUAGE JAVA NAME 'ShellExec.runShell(java.lang.String)';
  FUNCTION IS_WIN RETURN NUMBER IS LANGUAGE JAVA NAME 'ShellExec.onWindows() return int';
END;
/
"""
MIXED = (
    "CREATE TABLE T(X NUMBER);\n"
    + ENVELOPE
    + CALL_SPEC
    + "CREATE OR REPLACE PROCEDURE P AS BEGIN UPDATE T SET X=1; END;\n/\n"
)
EXTERNAL = "CREATE OR REPLACE JAVA CLASS USING BFILE (JDIR, 'ShellExec.class');\n/\n"

WIDGET = """package com.acme.tools;
import java.util.List; import java.util.ArrayList; import java.util.function.Supplier;
import java.util.logging.Logger; import com.acme.text.Formatter;
import static com.acme.util.Checks.require; import static java.lang.Math.max;
public class Widget {
  private static final Logger LOG = Logger.getLogger("w");
  private final List<String> items = new ArrayList<>();
  public Widget() { init(); }
  private void init() { LOG.info("init"); }
  public int size() { return size(0); }
  public int size(int extra) { return items.size() + extra + max(1, 2); }
  public void render(Object helper) {
    Formatter.format("x"); Inner.touch(); Shape.area();
    Runnable Local = this::init; Local.run(); helper.run(); require(true);
    Supplier<String> s = () -> describe(); toString();
    new Runnable() { public void run() { size(); } }.run();
    class Helper { void go() { init(); } }
  }
  String describe() { return Mode.FAST.name(); }
  static class Inner { static void touch() { } }
  interface Shape { static double area() { return 0; } }
  enum Mode { FAST, SLOW; void flip() { } }
  record Point(int x, int y) { Point { require(x >= 0); } int sum() { return x + y; } }
}
"""
DEEP = (
    "public class Deep {\n  String s() { return "
    + " + ".join(['"a"'] * 2500)
    + "; }\n}\n"
)
TEXT_BLOCK = '''public class Sql {
  // CREATE TABLE COMMENTED(ID NUMBER);
  /* CREATE OR REPLACE PROCEDURE X AS BEGIN NULL; END; */
  static String ddl() {
    return """
CREATE TABLE INSIDE_TEXT_BLOCK(ID NUMBER);
CREATE OR REPLACE VIEW V AS SELECT 1 FROM DUAL;
""";
  }
  static String q() { return "CREATE TABLE IN_STRING(ID NUMBER)"; }
}
'''

JAVA_CASES = {
    "raw": SHELL_SRC,
    "envelope": ENVELOPE,
    "call_spec": CALL_SPEC,
    "package": PACKAGE,
    "mixed": MIXED,
    "external": EXTERNAL,
    "external_named": (
        'CREATE OR REPLACE JAVA RESOURCE NAMED "cfg/app.properties" '
        "USING BFILE (CFG_DIR, 'app.properties');\n/\n"
        'CREATE OR REPLACE JAVA SOURCE NAMED SCOTT."ext/Lib" '
        "USING BFILE (SRC_DIR, 'Lib.java');\n/\n"
    ),
    "multi_no_slash": (
        'CREATE OR REPLACE AND COMPILE JAVA SOURCE NAMED "A" AS\n'
        "public class A { static int one() { return B.two(); } }\n"
        'CREATE OR REPLACE AND COMPILE JAVA SOURCE NAMED "B" AS\n'
        "public class B { static int two() { return 2; } }\n"
        "CREATE TABLE AFTER_JAVA(ID NUMBER);\n"
    ),
    "slash_names": (
        'CREATE OR REPLACE AND RESOLVE JAVA SOURCE NAMED "com/acme/Util" AS\n'
        "package com.acme;\n"
        "public class Util { public static String up(String s) { return s.toUpperCase(); } }\n"
        "/\n"
        "CREATE OR REPLACE FUNCTION UP(S IN VARCHAR2) RETURN VARCHAR2\n"
        "AS LANGUAGE JAVA NAME 'com/acme/Util.up(java.lang.String) return java.lang.String';\n"
        "/\n"
    ),
    "slash_in_comment": (
        'CREATE OR REPLACE AND COMPILE JAVA SOURCE NAMED "Cut" AS\n'
        "public class Cut {\n  /* a slash alone on a line ends the SQL*Plus unit\n"
        "/\n  */\n  static void a() { }\n}\n/\n"
    ),
    "create_in_text": (
        'CREATE OR REPLACE AND COMPILE JAVA SOURCE NAMED "Sql" AS\n'
        + TEXT_BLOCK
        + "/\nCREATE TABLE REAL_TABLE(ID NUMBER);\n"
    ),
    "crlf_envelope": ENVELOPE.replace("\n", "\r\n"),
    "deep": DEEP,
    "type_spec": (
        "CREATE OR REPLACE TYPE ADDR_T AS OBJECT (\n"
        "  STREET VARCHAR2(30),\n"
        "  MEMBER FUNCTION FMT RETURN VARCHAR2\n"
        "    AS LANGUAGE JAVA NAME 'com.acme.Addr.format() return java.lang.String'\n"
        ");\n/\n"
        "CREATE OR REPLACE TYPE BODY ADDR_T AS\n"
        "  STATIC FUNCTION MAKE RETURN ADDR_T IS LANGUAGE JAVA NAME "
        "'com.acme.Addr$Factory.make() return com.acme.Addr';\n"
        "END;\n/\n"
    ),
    "widget_envelope": (
        'CREATE OR REPLACE AND COMPILE JAVA SOURCE NAMED "com/acme/tools/Widget" AS\n'
        + WIDGET
        + "/\n"
    ),
}

# Files whose cached parser_version is pinned by the golden (oracle dialect).
PARSER_VERSION_FILES = (
    "java_identifiers.sql",
    "plsql_package.sql",
    "envelope.sql",
    "mixed.sql",
    "raw.sql",
    "ShellExec.java",
)
