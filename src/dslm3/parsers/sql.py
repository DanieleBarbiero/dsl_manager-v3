"""Loss-preserving SQL units and scope-aware static dependencies.

SQLGlot parses SQL ASTs. PL/SQL envelopes are lexically recognized, never
executed or claimed to be a complete procedural compiler. Unresolved references
remain diagnostics and raw evidence, not fabricated schema attributes.
"""

from __future__ import annotations
import logging
import re

import sqlglot
import sqlparse
from sqlglot import exp
from sqlglot.dialects import Dialect

from dslm3.common import DomainError
from dslm3.parsers.base import ParseResult, location

logging.getLogger("sqlglot").setLevel(logging.ERROR)
IDENT = r'(?:"(?:""|[^"])+"|`(?:``|[^`])+`|\[[^\]]+\]|[A-Za-z_#$][\w$#]*)(?:\s*\.\s*(?:"(?:""|[^"])+"|`[^`]+`|\[[^\]]+\]|[A-Za-z_#$][\w$#]*))*'
UNIT = re.compile(
    r"\bCREATE\s+(?:OR\s+(?:REPLACE|ALTER)\s+)?(?:(?:EDITIONABLE|NONEDITIONABLE|DEFINER\s*=\s*\S+)\s+)?(PACKAGE\s+BODY|TYPE\s+BODY|PACKAGE|FUNCTION|PROCEDURE|TRIGGER|TYPE)\s+("
    + IDENT
    + r")",
    re.I,
)
CONTEXT = (exp.Select, exp.Update, exp.Delete, exp.Insert, exp.Merge)
HINTS = {
    "oracle": [
        r"\bVARCHAR2\b",
        r"\bPLS_INTEGER\b",
        r"\b(?:NON)?EDITIONABLE\b",
        r":(?:NEW|OLD)\.",
        r"\bRAISE_APPLICATION_ERROR\b",
        r"\bCONNECT\s+BY\b",
        r"\bPACKAGE\s+BODY\b",
        r"\(\+\)",
    ],
    "tsql": [
        r"\bNVARCHAR\b",
        r"\bTOP\s*\(?\d",
        r"\bGO\s*$",
        r"\bGETDATE\s*\(",
        r"@@\w+",
        r"\[dbo\]",
    ],
    "postgres": [
        r"\bLANGUAGE\s+(?:plpgsql|sql)\b",
        r"::\w+",
        r"\b(?:BIGSERIAL|SERIAL|JSONB)\b",
        r"\$\w*\$",
    ],
    "mysql": [
        r"\bDELIMITER\b",
        r"\bAUTO_INCREMENT\b",
        r"\bENGINE\s*=",
        r"\bUNSIGNED\b",
    ],
    "sqlite": [r"\bPRAGMA\b", r"\bAUTOINCREMENT\b", r"\bWITHOUT\s+ROWID\b"],
    "bigquery": [r"\bUNNEST\s*\(", r"\bSAFE_CAST\s*\(", r"`[^`]+\.[^`]+\.[^`]+`"],
    "snowflake": [r"\bQUALIFY\b", r"\bVARIANT\b", r"\bIFF\s*\("],
    "db2": [r"\bBEGIN\s+ATOMIC\b", r"\bWITH\s+UR\b", r"\bSYSCAT\."],
    "firebird": [r"\bSET\s+TERM\b", r"\bSUSPEND\b", r"\bGEN_ID\s*\("],
}
ALIASES = {
    "mssql": "tsql",
    "sqlserver": "tsql",
    "plsql": "oracle",
    "postgresql": "postgres",
    "mariadb": "mysql",
    "ansi": "",
    "generic": "",
}
LEGACY = {
    "oracle_outer_join_plus": r"\(\+\)",
    "oracle_connect_by": r"\bCONNECT\s+BY\b",
    "oracle_long_type": r"\bLONG(?:\s+RAW)?\b",
    "oracle_rule_hint": r"/\*\+\s*RULE\b",
    "oracle_sqlplus_directive": r"^\s*(?:SET\s+SERVEROUTPUT|SPOOL|PROMPT|WHENEVER\s+SQLERROR)",
    "sqlserver_legacy_outer_join": r"\*=|=\*",
    "mysql_delimiter": r"^\s*DELIMITER\b",
    "firebird_set_term": r"^\s*SET\s+TERM\b",
}


def catalog() -> dict:
    return {
        "ast_dialects": sorted(k for k in Dialect.classes if k),
        "lexical_only": ["db2", "firebird", "informix", "sybase"],
        "aliases": ALIASES,
        "procedure_strategy": "lexical_envelope_and_embedded_sql_ast",
        "version_detection": "explicit_declaration_or_feature_hints_only",
    }


def mask_literals(text: str) -> str:
    """Preserve offsets/newlines while hiding comments and literal strings."""
    pattern = re.compile(
        r"--[^\n]*|/\*[\s\S]*?\*/|q'(?P<q>[\[({<])|\$(?P<tag>\w*)\$|'", re.I
    )
    chars = list(text)
    pos = 0
    while match := pattern.search(text, pos):
        start = match.start()
        token = match.group()
        if token.startswith("--") or token.startswith("/*"):
            end = match.end()
        elif match.group("q"):
            closing = {"[": "]", "(": ")", "{": "}", "<": ">"}[match.group("q")] + "'"
            found = text.find(closing, match.end())
            end = len(text) if found < 0 else found + 2
        elif token.startswith("$"):
            found = text.find(token, match.end())
            end = len(text) if found < 0 else found + len(token)
        else:
            i = match.end()
            while i < len(text):
                if text[i] == "'":
                    if i + 1 < len(text) and text[i + 1] == "'":
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            end = i
        for i in range(start, end):
            if chars[i] != "\n":
                chars[i] = " "
        pos = end
    return "".join(chars)


def identify(text: str, dialect: str = "auto") -> dict:
    scores = {
        key: sum(bool(re.search(p, text, re.I | re.M)) for p in patterns)
        for key, patterns in HINTS.items()
    }
    ranked = sorted((v, k) for k, v in scores.items() if v)
    explicit = re.search(
        r"(?im)^\s*(?:--|/\*)\s*(?:dialect|database|dbms)\s*[:=]\s*([\w-]+)(?:\s+(\d+(?:\.\d+)*[a-z]?))?",
        text,
    )
    chosen = (
        ALIASES.get(dialect.casefold(), dialect.casefold())
        if dialect != "auto"
        else None
    )
    basis = "override" if chosen is not None else "ambiguous"
    if chosen is None and explicit:
        chosen = ALIASES.get(explicit[1].lower(), explicit[1].lower())
        basis = "declaration"
    if (
        chosen is None
        and ranked
        and (len(ranked) == 1 or ranked[-1][0] > ranked[-2][0])
    ):
        chosen = ranked[-1][1]
        basis = "syntax_hints"
    if chosen is None:
        chosen = ""
    if chosen not in Dialect.classes and chosen not in catalog()["lexical_only"]:
        raise DomainError("unknown_dialect", f"Dialetto sconosciuto: {chosen}.")
    return {
        "dialect": chosen or "generic",
        "basis": basis,
        "candidates": [k for _, k in reversed(ranked)],
        "declared_version": explicit[2] if explicit else None,
        "legacy_features": [
            k for k, p in LEGACY.items() if re.search(p, text, re.I | re.M)
        ],
        "ast_supported": chosen in Dialect.classes,
    }


def units(text: str):
    # Remove client directives before masking dollar strings: DELIMITER $$ is
    # not a PostgreSQL dollar-quoted literal. All replacements preserve offsets.
    cleaned = list(text)

    def blank(start, end):
        for i in range(start, end):
            if cleaned[i] != "\n":
                cleaned[i] = " "

    delimiters = []
    terminators = []
    for m in re.finditer(
        r"(?im)^[ \t]*(?:DELIMITER\s+(\S+)|SET\s+TERM\s+(\S+)\s+\S+)[ \t]*$", text
    ):
        delimiters.append(m[1] or m[2])
        blank(m.start(), m.end())
    for delimiter in delimiters:
        if delimiter != ";":
            for m in re.finditer(re.escape(delimiter) + r"(?=[ \t]*(?:\n|$))", text):
                terminators.extend([m.start(), m.end()])
                blank(m.start(), m.end())
    for m in re.finditer(
        r"(?im)^[ \t]*(?:/|GO(?:\s+\d+)?|SET\s+SERVEROUTPUT\s+\S+|SPOOL[^\n]*|PROMPT[^\n]*)[ \t]*$",
        "".join(cleaned),
    ):
        terminators.extend([m.start(), m.end()])
        blank(m.start(), m.end())
    prepared = "".join(cleaned)
    masked = mask_literals(prepared)
    starts = [
        m.start()
        for m in re.finditer(
            r"\bCREATE\s+(?:(?:OR\s+(?:REPLACE|ALTER)|GLOBAL\s+TEMPORARY|TEMPORARY|UNIQUE|EDITIONABLE|NONEDITIONABLE)\s+)*(?:TABLE|VIEW|MATERIALIZED\s+VIEW|INDEX|SEQUENCE|SYNONYM|PACKAGE|PROCEDURE|FUNCTION|TRIGGER|TYPE)\b",
            masked,
            re.I,
        )
    ]
    boundaries = sorted(set([0, len(text), *starts, *terminators]))
    for left, right in zip(boundaries, boundaries[1:]):
        block = prepared[left:right]
        meaningful = mask_literals(block).strip()
        if not meaningful:
            continue
        if UNIT.match(mask_literals(block).lstrip()) or re.match(
            r"(?:DECLARE|BEGIN)\b", meaningful, re.I
        ):
            # Procedural packages may contain many semicolon-terminated members.
            # A client terminator / GO or the next CREATE closes the envelope.
            first = len(block) - len(block.lstrip())
            last = len(block.rstrip())
            yield left + first, left + last, text[left + first : left + last]
            continue
        cursor = 0
        for piece in sqlparse.split(block):
            index = block.find(piece, cursor)
            if index < 0:
                continue
            start = left + index
            end = start + len(piece)
            cursor = index + len(piece)
            if mask_literals(piece).strip(" ;/$\n\t"):
                yield start, end, text[start:end]


def sql_name(node) -> str:
    if isinstance(node, exp.Table):
        return ".".join(
            x.name if x.args.get("quoted") else x.name.upper() for x in node.parts
        )
    if isinstance(node, exp.Identifier):
        return node.name if node.args.get("quoted") else node.name.upper()
    return str(node).strip('"`[]').upper()


def nearest(node):
    return node.find_ancestor(*CONTEXT)


def dependencies(
    tree, schema: dict[str, list[str]], parameters: set[str]
) -> tuple[list[dict], list[dict]]:
    schema = {k.upper(): {x.upper() for x in v} for k, v in schema.items()}
    deps = set()
    unresolved = []
    cte_names = {c.alias_or_name.upper() for c in tree.find_all(exp.CTE)}

    def tables_for(context):
        return [t for t in context.find_all(exp.Table) if nearest(t) is context]

    for table in tree.find_all(exp.Table):
        if table.name.upper() in cte_names:
            continue
        context = nearest(table)
        if context is None:
            continue
        target = context.args.get("this")
        if isinstance(target, exp.Schema):
            target = target.this
        is_target = target is table and not isinstance(context, exp.Select)
        deps.add(("writes_to" if is_target else "reads_from", sql_name(table)))
    for column in tree.find_all(exp.Column):
        col = column.name.upper()
        if col in {"ROWNUM", "ROWID", "LEVEL", "SQLCODE", "SQLERRM"}:
            continue
        if col in parameters and not any(col in values for values in schema.values()):
            continue
        context = nearest(column)
        if context is None:
            continue
        if column.table.upper() in {"NEW", "OLD"}:
            continue
        lookup = context
        resolved = None
        while lookup is not None:
            tables = [t for t in tables_for(lookup) if t.name.upper() not in cte_names]
            if column.table:
                matches = [
                    t
                    for t in tables
                    if column.table.upper() in {t.alias_or_name.upper(), t.name.upper()}
                ]
            else:
                known = [t for t in tables if col in schema.get(sql_name(t), set())]
                # Without schema, one direct table is unambiguous syntactically.
                matches = (
                    known if known else [t for t in tables if sql_name(t) not in schema]
                )
            if len(matches) == 1:
                t = sql_name(matches[0])
                if t in schema and col not in schema[t]:
                    unresolved.append(
                        {
                            "name": column.sql(),
                            "reason": "column_absent_from_schema",
                            "table": t,
                        }
                    )
                    break
                resolved = t + "." + col
                break
            if len(matches) > 1:
                unresolved.append({"name": column.sql(), "reason": "ambiguous_column"})
                break
            lookup = lookup.find_ancestor(*CONTEXT)
        if resolved:
            write = False
            if isinstance(context, exp.Update):
                write = any(
                    isinstance(e, exp.EQ) and e.this is column
                    for e in context.expressions
                )
            deps.add(("writes_to" if write else "reads_from", resolved))
        elif not any(x["name"] == column.sql() for x in unresolved):
            unresolved.append({"name": column.sql(), "reason": "unresolved_reference"})
    return [
        {"relation_type": kind, "target": target} for kind, target in sorted(deps)
    ], unresolved


def embedded_sql(body: str):
    masked = mask_literals(body)
    pos = 0
    while m := re.search(
        r"\b(?:SELECT|UPDATE|INSERT|DELETE|MERGE|WITH)\b", masked[pos:], re.I
    ):
        start = pos + m.start()
        end = masked.find(";", start)
        if end < 0:
            end = len(body)
        # A SELECT enclosed by RETURN (...) ends before its enclosing parenthesis.
        depth = 0
        for index in range(start, end):
            if masked[index] == "(":
                depth += 1
            elif masked[index] == ")":
                depth -= 1
                if depth < 0:
                    end = index
                    break
        # Semicolons in strings were masked, so this terminator is structural.
        yield start, end, body[start:end]
        pos = end + 1


def parse_sql(
    text: str, dialect: str = "auto", schema: dict | None = None
) -> ParseResult:
    result = ParseResult("sql/3")
    info = identify(text, dialect)
    result.metadata = info
    read = (
        info["dialect"]
        if info["dialect"] != "generic" and info["ast_supported"]
        else None
    )
    schema = dict(schema or {})
    if info["basis"] == "ambiguous":
        result.warn(
            "dialect_ambiguous",
            "Sintassi condivisa: nessun dialetto/versione può essere identificato con certezza.",
        )
    if not info["ast_supported"]:
        result.warn(
            "dialect_lexical_only",
            "Dialetto riconosciuto: conservazione lessicale; AST generico solo dove accettato.",
        )
    for start, end, raw in units(text):
        loc = location(text, start, end)
        unit = UNIT.search(mask_literals(raw))
        anonymous = re.match(r"\s*(?:DECLARE|BEGIN)\b", mask_literals(raw), re.I)
        if unit or anonymous:
            kind = re.sub(r"\s+", "_", unit[1].lower()) if unit else "anonymous_block"
            name = (
                unit[2].replace(" ", "").strip('"').upper()
                if unit
                else "ANONYMOUS::" + str(loc["line_start"])
            )
            if kind in {"package_body", "type_body"}:
                name += "::BODY"
            data = {
                "name": name,
                "unit_type": kind,
                "dialect": info["dialect"],
                "legacy_features": info["legacy_features"],
            }
            parameters = {
                m[1].upper()
                for m in re.finditer(
                    r"\b([\w$#]+)\s+(?:(?:IN|OUT|INOUT)\s+)?(?:NUMBER|INT(?:EGER)?|VARCHAR2?|NVARCHAR2?|TEXT|DATE|BOOLEAN|[\w.]+%TYPE)\b",
                    mask_literals(raw),
                    re.I,
                )
            }
            data["parameters"] = sorted(parameters)
            result.add("sql_" + kind, raw, data, loc)
            masked = mask_literals(raw)
            first_begin = re.search(r"\bBEGIN\b", masked, re.I)
            body_offset = (
                first_begin.end() if first_begin else unit.end() if unit else 0
            )
            body = raw[body_offset:]
            dollar = re.search(r"\$(\w*)\$([\s\S]*?)\$\1\$", raw)
            if dollar:
                body_offset = dollar.start(2)
                body = dollar[2]
            if kind in {"package", "package_body", "type_body"}:
                for nested in re.finditer(
                    r"\b(PROCEDURE|FUNCTION)\s+(" + IDENT + r")",
                    masked[unit.end() :],
                    re.I,
                ):
                    nstart = unit.end() + nested.start()
                    nname = name + "." + nested[2].upper()
                    result.add(
                        "sql_" + nested[1].lower(),
                        raw[nstart : nstart + len(nested[0])],
                        {
                            "name": nname,
                            "parent_unit": name,
                            "unit_type": nested[1].lower(),
                        },
                        location(text, start + nstart, start + nstart + len(nested[0])),
                    )
            if kind == "trigger":
                target = re.search(
                    r"\bON\s+(" + IDENT + r")", masked[:body_offset], re.I
                )
                if target:
                    trigger_table = target[1].upper()
                    result.add(
                        "sql_dependency",
                        raw,
                        {
                            "source": name,
                            "relation_type": "trigger_on",
                            "target": trigger_table,
                        },
                        loc,
                    )
                    for reference in re.finditer(
                        r":(NEW|OLD)\.([A-Za-z_][\w$#]*)", masked, re.I
                    ):
                        column = reference[2].upper()
                        remaining = masked[reference.end() :]
                        if (
                            trigger_table in schema
                            and column not in schema[trigger_table]
                        ):
                            result.warn(
                                "column_absent_from_schema",
                                "Colonna trigger non presente nello schema.",
                                table=trigger_table,
                                column=column,
                            )
                            continue
                        relation = (
                            "writes_to"
                            if re.match(r"\s*:=", remaining)
                            else "reads_from"
                        )
                        result.add(
                            "sql_dependency",
                            raw,
                            {
                                "source": name,
                                "relation_type": relation,
                                "target": trigger_table + "." + column,
                            },
                            loc,
                        )
            for a, b, statement in embedded_sql(body):
                _statement(
                    result,
                    statement,
                    start + body_offset + a,
                    start + body_offset + b,
                    text,
                    read,
                    schema,
                    name,
                    parameters,
                    procedural=True,
                )
            for call in re.finditer(
                r"(?im)(?:^|;|\bTHEN|\bBEGIN)\s*(" + IDENT + r")\s*\(",
                mask_literals(body),
            ):
                called = call[1].upper()
                if called not in {"IF", "WHILE", "FOR", "VALUES", "RETURN"}:
                    result.add(
                        "sql_dependency",
                        body[call.start() : call.end()],
                        {"source": name, "relation_type": "calls", "target": called},
                        location(
                            text,
                            start + body_offset + call.start(),
                            start + body_offset + call.end(),
                        ),
                    )
            if re.search(
                r"\b(?:EXECUTE\s+IMMEDIATE|DBMS_SQL|PREPARE\s+\w+\s+FROM|EXEC\s*\()",
                masked,
                re.I,
            ):
                result.warn(
                    "dynamic_sql_unresolved",
                    "SQL dinamico conservato: dipendenze runtime non inferite.",
                    unit=name,
                )
            continue
        _statement(result, raw, start, end, text, read, schema, None, set())
    return result


def _statement(
    result, raw, start, end, source, read, schema, owner, parameters, procedural=False
):
    loc = location(source, start, end)
    masked = mask_literals(raw)
    special = re.search(
        r"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:PUBLIC\s+)?(SYNONYM|DATABASE\s+LINK|DIRECTORY|TABLESPACE|CLUSTER|CONTEXT|LIBRARY)\s+("
        + IDENT
        + r")",
        masked,
        re.I,
    )
    if special:
        kind = re.sub(r"\s+", "_", special[1].lower())
        name = special[2].upper()
        result.add(
            "ddl_" + kind,
            raw,
            {"name": name, "object_type": kind, "recognition": "explicit_declaration"},
            loc,
        )
        if kind == "synonym":
            target = re.search(
                r"\bFOR\s+(" + IDENT + r")(?:@([\w.$#]+))?",
                masked[special.end() :],
                re.I,
            )
            if target:
                result.add(
                    "sql_dependency",
                    raw,
                    {
                        "source": name,
                        "relation_type": "synonym_for",
                        "target": target[1].upper()
                        + ("@" + target[2].upper() if target[2] else ""),
                    },
                    loc,
                )
        return
    try:
        parse_text = raw
        if (
            procedural
            and read in {"oracle", "postgres", "mysql"}
            and re.match(r"\s*SELECT\b", masked, re.I)
        ):
            into = re.search(r"\bINTO\s+[^;]+?(?=\bFROM\b)", masked, re.I)
            if into:
                parse_text = (
                    raw[: into.start()]
                    + " " * (into.end() - into.start())
                    + raw[into.end() :]
                )
        tree = sqlglot.parse_one(
            parse_text, read=read, error_level=sqlglot.ErrorLevel.RAISE
        )
        if tree is None:
            return
        if not isinstance(
            tree,
            (
                exp.Create,
                exp.Alter,
                exp.Drop,
                exp.Grant,
                exp.Revoke,
                exp.Select,
                exp.Union,
                exp.Intersect,
                exp.Except,
                exp.Update,
                exp.Delete,
                exp.Insert,
                exp.Merge,
                exp.Transaction,
                exp.Commit,
                exp.Rollback,
                exp.Set,
                exp.Use,
                exp.Pragma,
            ),
        ):
            raise ValueError("costrutto senza AST strutturato")
    except Exception as exc:
        result.add(
            "sql_unparsed", raw, {"owner": owner, "parse_error": str(exc)[:600]}, loc
        )
        result.warn(
            "sql_unparsed",
            "Statement conservato senza derivazione automatica.",
            line=loc["line_start"],
            detail=str(exc)[:300],
        )
        return
    if isinstance(tree, exp.Create):
        kind = (tree.args.get("kind") or "object").lower()
        if kind == "view" and re.search(r"\bMATERIALIZED\s+VIEW\b", masked, re.I):
            kind = "materialized view"
        target = tree.this
        table = target.this if isinstance(target, exp.Schema) else target
        if isinstance(target, exp.Index):
            table = target.this
        name = sql_name(table)
        result.add("ddl_" + kind, raw, {"name": name, "object_type": kind}, loc)
        if kind == "table" and isinstance(target, exp.Schema):
            cols = []
            for column in target.expressions:
                if not isinstance(column, exp.ColumnDef):
                    continue
                cname = sql_name(column.this)
                cols.append(cname)
                constraints = [c.sql(dialect=read) for c in column.constraints]
                result.add(
                    "ddl_column",
                    raw,
                    {
                        "name": name + "." + cname,
                        "table": name,
                        "column": cname,
                        "datatype": column.args["kind"].sql(dialect=read),
                        "constraints": constraints,
                        "nullable": not any(
                            isinstance(c.kind, exp.NotNullColumnConstraint)
                            for c in column.constraints
                        ),
                    },
                    loc,
                )
            schema[name] = cols
            for constraint in target.find_all(exp.Reference):
                referenced = constraint.this
                other = (
                    referenced.this
                    if isinstance(referenced, exp.Schema)
                    else referenced
                )
                local = constraint.find_ancestor(exp.ForeignKey, exp.ColumnDef)
                local_cols = (
                    [sql_name(x) for x in local.expressions]
                    if isinstance(local, exp.ForeignKey)
                    else [sql_name(local.this)]
                    if local
                    else []
                )
                result.add(
                    "ddl_constraint",
                    raw,
                    {
                        "table": name,
                        "constraint_type": "foreign_key",
                        "columns": local_cols,
                        "target_table": sql_name(other),
                        "target_columns": [sql_name(x) for x in referenced.expressions]
                        if isinstance(referenced, exp.Schema)
                        else [],
                    },
                    loc,
                )
            for pk in target.find_all(exp.PrimaryKey):
                result.add(
                    "ddl_constraint",
                    raw,
                    {
                        "table": name,
                        "constraint_type": "primary_key",
                        "columns": [sql_name(x) for x in pk.expressions],
                    },
                    loc,
                )
        if kind in {"view", "materialized view"}:
            owner = name
        if kind == "index" and isinstance(target, exp.Index):
            result.add(
                "sql_dependency",
                raw,
                {
                    "source": name,
                    "relation_type": "indexes",
                    "target": sql_name(target.args["table"]),
                },
                loc,
            )
    elif isinstance(tree, exp.Alter):
        result.add(
            "ddl_alter",
            raw,
            {"name": sql_name(tree.this), "ast": tree.sql(dialect=read)},
            loc,
        )
    elif isinstance(tree, (exp.Drop, exp.Grant, exp.Revoke)):
        result.add(
            "ddl_" + tree.key,
            raw,
            {"name": str(tree.this), "ast": tree.sql(dialect=read)},
            loc,
        )
    else:
        result.add(
            "sql_statement", raw, {"owner": owner, "statement_type": tree.key}, loc
        )
    if owner:
        deps, unresolved = dependencies(tree, schema, parameters)
        for dep in deps:
            result.add("sql_dependency", raw, {"source": owner, **dep}, loc)
        for item in unresolved:
            result.warn(
                item["reason"],
                "Riferimento SQL non promosso a dipendenza.",
                unit=owner,
                **{k: v for k, v in item.items() if k != "reason"},
            )
